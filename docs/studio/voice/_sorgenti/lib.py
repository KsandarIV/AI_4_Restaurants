"""Mini motore per le slide: HTML 16:9 con schemi SVG, trasformato in PDF con Edge/Chrome headless.

Uso (dalla cartella _sorgenti):   python build.py        -> genera i 4 PDF nella cartella docs/studio/voice
Non servono librerie: solo la libreria standard e un browser Chromium (Edge o Chrome) installato.
"""

from __future__ import annotations

import html
import pathlib
import shutil
import subprocess
import tempfile

# palette = quella del sito del ristorante
INK, MUTED, LINE = "#2b211b", "#6e5f55", "#eadfce"
RED, DARK, CREAM, GOLD, BROWN, GREEN, BLUE = "#b3341f", "#8a2615", "#fffaf3", "#c9a227", "#3a1f14", "#2e8b57", "#2f5d8a"

CSS = f"""
@page {{ size: 1280px 720px; margin: 0; }}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; background: {CREAM}; color: {INK}; font-family: "Segoe UI", system-ui, Arial, sans-serif; }}
.slide {{ width: 1280px; height: 720px; position: relative; overflow: hidden; page-break-after: always; break-after: page;
  background: {CREAM}; padding: 46px 64px 54px; }}
.slide:last-child {{ page-break-after: auto; break-after: auto; }}
.tag {{ position: absolute; top: 20px; left: 64px; font-size: 13px; letter-spacing: .14em; text-transform: uppercase; color: {MUTED}; }}
.num {{ position: absolute; top: 20px; right: 64px; font-size: 13px; color: {MUTED}; }}
.foot {{ position: absolute; bottom: 18px; left: 64px; right: 64px; display: flex; justify-content: space-between; font-size: 12px; color: {MUTED};
  border-top: 1px solid {LINE}; padding-top: 8px; }}
h1 {{ font-family: Georgia, "Times New Roman", serif; font-size: 38px; margin: 26px 0 14px; color: {DARK}; line-height: 1.15; }}
h2 {{ font-family: Georgia, serif; font-size: 22px; margin: 0 0 8px; color: {DARK}; }}
p, li {{ font-size: 19px; line-height: 1.42; margin: 0 0 8px; }}
ul {{ margin: 0; padding-left: 22px; }}
li {{ margin-bottom: 6px; }}
small, .small {{ font-size: 15px; color: {MUTED}; }}
b, strong {{ color: {DARK}; }}
code, .mono {{ font-family: Consolas, "Cascadia Mono", monospace; font-size: .88em; background: #f4ece0; padding: 1px 6px; border-radius: 5px; color: {BROWN}; }}
pre {{ font-family: Consolas, monospace; font-size: 15px; line-height: 1.4; background: {BROWN}; color: #f6e9d6; padding: 14px 18px; border-radius: 12px; margin: 8px 0; white-space: pre-wrap; }}
.cols {{ display: flex; gap: 28px; align-items: flex-start; }}
.col {{ flex: 1; min-width: 0; }}
.card {{ background: #fff; border: 1px solid {LINE}; border-radius: 14px; padding: 14px 18px; box-shadow: 0 2px 8px rgba(58,31,20,.06); }}
.card.red {{ border-left: 6px solid {RED}; }} .card.gold {{ border-left: 6px solid {GOLD}; }}
.card.green {{ border-left: 6px solid {GREEN}; }} .card.brown {{ border-left: 6px solid {BROWN}; }} .card.blue {{ border-left: 6px solid {BLUE}; }}
.chip {{ display: inline-block; background: #f4ece0; color: {BROWN}; border-radius: 999px; padding: 3px 12px; font-size: 14px; margin: 0 6px 6px 0; }}
.chip.red {{ background: {RED}; color: #fff; }} .chip.brown {{ background: {BROWN}; color: #fff; }} .chip.green {{ background: {GREEN}; color: #fff; }}
.chip.gold {{ background: {GOLD}; color: #fff; }}
table {{ border-collapse: collapse; width: 100%; font-size: 16px; }}
th {{ text-align: left; background: {BROWN}; color: #fff; padding: 8px 12px; font-weight: 600; }}
td {{ padding: 7px 12px; border-bottom: 1px solid {LINE}; vertical-align: top; }}
tr:nth-child(even) td {{ background: #fff7ec; }}
.big {{ font-family: Georgia, serif; font-size: 54px; color: {RED}; line-height: 1; }}
.kpi {{ text-align: center; }} .kpi .lbl {{ font-size: 15px; color: {MUTED}; }}
.cover {{ background: linear-gradient(135deg, {BROWN} 0%, {DARK} 60%, {RED} 100%); color: #fff; padding: 0 90px; display: flex; flex-direction: column; justify-content: center; }}
.cover h1 {{ color: #fff; font-size: 54px; margin: 10px 0 14px; }} .cover p {{ color: #f6e9d6; font-size: 24px; }}
.cover .tag, .cover .num, .cover .foot {{ color: #e8d2bd; border-color: rgba(255,255,255,.25); }}
.problem {{ background: #fdecea; border: 1px solid #f0c4bd; border-radius: 12px; padding: 10px 16px; margin-bottom: 10px; }}
.fix {{ background: #e3f3e8; border: 1px solid #b9dfc6; border-radius: 12px; padding: 10px 16px; }}
.lbl-red {{ color: {DARK}; font-weight: 700; font-size: 14px; letter-spacing: .08em; text-transform: uppercase; }}
.lbl-green {{ color: #1f6b3d; font-weight: 700; font-size: 14px; letter-spacing: .08em; text-transform: uppercase; }}
svg text {{ font-family: "Segoe UI", system-ui, Arial, sans-serif; }}
"""


def esc(s: str) -> str:
    return html.escape(s, quote=False)


# ------------------------------------------------------------------ SVG helpers
_svg_counter = [0]


def svg(w: int, h: int, content: str) -> str:
    """Ogni schema ha marker con id propri: con id duplicati il browser userebbe quelli del primo schema della pagina."""
    _svg_counter[0] += 1
    u = _svg_counter[0]
    content = content.replace("url(#ahr)", f"url(#ahr{u})").replace("url(#ah)", f"url(#ah{u})")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            '<defs>'
            f'<marker id="ah{u}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{BROWN}"/></marker>'
            f'<marker id="ahr{u}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
            f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{RED}"/></marker>'
            '</defs>' + content + '</svg>')


def text(x: float, y: float, s: str, size: int = 16, weight: str = "400", anchor: str = "middle", fill: str = INK) -> str:
    size = max(size, 15)
    lines = s.split("\n")
    out = [f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}">']
    for i, line in enumerate(lines):
        out.append(f'<tspan x="{x}" dy="{0 if i == 0 else size * 1.22:.1f}">{esc(line)}</tspan>')
    out.append("</text>")
    return "".join(out)


def box(x: float, y: float, w: float, h: float, label: str, fill: str = "#fff", stroke: str = BROWN, color: str = INK,
        size: int = 16, weight: str = "600", sub: str = "", rx: int = 12) -> str:
    lines = label.split("\n")
    total = len(lines) * size * 1.22 + ((max(13, size - 2) * 1.22 * (sub.count(chr(10)) + 1) + 4) if sub else 0)
    y0 = y + (h - total) / 2 + size * 0.95
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>',
           text(x + w / 2, y0, label, size, weight, "middle", color)]
    if sub:
        out.append(text(x + w / 2, y0 + len(lines) * size * 1.22 + 2, sub, max(13, size - 2), "400", "middle",
                        color if color != INK else MUTED))
    return "".join(out)


def arrow(x1: float, y1: float, x2: float, y2: float, label: str = "", dash: bool = False, red: bool = False,
          lx: float = 0, ly: float = -8, size: int = 15) -> str:
    col = RED if red else BROWN
    d = ' stroke-dasharray="6 5"' if dash else ""
    mk = "ahr" if red else "ah"
    out = [f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-width="2.2"{d} marker-end="url(#{mk})"/>']
    if label:
        out.append(text((x1 + x2) / 2 + lx, (y1 + y2) / 2 + ly, label, size, "500", "middle", col))
    return "".join(out)


def line(x1: float, y1: float, x2: float, y2: float, col: str = LINE, w: float = 1.5, dash: bool = False) -> str:
    d = ' stroke-dasharray="5 5"' if dash else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-width="{w}"{d}/>'


def seq(actors: list[tuple[str, str]], steps: list[tuple[int, int, str] | tuple[int, int, str, bool]], width: int = 1150,
        height: int = 470, top: int = 70, gap: float | None = None, size: int = 14) -> str:
    """Diagramma di sequenza: attori in colonna, messaggi come frecce orizzontali."""
    n = len(actors)
    colw = width / n
    xs = [colw * (i + 0.5) for i in range(n)]
    out = []
    for i, (name, col) in enumerate(actors):
        out.append(box(xs[i] - colw / 2 + 8, 6, colw - 16, 44, name, fill=col, stroke=col, color="#fff", size=15))
        out.append(line(xs[i], 52, xs[i], height - 6, "#cdbba5", 2, True))
    step = gap or (height - top - 14) / max(1, len(steps))
    for k, st in enumerate(steps):
        a, b, label = st[0], st[1], st[2]
        red = len(st) > 3 and bool(st[3])
        y = top + k * step
        if a == b:
            out.append(text(xs[a] + 12, y + 4, label, size, "500", "start", RED if red else BROWN))
        else:
            off = 4 if xs[b] > xs[a] else -4
            out.append(arrow(xs[a] + off, y, xs[b] - off, y, label, red=red, ly=-6, size=size))
    return svg(width, height, "".join(out))


# ------------------------------------------------------------------ deck
class Deck:
    def __init__(self, tag: str, file_stem: str, footer: str = "Trattoria Bella Napoli · AI 4 Restaurants · componente VOICE") -> None:
        self.tag, self.stem, self.footer = tag, file_stem, footer
        self.slides: list[str] = []

    def cover(self, title: str, subtitle: str) -> None:
        self.slides.append(
            f'<section class="slide cover"><div class="tag">{esc(self.tag)}</div>'
            f'<div style="font-size:15px;letter-spacing:.2em;text-transform:uppercase;color:#e8d2bd">Presentazione tecnica</div>'
            f'<h1>{title}</h1><p>{subtitle}</p>'
            f'<div class="foot"><span>{esc(self.footer)}</span><span>Ottobre 2026</span></div></section>')

    def add(self, title: str, body: str) -> None:
        n = len(self.slides) + 1
        self.slides.append(
            f'<section class="slide"><div class="tag">{esc(self.tag)}</div><div class="num">{n}</div>'
            f'<h1>{title}</h1>{body}'
            f'<div class="foot"><span>{esc(self.footer)}</span><span>{esc(self.tag)} · {n}</span></div></section>')

    def html(self) -> str:
        return (f'<!doctype html><html lang="it"><head><meta charset="utf-8"><title>{esc(self.tag)}</title>'
                f'<style>{CSS}</style></head><body>{"".join(self.slides)}'
                '<script>var m=location.hash.match(/s([0-9]+)/);if(m){document.querySelectorAll(".slide").forEach(function(s,i){s.style.display=(i==+m[1]-1)?"block":"none";});}</script>'
                '</body></html>')

    def build(self, out_dir: pathlib.Path, src_dir: pathlib.Path) -> pathlib.Path:
        src_dir.mkdir(parents=True, exist_ok=True)
        html_path = src_dir / f"{self.stem}.html"
        html_path.write_text(self.html(), encoding="utf-8")
        pdf_path = out_dir / f"{self.stem}.pdf"
        to_pdf(html_path, pdf_path)
        return pdf_path


def find_browser() -> str:
    for cand in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                 r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                 r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if pathlib.Path(cand).is_file():
            return cand
    found = shutil.which("msedge") or shutil.which("chrome") or shutil.which("chromium")
    if not found:
        raise SystemExit("Serve Edge o Chrome installato per generare i PDF.")
    return found


def to_pdf(html_path: pathlib.Path, pdf_path: pathlib.Path) -> None:
    browser = find_browser()
    profile = tempfile.mkdtemp(prefix="slides_")
    cmd = [browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={profile}",
           f"--print-to-pdf={pdf_path}", "--virtual-time-budget=4000", html_path.resolve().as_uri()]
    subprocess.run(cmd, check=True, capture_output=True, timeout=180)
    shutil.rmtree(profile, ignore_errors=True)
    if not pdf_path.is_file() or pdf_path.stat().st_size < 2000:
        raise SystemExit(f"PDF non generato: {pdf_path}")
