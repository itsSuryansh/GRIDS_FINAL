"""Build the GRIDS logo lockup as SVG, then convert to the exact WOFF2 the UI needs.

Reference: a satellite over a globe -- light-blue landmass inside a navy/blue
orbit arc -- with a blue locator arrow on the horizon, a map-pin on the arc, a
heavy condensed GRIDS wordmark and the spaced-out sub-line.

The wordmark glyph outlines are extracted from Archivo Black (SIL Open Font
License) so the text is real vector outlines, not a font reference: the SVGs
stand alone anywhere, with no webfont required.
"""
import base64
import io
import pathlib
import string
import sys

from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

WORK = pathlib.Path("/home/user/logo-work")
OUT = WORK
FONT = WORK / "archivo-black.ttf"

# ---------------------------------------------------------------- glyphs ----
font = TTFont(FONT)
upem = font["head"].unitsPerEm
glyphset = font.getGlyphSet()
cmap = font.getBestCmap()
hmtx = font["hmtx"]


def glyph_path(ch, size, tracking_px=0.0):
    """Return (path_d, advance_px) for one character, baseline at y=0, y down."""
    name = cmap[ord(ch)]
    pen = SVGPathPen(glyphset, ntos=lambda v: f"{v:.2f}")
    scale = size / upem
    # font units are y-up: flip to SVG y-down
    tpen = TransformPen(pen, (scale, 0, 0, -scale, 0, 0))
    glyphset[name].draw(tpen)
    advance = hmtx[name][0] * scale + tracking_px
    return pen.getCommands(), advance


def word_paths(text, size, tracking_px=0.0):
    x = 0.0
    parts = []
    for ch in text:
        if ch == " ":
            x += size * 0.30 + tracking_px
            continue
        d, adv = glyph_path(ch, size, tracking_px)
        parts.append((x, d))
        x += adv - tracking_px + tracking_px
    return parts, x


def spaced_text_paths(text, size, tracking_px):
    """Heavy-tracking caps for the sub-line (e.g. G N S S - R E S ...)."""
    return word_paths(text, size, tracking_px)


def text_width(text, size, tracking_px=0.0):
    return word_paths(text, size, tracking_px)[1]


# ------------------------------------------------------------- the mark ----
# The mark is drawn on its own 240x150 canvas and then placed by transform, so
# the geometry stays hand-tuned instead of derived from guesswork.
MW, MH = 240.0, 150.0


def catmull(points, closed=True, tension=1.0):
    """Smooth open/closed polyline through the given points (Catmull-Rom -> cubic)."""
    pts = list(points)
    n = len(pts)
    if closed:
        ext = [pts[-1]] + pts + [pts[0], pts[1]]
    else:
        ext = [pts[0]] + pts + [pts[-1]]
    d = [f"M{pts[0][0]:.2f} {pts[0][1]:.2f}"]
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6 * tension, p1[1] + (p2[1] - p0[1]) / 6 * tension)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6 * tension, p2[1] - (p3[1] - p1[1]) / 6 * tension)
        d.append(f"C{c1[0]:.2f} {c1[1]:.2f} {c2[0]:.2f} {c2[1]:.2f} {p2[0]:.2f} {p2[1]:.2f}")
    if closed:
        d.append("Z")
    return "".join(d)


LAND_MAIN = [
    (74, 40), (86, 28), (102, 26), (114, 32), (124, 28), (134, 34), (136, 44),
    (131, 52), (138, 60), (134, 72), (124, 78), (121, 88), (109, 90), (100, 84),
    (92, 86), (86, 74), (79, 66), (79, 54), (70, 48),
]
LAND_ISLE = [(143, 70), (153, 66), (160, 71), (157, 79), (147, 81), (141, 76)]
LAND_SOUTH = [(88, 94), (100, 92), (107, 99), (99, 106), (89, 104), (84, 99)]

MARK_BODY_T = """
  <!-- globe: landmass clipped to the sphere -->
  <circle cx="116" cy="62" r="41" fill="{globe}"/>
  <g clip-path="url(#globeClip)">
    <path d="{catmull(LAND_MAIN)}" fill="url(#land)"/>
    <path d="{catmull(LAND_ISLE)}" fill="url(#land)" opacity="0.75"/>
    <path d="{catmull(LAND_SOUTH)}" fill="url(#land)" opacity="0.45"/>
  </g>

  <!-- orbit arc over the globe -->
  <path d="M14 99C34 24 166 6 202 66" fill="none" stroke="url(#arcNavy)"
        stroke-width="6.4" stroke-linecap="round"/>

  <!-- globe lower horizon: bright blue rim -->
  <path d="M66 103C90 118 144 118 168 101" fill="none" stroke="url(#arcBlue)"
        stroke-width="5.8" stroke-linecap="round"/>
  <!-- thin echo below the horizon -->
  <path d="M82 127C102 137 138 137 156 126" fill="none" stroke="#7fd0f4"
        stroke-width="2.3" stroke-linecap="round" opacity="0.8"/>

  <!-- locator arrow lifting off the horizon -->
  <path d="M176 52 L148 104 L164 98 L170 112 Z" fill="url(#arrow)"/>
  <path d="M176 52 L170 112 L164 98 Z" fill="#8ed6f6" opacity="0.85"/>

  <!-- pin above the arc -->
  <path d="M193 25c6.6 0 12 5.4 12 12 0 8.8-12 22-12 22s-12-13.2-12-22c0-6.6 5.4-12 12-12z" fill="#0f3d75"/>
  <circle cx="193" cy="37" r="4.2" fill="#ffffff"/>

  <!-- satellite: dish, bus, panels -->
  <g transform="translate(40 46) rotate(-38)">
    <path d="M-5 12l9 9-9 5z" fill="#1a5fae"/>
    <rect x="-22" y="-6.5" width="44" height="13" rx="2.4" fill="#0f3d75"/>
    <rect x="-22" y="-6.5" width="13" height="13" rx="2" fill="#1a5fae"/>
    <rect x="9" y="-6.5" width="13" height="13" rx="2" fill="#1a5fae"/>
    <g stroke="#eaf4fc" stroke-width="1.15" stroke-opacity="0.7">
      <line x1="-17" y1="-6.5" x2="-17" y2="6.5"/><line x1="-12.5" y1="-6.5" x2="-12.5" y2="6.5"/>
      <line x1="12.5" y1="-6.5" x2="12.5" y2="6.5"/><line x1="17" y1="-6.5" x2="17" y2="6.5"/>
    </g>
    <rect x="-4" y="6.5" width="8" height="6" rx="1.5" fill="#0f3d75"/>
  </g>
  <!-- signal arcs off the dish -->
  <g fill="none" stroke="#1a5fae" stroke-linecap="round">
    <path d="M62 68a15 15 0 0 1 15 15" stroke-width="2.8" opacity="0.36"/>
    <path d="M62 60a23 23 0 0 1 23 23" stroke-width="2.8" opacity="0.64"/>
    <path d="M62 52a31 31 0 0 1 31 31" stroke-width="2.8" opacity="0.95"/>
  </g>
"""


MARK_BODY_LIGHT = MARK_BODY_T.replace('fill="{globe}"', 'fill="#e6f1fb"')
MARK_BODY_DARK = MARK_BODY_T.replace('fill="{globe}"', 'fill="#f8fbff"')


def mark_svg(cx, cy, w, opacity=1.0, on_light=False):
    """Place the 240x150 mark so its centre lands on (cx, cy) with width w."""
    k = w / MW
    tx, ty = cx - (MW / 2) * k, cy - (MH / 2) * k
    body = MARK_BODY_LIGHT if on_light else MARK_BODY_DARK
    return (f'  <g opacity="{opacity}" transform="translate({tx:.2f},{ty:.2f}) scale({k:.4f})">'
            f'<g id="grids-mark-body">{body}</g></g>')


DEFS = """<defs>
    <linearGradient id="arcNavy" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#123a6b"/><stop offset="0.5" stop-color="#0f3d75"/><stop offset="1" stop-color="#1c6fd0"/>
    </linearGradient>
    <linearGradient id="arcBlue" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#5ec8f5"/><stop offset="0.55" stop-color="#2f9ae8"/><stop offset="1" stop-color="#12457f"/>
    </linearGradient>
    <linearGradient id="land" x1="0" y1="0" x2="0.3" y2="1">
      <stop offset="0" stop-color="#dceaf8"/><stop offset="1" stop-color="#a9cdea"/>
    </linearGradient>
    <linearGradient id="arrow" x1="0" y1="1" x2="1" y2="0">
      <stop offset="0" stop-color="#5ec8f5"/><stop offset="1" stop-color="#12507f"/>
    </linearGradient>
    <clipPath id="globeClip"><circle cx="116" cy="62" r="41"/></clipPath>
    <linearGradient id="word" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#0d2a4d"/><stop offset="1" stop-color="#081c34"/>
    </linearGradient>
  </defs>"""


def wordmark_fragment(size, cx, baseline_y, text="GRIDS", tracking=0.0, fill="url(#word)"):
    parts, width = word_paths(text, size, tracking)
    x0 = cx - width / 2
    d = " ".join(f'<path transform="translate({x0 + x:.2f},{baseline_y:.2f})" d="{dd}"/>'
                 for x, dd in parts if dd)
    return f'  <g fill="{fill}">{d}</g>', width


def build_full(width=1000):
    """Horizontal-free, stacked lockup: mark above the wordmark, sub-line below."""
    h = width * 0.92
    cx = width / 2
    mark_cy = width * 0.245
    head, ww = wordmark_fragment(width * 0.235, cx, width * 0.665)
    sub, subw = spaced_text_paths("GNSS-RESILIENT INTELLIGENT", width * 0.0285, width * 0.0125)
    sub2, sub2w = spaced_text_paths("DEAD RECKONING SYSTEM", width * 0.0285, width * 0.0125)
    sub_frag = " ".join(f'<path transform="translate({cx - subw / 2 + x:.2f},{width*0.745:.2f})" d="{d}"/>'
                        for x, d in sub if d)
    sub2_frag = " ".join(f'<path transform="translate({cx - sub2w / 2 + x:.2f},{width*0.792:.2f})" d="{d}"/>'
                         for x, d in sub2 if d)
    rule_y1, rule_y2 = width * 0.738, width * 0.788
    rule_len = width * 0.085
    left_edge = cx - max(ww / 2, subw / 2, sub2w / 2) - width * 0.02
    right_edge = cx + max(ww / 2, subw / 2, sub2w / 2) + width * 0.02
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {h:.0f}" width="{width}" height="{h:.0f}" role="img" aria-label="GRIDS — GNSS-Resilient Intelligent Dead Reckoning System">
  <title>GRIDS — GNSS-Resilient Intelligent Dead Reckoning System</title>
  {DEFS}
{mark_svg(cx, mark_cy, width * 0.62, on_light=True)}
{head}
  <g fill="#1c6fd0">
    <rect x="{left_edge - rule_len:.2f}" y="{rule_y1:.2f}" width="{rule_len:.2f}" height="{width*0.006:.2f}" rx="{width*0.003:.2f}"/>
    <rect x="{right_edge:.2f}" y="{rule_y2:.2f}" width="{rule_len:.2f}" height="{width*0.006:.2f}" rx="{width*0.003:.2f}"/>
  </g>
  <g fill="#0d2a4d">{sub_frag}</g>
  <g fill="#0d2a4d">{sub2_frag}</g>
</svg>
"""
    return svg


def build_horizontal(width=1000):
    """Wide lockup for the top bar: mark left, wordmark + sub-line right."""
    h = width * 0.30
    r = h * 0.40
    mark_cx = h * 0.52
    mark_cy = h * 0.50
    text_x = h * 1.10
    head, ww = wordmark_fragment(width * 0.105, 0, h * 0.60)
    # left-align the wordmark at text_x
    parts, wwidth = word_paths("GRIDS", width * 0.105, 0)
    head_frag = " ".join(f'<path transform="translate({text_x + x:.2f},{h*0.575:.2f})" d="{d}"/>'
                         for x, d in parts if d)
    sub, sw = spaced_text_paths("GNSS-RESILIENT INTELLIGENT DEAD RECKONING SYSTEM",
                                h * 0.085, h * 0.055)
    sub_frag = " ".join(f'<path transform="translate({text_x + x:.2f},{h*0.815:.2f})" d="{d}"/>'
                        for x, d in sub if d)
    total_w = text_x + max(wwidth, sw) + h * 0.18
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_w:.0f} {h:.0f}" width="{total_w:.0f}" height="{h:.0f}" role="img" aria-label="GRIDS">
  <title>GRIDS — GNSS-Resilient Intelligent Dead Reckoning System</title>
  {DEFS}
{mark_svg(mark_cx, mark_cy, h * 0.86, on_light=True)}
  <g fill="url(#word)">{head_frag}</g>
  <g fill="#47617f">{sub_frag}</g>
</svg>
"""
    return svg


def build_tile(size=64):
    """Square app icon / favicon: the mark alone on a navy tile."""
    s = size
    tile = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {s} {s}" width="{s}" height="{s}" role="img" aria-label="GRIDS">
  <title>GRIDS</title>
  {DEFS}
  <rect width="{s}" height="{s}" rx="{s*0.22:.2f}" fill="#0b1f38"/>
  <rect x="0.5" y="0.5" width="{s-1}" height="{s-1}" rx="{s*0.22:.2f}" fill="none" stroke="#2f9ae8" stroke-opacity="0.28" stroke-width="{s*0.012:.2f}"/>
{mark_svg(s/2, s*0.50, s*0.80)}
</svg>
"""
    return tile


# ------------------------------------------------------------------ build ----
def build_symbol():
    """Transparent mark only (no tile) -- used in the dashboard top bar."""
    body = MARK_BODY_LIGHT
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {MW:.0f} {MH:.0f}" width="{MW:.0f}" height="{MH:.0f}" role="img" aria-label="GRIDS">
  <title>GRIDS</title>
  {DEFS}
  <g id="grids-mark-body">{body}</g>
</svg>
"""


svg_symbol = build_symbol()
(OUT / "grids-symbol.svg").write_text(svg_symbol)
svg_full = build_full()
svg_h = build_horizontal()
svg_tile = build_tile()
(OUT / "grids-logo.svg").write_text(svg_full)
(OUT / "grids-lockup-horizontal.svg").write_text(svg_h)
(OUT / "grids-mark.svg").write_text(svg_tile)
print("wrote svgs", len(svg_full), len(svg_h), len(svg_tile))

# WOFF2 subset for the dashboard wordmark: digit-free, uppercase only.
sub = TTFont(FONT)
keep = set(map(ord, "ABCDEFGHIJKLMNOPQRSTUVWXYZ -"))
sub.setGlyphOrder  # noqa: B018  (keep API warm)
from fontTools import subset as ftsubset

opts = ftsubset.Options()
opts.flavor = "woff2"
opts.desubroutinize = False
opts.layout_features = []
opts.name_IDs = [1, 2, 6]
opts.notdef_outline = True
f2 = TTFont(FONT)
subs = ftsubset.Subsetter(options=opts)
subs.populate(text="ABCDEFGHIJKLMNOPQRSTUVWXYZ -")
subs.subset(f2)
f2.flavor = "woff2"
buf = io.BytesIO()
f2.save(buf)
data = buf.getvalue()
(OUT / "archivo-black-subset.woff2").write_bytes(data)
print("woff2 bytes", len(data))
