"""QR payload construction — turning a validated request into the string that
gets encoded, per QR type (Phase 2a).

Pure: no DB, no rendering. Rendering is app/services/render.py.
"""
import json
import logging
import re

logger = logging.getLogger("DR")


def build_gs1_content(data):
    # Real GS1 Digital Link: https://id.gs1.org/01/<gtin>...
    # Accept gtin, lot, expiry, serial, etc.
    gtin = data.get("gtin") or data.get("content") or ""
    # if content already looks like GS1 Digital Link, return as is
    if gtin.startswith("http"):
        return gtin
    # if content has parentheses AI like (01)09506000134352(17)240105
    if gtin.startswith("("):
        # Convert AI format to digital link path: (01)X(10)Y -> /01/X/10/Y
        try:
            # parse (AI)value
            parts = re.findall(r"\((\d+)\)([^(]+)", gtin)
            if parts:
                path = "/".join([f"{ai}/{val.strip()}" for ai, val in parts])
                return f"https://id.gs1.org/{path}"
        except Exception as e:
            logger.warning("GS1 parse failed: %s", e)
        return gtin
    # if gtin is plain 8/12/13/14 digits
    gtin_digits = re.sub(r"\D", "", gtin)
    if 8 <= len(gtin_digits) <= 14:
        # pad to 14 for GS1
        gtin14 = gtin_digits.zfill(14)
        extra = ""
        if data.get("lot"):
            extra += f"/10/{data['lot']}"
        if data.get("serial"):
            extra += f"/21/{data['serial']}"
        if data.get("expiry"):
            extra += f"/17/{data['expiry']}"
        return f"https://id.gs1.org/01/{gtin14}{extra}"
    # fallback
    return data.get("url") or data.get("content") or gtin or "https://id.gs1.org/"


def build_qr_content(qr_type, data):
    t = qr_type.lower().strip()
    d = data or {}
    try:
        if t == "url" or t == "link":
            url = d.get("url") or d.get("content") or "https://DRandco.com"
            if not re.match(r'^https?://', url):
                url = "https://" + url
            return url
        elif t == "text":
            return d.get("text") or d.get("content") or "Hello DR & CO"
        elif t == "email":
            email = d.get("email", "")
            subj = d.get("subject", "")
            body = d.get("body", "")
            return f"mailto:{email}?subject={subj}&body={body}"
        elif t == "sms":
            num = d.get("phone") or d.get("number") or ""
            msg = d.get("message") or d.get("body") or ""
            return f"SMSTO:{num}:{msg}"
        elif t == "wifi":
            ssid = d.get("ssid", "")
            pwd = d.get("password", "")
            enc = d.get("encryption", "WPA")
            hidden = "true" if d.get("hidden") else "false"
            return f"WIFI:T:{enc};S:{ssid};P:{pwd};H:{hidden};;"
        elif t == "vcard":
            fn = d.get("name") or d.get("fullName") or "John Doe"
            org = d.get("organization") or ""
            phone = d.get("phone") or ""
            email = d.get("email") or ""
            url = d.get("url") or ""
            addr = d.get("address") or ""
            return f"BEGIN:VCARD\nVERSION:3.0\nFN:{fn}\nORG:{org}\nTEL:{phone}\nEMAIL:{email}\nURL:{url}\nADR:{addr}\nEND:VCARD"
        elif t == "whatsapp":
            phone = d.get("phone", "")
            msg = d.get("message", "")
            return f"https://wa.me/{phone}?text={msg}"
        elif t == "location":
            lat = d.get("latitude") or d.get("lat") or "0"
            lon = d.get("longitude") or d.get("lon") or "0"
            return f"geo:{lat},{lon}"
        elif t == "event":
            title = d.get("title", "Event")
            loc = d.get("location", "")
            start = d.get("start") or d.get("startDate") or "20260101T100000Z"
            end = d.get("end") or d.get("endDate") or "20260101T120000Z"
            desc = d.get("description", "")
            return f"BEGIN:VEVENT\nSUMMARY:{title}\nLOCATION:{loc}\nDTSTART:{start}\nDTEND:{end}\nDESCRIPTION:{desc}\nEND:VEVENT"
        elif t in ["facebook", "instagram", "youtube", "tiktok", "twitter", "pinterest", "linkedin"]:
            return d.get("url") or d.get("link") or f"https://{t}.com/"
        elif t == "mp3" or t == "audio":
            return d.get("url") or d.get("link") or ""
        elif t == "file":
            return d.get("url") or d.get("fileUrl") or d.get("content") or "https://DRandco.com/file"
        elif t in ["appstore", "app stores"]:
            android = d.get("android") or ""
            ios = d.get("ios") or ""
            return android or ios or "https://play.google.com/store"
        elif t == "smarturl" or t == "smart url" or t == "multiurl":
            # Store rules but return primary for generation; routing happens on redirect
            return d.get("primaryUrl") or d.get("url") or "https://DRandco.com"
        elif t == "gs1":
            return build_gs1_content(d)
        elif t == "menu":
            return d.get("url") or json.dumps(d)
        elif t == "landingpage" or t == "landing page":
            return d.get("url") or "https://DRandco.com/landing"
        elif t == "linkpage" or t == "link page" or t == "bio":
            return d.get("url") or json.dumps(d.get("links", []))
        elif t == "googlereview" or t == "google review":
            return d.get("url") or ""
        elif t == "googleform":
            return d.get("url") or ""
        else:
            return d.get("url") or d.get("content") or d.get("text") or json.dumps(d)
    except Exception as e:
        logger.warning("build_qr_content error for %s: %s", qr_type, e)
        return str(data)
