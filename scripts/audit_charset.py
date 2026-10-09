"""Audit non-ASCII codepoints per file, flagging CP437-mangled UTF-8.

Prints each distinct non-ASCII character with its codepoint and count, so a
file can be judged clean (em dash U+2014, bullet U+2022) versus mangled
(the mojibake chars produced by mis-decoding those same bytes as CP437).
"""
import os
import sys
from collections import Counter

SKIP_DIRS = {".git", "node_modules", "__pycache__", "dist", ".pytest_cache"}
SKIP_EXT = {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico",
            ".db", ".map", ".woff", ".woff2", ".ttf", ".zip"}

# characters that mean "a byte was mis-decoded"
MANGLED = set("ΓÇöù¬Ö¬®†°£¥¤¡¢¤")


def audit(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except (UnicodeDecodeError, OSError):
        return None
    counts = Counter(ch for ch in text if ord(ch) > 127)
    if not counts:
        return []
    return [(ch, ord(ch), n, ch in MANGLED) for ch, n in counts.most_common()]


def main():
    root = sys.argv[1]
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in sorted(filenames):
            if os.path.splitext(name)[1] in SKIP_EXT:
                continue
            p = os.path.join(dirpath, name)
            rows = audit(p)
            if rows is None:
                continue
            if not rows:
                continue
            mangled = [r for r in rows if r[3]]
            rel = os.path.relpath(p, root)
            if mangled:
                print(f"MANGLED  {rel}")
                for ch, cp, n, _ in mangled:
                    print(f"    U+{cp:04X}  {ch!r}  x{n}")
            else:
                shown = ", ".join(f"U+{cp:04X}({ch})x{n}" for ch, cp, n, _ in rows[:6])
                print(f"clean    {rel}: {shown}")


if __name__ == "__main__":
    main()
