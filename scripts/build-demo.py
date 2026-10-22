"""Inline the built phone demo (web/dist-demo) into one self-contained HTML fragment."""

import sys
from pathlib import Path

dist = Path(__file__).resolve().parents[1] / "web" / "dist-demo"
out = Path(sys.argv[1])
js = next((dist / "assets").glob("*.js")).read_text().replace("</script", "<\\/script")
css = next((dist / "assets").glob("*.css")).read_text()
page = (
    "<title>Resident Kiosk Demo</title>\n"
    '<meta name="claude:viewport-fit-sides" content="cover">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">\n'
    f"<style>body{{margin:0;background:#0f172a}}{css}</style>\n"
    '<div id="root"></div>\n'
    f'<script type="module">{js}</script>\n'
)
out.write_text(page)
print(out, len(page) // 1024, "KB")
