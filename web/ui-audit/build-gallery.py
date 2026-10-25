"""Builds one self-contained HTML page that browses the resident and staff screenshots.

Usage: build-gallery.py <resident-dir> <staff-dir> <out.html>
Resident files: <screen>__<lang>__<text>__1280x800.png (and -night variants). Staff files: <page>__<lang>__1280x800.png.
"""

import base64
import io
import json
import sys
from pathlib import Path

from PIL import Image

res_dir, staff_dir, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])

RESIDENT = [
    ("home-clear", "Home"),
    ("home-locked", "Home, with a restriction"),
    ("why-locked", "Why is this locked?"),
    ("tier", "Tier and ceiling"),
    ("education", "Education"),
    ("commissary", "Commissary"),
    ("calls", "Calls"),
    ("reading", "Reading library"),
    ("jobs", "Optional jobs"),
    ("reentry", "Getting ready for release"),
]
STAFF = [
    ("dashboard", "Dashboard"),
    ("roster", "Roster"),
    ("confirmations", "Confirmations"),
    ("appeals", "Appeals"),
    ("welfare", "Welfare"),
    ("outliers", "Outliers"),
    ("view-as", "View as resident"),
    ("config", "Config"),
    ("devices", "Devices"),
    ("out-of-cell", "Out of cell"),
    ("schedule", "Schedule"),
    ("contacts", "Contacts"),
    ("monitoring", "Monitoring"),
    ("mirror", "Live mirror"),
    ("intake", "Intake"),
    ("content", "Content and jobs"),
    ("finance", "Finance"),
    ("outcomes", "Outcomes"),
    ("audit", "Audit log"),
    ("styleguide", "Style guide"),
]


def enc(path: Path, width: int = 1280) -> str | None:
    if not path.exists():
        return None
    im = Image.open(path).convert("RGB")
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)))
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=72, method=4)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


imgs: dict[str, str] = {}
for name, _ in RESIDENT:
    for lang in ("en", "es"):
        for text in ("normal", "large"):
            for theme in ("day", "night"):
                suffix = "-night" if theme == "night" else ""
                data = enc(res_dir / f"{name}{suffix}__{lang}__{text}__1280x800.png")
                if data:
                    imgs[f"r|{name}|{lang}|{text}|{theme}"] = data
for name, _ in STAFF:
    for lang in ("en", "es"):
        data = enc(staff_dir / f"{name}__{lang}__1280x800.png")
        if data:
            imgs[f"s|{name}|{lang}"] = data

page = (Path(__file__).parent / "gallery-template.html").read_text()
page = page.replace("__RESIDENT__", json.dumps(RESIDENT)).replace("__STAFF__", json.dumps(STAFF))
page = page.replace("__IMAGES__", json.dumps(imgs))
out.write_text(page)
print(out, len(page) // 1024, "KB,", len(imgs), "images")
