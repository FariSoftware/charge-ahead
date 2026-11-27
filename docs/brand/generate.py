"""Generate the Charge Ahead icon and logo SVGs.

The wordmark is outlined to paths, so the SVGs need no font at render time.
Requires fontTools and Fira Sans SemiBold (SIL Open Font License); adjust
FONT to its path. Render the PNGs in custom_components/charge_ahead/brand
with rsvg-convert.
"""
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from pathlib import Path

OUT = Path(__file__).parent
FONT = TTFont("/usr/share/fonts/truetype/google-fonts/ofl/firasans/FiraSans-SemiBold.ttf")

TEAL = "#0FA37F"
TEAL_DARK = "#0A7A5F"
INK = "#1E2A32"
INK_DARK_BG = "#EEF3F1"


def text_path(text: str, size: float, x: float, baseline: float) -> tuple[str, float]:
    """Return an SVG path for text and its advance width."""
    gs = FONT.getGlyphSet()
    cmap = FONT.getBestCmap()
    upm = FONT["head"].unitsPerEm
    scale = size / upm
    pen = SVGPathPen(gs)
    cursor = 0.0
    for ch in text:
        name = cmap[ord(ch)]
        # flip y: font units are y-up
        tpen = TransformPen(pen, (scale, 0, 0, -scale, x + cursor * scale, baseline))
        gs[name].draw(tpen)
        cursor += gs[name].width
    return pen.getCommands(), cursor * scale


def icon_group(dx: float = 0, dy: float = 0) -> str:
    # 256x256 artboard. Calendar page with binding tabs, bolt inside.
    # The gap around the tabs is cut out with a mask so it stays transparent
    # on any background.
    return f'''<defs>
  <mask id="tabgap" maskUnits="userSpaceOnUse" x="0" y="0" width="256" height="256">
    <rect width="256" height="256" fill="#fff"/>
    <rect x="62" y="8" width="42" height="68" rx="21" fill="#000"/>
    <rect x="152" y="8" width="42" height="68" rx="21" fill="#000"/>
  </mask>
</defs>
<g transform="translate({dx},{dy})">
  <g mask="url(#tabgap)">
    <rect x="20" y="40" width="216" height="196" rx="40" fill="{TEAL}"/>
    <path d="M20 80 a40 40 0 0 1 40 -40 h136 a40 40 0 0 1 40 40 v10 h-216 z" fill="{TEAL_DARK}"/>
  </g>
  <rect x="70" y="16" width="26" height="52" rx="13" fill="{TEAL_DARK}"/>
  <rect x="160" y="16" width="26" height="52" rx="13" fill="{TEAL_DARK}"/>
  <path d="M148 102 L88 172 H123 L108 226 L172 150 H134 L152 102 Z" fill="#FFFFFF"/>
</g>'''


def svg(width: float, height: float, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
        f'viewBox="0 0 {width:.2f} {height:.2f}">\n{body}\n</svg>\n'
    )


(OUT / "icon.svg").write_text(svg(256, 256, icon_group()))

def logo(word_color: str) -> str:
    size = 120
    baseline = 128 + size * 0.35
    p1, w1 = text_path("Charge", size, 296, baseline)
    p2, w2 = text_path("Ahead", size, 296 + w1 + 28, baseline)
    width = 296 + w1 + 28 + w2 + 8
    body = icon_group() + f'\n<path d="{p1}" fill="{word_color}"/>\n<path d="{p2}" fill="{TEAL}"/>'
    return svg(width, 256, body)

(OUT / "logo.svg").write_text(logo(INK))
(OUT / "dark_logo.svg").write_text(logo(INK_DARK_BG))
print("ok")
