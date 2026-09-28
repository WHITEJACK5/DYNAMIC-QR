"""User-agent parsing into (device, browser, os).

Pure string matching, no dependency on a UA database: the three fields are
used for analytics grouping, so a coarse, predictable answer is preferable to
a heavyweight parser with a different answer per release.
"""


def detect_device(user_agent):
    ua = (user_agent or "").lower()
    device = "Desktop"
    browser = "Unknown"
    os_name = "Unknown"
    if "mobile" in ua or "android" in ua or "iphone" in ua:
        device = "Mobile"
    elif "tablet" in ua or "ipad" in ua:
        device = "Tablet"
    if "chrome" in ua and "edg" not in ua:
        browser = "Chrome"
    elif "firefox" in ua:
        browser = "Firefox"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    elif "edg" in ua:
        browser = "Edge"
    if "windows" in ua:
        os_name = "Windows"
    elif "android" in ua:
        os_name = "Android"
    elif "iphone" in ua or "mac os" in ua:
        os_name = "iOS/Mac"
    elif "linux" in ua:
        os_name = "Linux"
    return device, browser, os_name
