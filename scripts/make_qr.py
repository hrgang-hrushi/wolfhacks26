"""Make the poster QR code for the phone dashboard.

Run after the site is deployed, with its real address:

    uv run --no-project --with segno --with pillow python scripts/make_qr.py https://<deployed-domain>/m?demo=1

Writes web/public/qr/unwatched-roads.png and .svg, each with the address printed
underneath so a poster still works if a phone will not scan it. `?demo=1` opens
the page straight into "Model in action".
"""

from __future__ import annotations

import argparse
import io
import re
from pathlib import Path
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "public" / "qr"


def short_url(url: str) -> str:
    """The address as a person would type it: no scheme, no query."""
    u = urlsplit(url)
    return f"{u.netloc}{u.path}".rstrip("/")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("url", help="full https address of the phone dashboard, e.g. https://example.org/m?demo=1")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--name", default="unwatched-roads")
    args = ap.parse_args()

    u = urlsplit(args.url)
    if u.scheme != "https" or not u.netloc:
        raise SystemExit("Give the full https:// address. A phone cannot open localhost, and location needs https.")

    import segno
    from PIL import Image, ImageDraw, ImageFont

    qr = segno.make(args.url, error="m")
    label = short_url(args.url)
    args.out.mkdir(parents=True, exist_ok=True)

    # SVG: the code, then the address as real text underneath.
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=10, border=4, xmldecl=False, svgns=True, nl=False)
    svg = buf.getvalue().decode()
    w, h = (int(float(v)) for v in re.search(r'width="([\d.]+)" height="([\d.]+)"', svg).groups())
    pad = 44
    inner = re.sub(r"^<svg[^>]*>|</svg>$", "", svg)
    (args.out / f"{args.name}.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h + pad}" viewBox="0 0 {w} {h + pad}">'
        f'<rect width="{w}" height="{h + pad}" fill="#fff"/>{inner}'
        f'<text x="{w / 2}" y="{h + 14}" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" '
        f'font-size="22" font-weight="700" fill="#111">{escape(label)}</text></svg>\n'
    )

    # PNG: same layout, drawn with Pillow.
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=16, border=4)
    code = Image.open(buf).convert("RGB")
    try:
        font = ImageFont.truetype("Helvetica.ttc", 34)
    except OSError:
        font = ImageFont.load_default(size=34)
    canvas = Image.new("RGB", (code.width, code.height + 60), "white")
    canvas.paste(code, (0, 0))
    draw = ImageDraw.Draw(canvas)
    tw = draw.textlength(label, font=font)
    draw.text(((code.width - tw) / 2, code.height - 18), label, fill="#111111", font=font)
    canvas.save(args.out / f"{args.name}.png")

    print(f"QR code for {args.url}")
    print(f"  {args.out / (args.name + '.png')}")
    print(f"  {args.out / (args.name + '.svg')}")
    print(f"Fallback address to print on the poster: {label}")


if __name__ == "__main__":
    main()
