"""Repair CP437-decoded UTF-8 mojibake across the project.

Root cause: UTF-8 bytes were decoded as CP437 at some point in the pipeline,
so U+2014 (em dash, bytes E2 80 94) surfaces as the three characters
"Gamma, C-cedilla, o-umlaut" = "—". Bullets and arrows mangled the same way.

The repair is the exact inverse of that mis-decode:
    raw = mojibake.encode("cp437")     # recover the original UTF-8 bytes
    fixed = raw.decode("utf-8")        # read them correctly

Only runs of high/Cyrillic-ish characters are touched, and a run is only
rewritten when the whole round-trip succeeds, so clean text is never
modified. Binary/build artefacts are excluded by extension.
"""
import os
import re
import sys

SKIP_DIRS = {".git", "node_modules", "__pycache__", "dist", ".pytest_cache",
             "build", ".venv", "venv"}
SKIP_EXT = {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico",
            ".db", ".map", ".coverage", ".zip", ".woff", ".woff2", ".ttf"}
SKIP_NAME = {"tsconfig.tsbuildinfo", "package-lock.json", "lighthouse-report.json",
             ".coverage", "lastfailed", "nodeids"}

# A run of characters that only appear because bytes were mis-decoded.
# Deliberately broad: the CP437 "high half" is scattered across Latin-1
# (¢£¥°), box-drawing/shade (U+2500-25FF, where a hamburger icon lands)
# and Greek (Î). Too narrow a set splits a glyph mid-sequence and defeats the
# round-trip. False positives are still impossible: a segment is only
# rewritten when encoding it back to cp437/cp1252 and decoding the result as
# UTF-8 succeeds, which real prose essentially never does by accident.
MOJI = re.compile(
    "[\u00a0-\u00ff\u0150-\u019f\u0370-\u03ff\u2018-\u201f\u2026\u20ac"
    "\u0152\u0153\u0178\u017d\u017e\u0160\u0161\u2020\u2021\u2030\u2039"
    "\u203a\u2122\u2200-\u22ff\u2500-\u25ff\u2190-\u21ff]{2,}"
)


# Both ways UTF-8 bytes get mis-decoded, plus the characters each produces.
#   cp437  -> "Gamma C-cedilla o-umlaut" for an em dash (PowerShell's OEM
#             codepage, hit by `git show x > file` in PS 5.1)
#   cp1252 -> "a-tilde euro cent-sign" for a bullet (the usual web mangle)
ENCODINGS = ("cp437", "cp1252")


def repair(text):
    """Return (fixed_text, n_segments_fixed)."""
    hits = [0]

    def repl(m):
        seg = m.group(0)
        for enc in ENCODINGS:
            try:
                raw = seg.encode(enc)
            except UnicodeEncodeError:
                continue
            try:
                fixed = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if fixed != seg and fixed and not seg.isspace():
                hits[0] += 1
                return fixed
        return seg

    return MOJI.sub(repl, text), hits[0]


def iter_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name in SKIP_NAME or os.path.splitext(name)[1] in SKIP_EXT:
                continue
            yield os.path.join(dirpath, name)


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    changed = 0
    total = 0
    for path in iter_files(root):
        try:
            with open(path, encoding="utf-8") as f:
                src = f.read()
        except (UnicodeDecodeError, OSError):
            continue
        fixed, n = repair(src)
        if fixed == src:
            continue
        if total < 40:
            print(f"  {n:3d} segments  {os.path.relpath(path, root)}")
        elif total == 40:
            print("  ... (further files suppressed)")
        total += n
        changed += 1
        if len(sys.argv) > 2 and sys.argv[2] == "--write":
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(fixed)
    print(f"\n{changed} files affected, {total} segments. "
          f"{'WRITTEN' if (len(sys.argv) > 2 and sys.argv[2] == '--write') else 'dry run'}")


if __name__ == "__main__":
    main()
