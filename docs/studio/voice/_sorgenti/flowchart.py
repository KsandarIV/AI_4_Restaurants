"""Flowchart verticale di tutto il flusso del codice (avvio -> chiamata -> chiusura), in SVG puro.

Forme standard: terminatore (ovale), processo (rettangolo), decisione (rombo), ingresso/uscita (parallelogramma),
sottoprocesso (rettangolo con bordi doppi). Genera ../flowchart_flusso_codice.svg e ../05_flowchart_verticale.pdf.
"""

from __future__ import annotations

import html
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lib import BROWN, DARK, GOLD, GREEN, INK, LINE, MUTED, RED, to_pdf  # noqa: E402

W = 1520
LANE_L, LANE_R = 22, 1498
COL = {"l": 250, "c": 760, "r": 1270}
NODE_W = {"term": 400, "proc": 400, "io": 400, "sub": 600, "dec": 440}
STYLE = {  # fill, stroke, text colour
    "term": (BROWN, BROWN, "#fff"), "proc": ("#fff", BROWN, INK), "dec": ("#fff7ec", GOLD, INK),
    "io": ("#fdecea", RED, INK), "sub": ("#e3f3e8", GREEN, INK), "note": ("#f4ece0", MUTED, INK)}


class Node:
    def __init__(self, nid: str, kind: str, text: str, cx: float, cy: float) -> None:
        self.id, self.kind, self.text, self.cx, self.cy = nid, kind, text, cx, cy
        lines = text.count("\n") + 1
        self.w = NODE_W.get(kind, 400)
        self.h = max(70 if kind != "dec" else 112, lines * 21 + (30 if kind != "dec" else 52))

    def anchor(self, side: str) -> tuple[float, float]:
        return {"t": (self.cx, self.cy - self.h / 2), "b": (self.cx, self.cy + self.h / 2),
                "l": (self.cx - self.w / 2, self.cy), "r": (self.cx + self.w / 2, self.cy)}[side]


class Flow:
    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.parts: list[str] = []
        self.edges: list[str] = []
        self.y = 20.0

    # ------------------------------------------------------------ nodes
    def band(self, title: str, color: str = DARK) -> None:
        self.parts.append(f'<rect x="0" y="{self.y}" width="{W}" height="46" fill="{color}"/>'
                          f'<text x="24" y="{self.y + 30}" font-size="22" font-weight="700" fill="#fff">{html.escape(title)}</text>')
        self.y += 46 + 40

    def place(self, nid: str, kind: str, text: str, col: str = "c", gap: float = 44) -> Node:
        n = Node(nid, kind, text, COL[col], 0)
        n.cy = self.y + n.h / 2
        self.y += n.h + gap
        self._add(n)
        return n

    def side(self, nid: str, kind: str, text: str, ref: str, col: str = "r") -> Node:
        n = Node(nid, kind, text, COL[col], self.nodes[ref].cy)
        self._add(n)
        return n

    def _add(self, n: Node) -> None:
        self.nodes[n.id] = n
        fill, stroke, tcol = STYLE[n.kind]
        x, y, w, h = n.cx - n.w / 2, n.cy - n.h / 2, n.w, n.h
        if n.kind == "term":
            shape = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h / 2}" fill="{fill}" stroke="{stroke}" stroke-width="2.5"/>'
        elif n.kind == "dec":
            pts = f"{n.cx},{y} {x + w},{n.cy} {n.cx},{y + h} {x},{n.cy}"
            shape = f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="2.5"/>'
        elif n.kind == "io":
            pts = f"{x + 24},{y} {x + w},{y} {x + w - 24},{y + h} {x},{y + h}"
            shape = f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="2.5"/>'
        elif n.kind == "sub":
            shape = (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="2.5"/>'
                     f'<line x1="{x + 16}" y1="{y}" x2="{x + 16}" y2="{y + h}" stroke="{stroke}" stroke-width="2"/>'
                     f'<line x1="{x + w - 16}" y1="{y}" x2="{x + w - 16}" y2="{y + h}" stroke="{stroke}" stroke-width="2"/>')
        else:
            shape = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="2.5"/>'
        lines = n.text.split("\n")
        top = n.cy - (len(lines) - 1) * 10.5 + 5
        txt = [f'<text x="{n.cx}" y="{top}" font-size="16" font-weight="600" text-anchor="middle" fill="{tcol}">']
        for i, ln in enumerate(lines):
            txt.append(f'<tspan x="{n.cx}" dy="{0 if i == 0 else 21}">{html.escape(ln)}</tspan>')
        txt.append("</text>")
        self.parts.append(shape + "".join(txt))

    # ------------------------------------------------------------ edges
    def edge(self, a: str, a_side: str, b: str, b_side: str, via: list[tuple[float, float]] | None = None,
             label: str = "", lpos: tuple[float, float] | None = None, color: str = BROWN, dash: bool = False) -> None:
        pts = [self.nodes[a].anchor(a_side)] + (via or []) + [self.nodes[b].anchor(b_side)]
        d = " ".join(f"{x},{y}" for x, y in pts)
        dash_attr = ' stroke-dasharray="7 6"' if dash else ""
        self.edges.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="2.4"{dash_attr} marker-end="url(#arr)"/>')
        if label:
            lx, ly = lpos if lpos else (pts[0][0] + 14, pts[0][1] + 16)
            self.edges.append(f'<text x="{lx}" y="{ly}" font-size="16" font-weight="700" fill="{color}" '
                              f'stroke="#fffaf3" stroke-width="5" paint-order="stroke">{html.escape(label)}</text>')

    # ------------------------------------------------------------ on-page connectors (circles with a letter)
    def circle(self, letter: str, x: float, y: float, color: str = RED) -> None:
        self.parts.append(f'<circle cx="{x}" cy="{y}" r="17" fill="#fff" stroke="{color}" stroke-width="2.6"/>'
                          f'<text x="{x}" y="{y + 6}" font-size="17" font-weight="800" text-anchor="middle" fill="{color}">{letter}</text>')

    def arrow_pts(self, pts: list[tuple[float, float]], color: str = BROWN, label: str = "", lpos: tuple[float, float] | None = None) -> None:
        d = " ".join(f"{x},{y}" for x, y in pts)
        self.edges.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="2.4" marker-end="url(#arr)"/>')
        if label:
            lx, ly = lpos if lpos else (pts[0][0] + 8, pts[0][1] - 10)
            self.edges.append(f'<text x="{lx}" y="{ly}" font-size="16" font-weight="700" fill="{color}" '
                              f'stroke="#fffaf3" stroke-width="5" paint-order="stroke">{html.escape(label)}</text>')

    def exit_left(self, src: str, letter: str, label: str = "") -> None:
        n = self.nodes[src]
        x0, y = n.cx - n.w / 2, n.cy
        self.arrow_pts([(x0, y), (x0 - 62, y)], RED, label, (x0 - 56, y - 10))
        self.circle(letter, x0 - 82, y)

    def exit_below(self, src: str, letter: str) -> None:
        n = self.nodes[src]
        y0 = n.cy + n.h / 2
        self.arrow_pts([(n.cx, y0), (n.cx, y0 + 22)], RED)
        self.circle(letter, n.cx, y0 + 38)

    def entry_left(self, dst: str, letter: str) -> None:
        n = self.nodes[dst]
        x0, y = n.cx - n.w / 2, n.cy
        self.circle(letter, x0 - 82, y)
        self.arrow_pts([(x0 - 64, y), (x0, y)], RED)

    def down(self, a: str, b: str, label: str = "") -> None:
        self.edge(a, "b", b, "t", label=label)

    def svg(self) -> str:
        h = int(self.y + 20)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" font-family="Segoe UI, system-ui, Arial, sans-serif">'
                f'<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" markerHeight="9" orient="auto">'
                f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{BROWN}"/></marker></defs>'
                f'<rect width="{W}" height="{h}" fill="#fffaf3"/>' + "".join(self.parts) + "".join(self.edges) + "</svg>")


def build_flow() -> Flow:
    f = Flow()
    f.parts.append(f'<text x="24" y="{f.y + 26}" font-size="30" font-weight="700" fill="{DARK}" font-family="Georgia, serif">'
                   'Flowchart del flusso del codice · AI 4 Restaurants (VOICE)</text>')
    f.parts.append(f'<text x="24" y="{f.y + 54}" font-size="16" fill="{MUTED}">'
                   'Ovale = inizio/fine · rettangolo = azione · rombo = decisione · parallelogramma = ingresso/uscita (rete, audio) · '
                   'doppio bordo = sottoprocesso nel BE</text>')
    f.y += 86

    # ================================================================ 1 AVVIO
    f.band("1 · AVVIO DI UNA MACCHINA   (entrypoint/avvia.py)")
    f.place("s", "term", "python entrypoint\\avvia.py\n[--role be|chat|voice]")
    f.place("git", "proc", "1 · git pull --ff-only\n(codice aggiornato, mai merge sporchi)")
    d1 = f.place("d1", "dec", "pull riuscito?")
    f.side("stop", "term", "STOP: risolvi a mano\n(git status, non forzare)", "d1")
    f.place("idn", "proc", "2 · Identità della macchina\nruolo + IP rilevato → lan/macchina.json")
    d2 = f.place("d2", "dec", "venv pronto per il ruolo?\n(hash dei requisiti uguali)")
    f.side("inst", "proc", "3 · setup_env.py\ninstalla pacchetti per ruolo,\neditable, modelli, scrive stato", "d2")
    f.place("env", "proc", "4 · .env di macchina\nBACKEND_BASE_URL=http://IP-BE:8000")
    f.place("fw", "proc", "5 · Firewall: regola TCP\nper le porte del ruolo")
    d3 = f.place("d3", "dec", "ruolo = chat o voice?")
    f.place("gate", "dec", "6 · il BE risponde a\nGET /api/health?")
    f.side("wait", "proc", "attende 2 s e riprova\n(al massimo 180 s)", "gate")
    f.place("run", "proc", "7 · Avvio del componente (log live)\nBE: python -m backend.main\nCHAT: streamlit :8501 + uvicorn :8002\nVOICE: python -m voicebot")
    # edges
    f.down("s", "git"); f.down("git", "d1"); f.edge("d1", "r", "stop", "l", label="no", lpos=(1030, f.nodes["d1"].cy - 10))
    f.down("d1", "idn", "sì"); f.down("idn", "d2")
    f.edge("d2", "r", "inst", "l", label="no", lpos=(1030, f.nodes["d2"].cy - 10))
    f.down("d2", "env", "sì")
    f.edge("inst", "b", "env", "r", via=[(COL["r"], f.nodes["env"].cy)])
    f.down("env", "fw"); f.down("fw", "d3")
    f.edge("d3", "b", "gate", "t", label="sì", lpos=(724, f.nodes["d3"].cy + 78))
    f.edge("d3", "l", "run", "l", via=[(480, f.nodes["d3"].cy), (480, f.nodes["run"].cy)], label="no (BE)", lpos=(380, f.nodes["d3"].cy - 10))
    f.edge("gate", "r", "wait", "l", label="no", lpos=(1030, f.nodes["gate"].cy - 10))
    f.exit_below("wait", "C")
    f.entry_left("gate", "C")
    f.down("gate", "run", "sì")

    # ================================================================ 2 PREPARAZIONE
    f.band("2 · IL BE E IL VOICE SI PREPARANO")
    f.place("be", "proc", "BE (macchina BE): init_db + dati iniziali\nscelta del modello Ollama con strumenti\nwarm-up del modello in un thread")
    f.place("vp", "proc", "VOICE (macchina VOICE): uvicorn :8003\ncarica in background Whisper small + Piper\n(PRELOAD_MODELS)")
    f.place("wu", "io", "VOICE → BE: turno finto «Buongiorno»\ncon anon_voice (WARM_BACKEND):\nil LLM legge il prompt una volta")
    f.place("rdy", "term", "Pronti: sito / · pagina /test-voice\nWebSocket /ws/voice")
    f.edge("run", "b", "be", "t", via=[(COL["c"], f.nodes["run"].cy + f.nodes["run"].h / 2 + 22)])
    f.down("be", "vp"); f.down("vp", "wu"); f.down("wu", "rdy")

    # ================================================================ 3 CHIAMATA
    f.band("3 · UNA CHIAMATA   (pipeline/session.py + orchestrator.py + BE)")
    f.place("c0", "term", "Il cliente tocca «Prenota a voce»\n(il pulsante diventa l'orb)")
    f.place("ws", "io", "Browser: microfono 16 kHz\n→ WebSocket /ws/voice")
    d5 = f.place("d5", "dec", "modelli STT/TTS pronti?")
    f.side("load", "proc", "evento loading:\nattende (max 120 s)", "d5")
    f.place("hi", "proc", "evento ready + saluto breve\n«Come posso aiutarla?» (Piper)", gap=70)
    lp = f.place("listen", "io", "ASCOLTO: audio PCM → VAD\n(blocchi da 128 ms / frame da 20 ms)")
    d6 = f.place("d6", "dec", "voce ≥ 250 ms e poi\npausa ≥ 600 ms?")
    d7 = f.place("d7", "dec", "il bot stava parlando e la voce\ndura ≥ 300 ms? (barge-in)")
    f.side("barge", "proc", "annulla il turno, svuota l'audio\nin coda, evento barge_in", "d7")
    f.place("stt", "proc", "STT faster-whisper small\nutterance → testo")
    d8 = f.place("d8", "dec", "testo vuoto o\n«allucinazione»?")
    d9 = f.place("d9", "dec", "fase REGISTRAZIONE\nin corso?")
    r1 = f.side("r1", "proc", "contacts: estrae nome e telefono\n(cifre a parole, validati E.164)", "d9")
    d10 = f.place("d10", "dec", "non registrato e parla\ndi prenotare? (wants_booking)")
    f.side("r2", "proc", "avvia la registrazione:\n«Mi dice il suo nome e un\nnumero di telefono?»", "d10")
    d11 = f.place("d11", "dec", "c'è un referto in attesa\ndel «sì» finale?")
    f.side("r3", "proc", "«sì» breve → popup si chiude dopo 4 s\n«no» → chiede cosa cambiare\naltro → prosegue verso il BE", "d11")
    d12 = f.place("d12", "dec", "contesto pieno?\n(≥ 20 scambi senza prenotare)")
    f.side("r4", "proc", "nuova sessione BE + recap parlato\n3° volta: avviso · 4° volta: fine chiamata", "d12")
    f.place("anon", "proc", "Anonimizza: regex + spaCy\n→ [NOME_1], [TELEFONO_1]")
    f.place("post", "io", "POST /api/chat/stream\nmessage + session_id + customer_id")
    f.place("be2", "sub", "BE · process_message()\n1 proposta in attesa + «sì» → esegue lo strumento\n2 allergie → risposta scritta dal codice\n3 altrimenti LLM + strumenti (LangGraph)\n4 create/modify/cancel → riepilogo «Confermi?»")
    f.place("sse", "proc", "Token SSE, parola per parola\nla prima frase (≥ 40 caratteri) è trattenuta")
    d13 = f.place("d13", "dec", "parla di strumenti, chiede un\npermesso inutile o «offre» senza dare?")
    f.side("tg", "proc", "toolguard: scarta e riprova 1 volta\ncon NUDGE; se ancora sì → frase neutra", "d13")
    f.place("rest", "proc", "Ripristina i segnaposto\n(mai mezzo segnaposto detto a voce)")
    f.place("tts", "proc", "TTS Piper frase per frase\nspeakable(): codici «R E S, 9 A 8 B…»")
    f.place("out", "io", "Audio PCM → WebSocket → browser\n+ eventi reply · reservation · …")
    d14 = f.place("d14", "dec", "la risposta contiene\nun codice RES-…?")
    f.place("rep", "io", "GET /api/reservations/{codice}\n(solo il proprietario)")
    f.place("rep2", "proc", "Referto detto dal codice (non dall'LLM)\nevento reservation → popup riepilogo\ncontatori del contesto a zero")
    d15 = f.place("d15", "dec", "fine chiamata?\n(call_ended · orb · inattività 60 s)")
    f.place("end", "term", "Chiusura: il pulsante torna\n«Prenota a voce»", gap=30)

    # main chain (A = torna ad ascoltare · B = prosegue verso il BE con la richiesta ripetuta · D = attende i modelli)
    f.down("c0", "ws"); f.down("ws", "d5")
    f.edge("d5", "r", "load", "l", label="no", lpos=(1030, f.nodes["d5"].cy - 10))
    f.exit_below("load", "D")
    f.entry_left("d5", "D")
    f.down("d5", "hi", "sì"); f.down("hi", "listen"); f.down("listen", "d6")
    f.entry_left("listen", "A")
    f.exit_left("d6", "A", "no")
    f.down("d6", "d7", "sì")
    f.edge("d7", "r", "barge", "l", label="sì", lpos=(1030, f.nodes["d7"].cy - 10))
    f.edge("barge", "b", "stt", "r", via=[(COL["r"], f.nodes["stt"].cy)])
    f.down("d7", "stt", "no")
    f.down("stt", "d8")
    f.exit_left("d8", "A", "sì")
    f.down("d8", "d9", "no")
    f.edge("d9", "r", "r1", "l", label="sì", lpos=(1030, f.nodes["d9"].cy - 10))
    r1n = f.nodes["r1"]
    y0 = r1n.cy + r1n.h / 2
    f.arrow_pts([(r1n.cx - 110, y0), (r1n.cx - 110, y0 + 22)], RED)
    f.circle("A", r1n.cx - 110, y0 + 38)
    f.parts.append(f'<text x="{r1n.cx - 134}" y="{y0 + 44}" font-size="15" font-weight="700" fill="{RED}" text-anchor="end">dati mancanti</text>')
    f.arrow_pts([(r1n.cx + 110, y0), (r1n.cx + 110, y0 + 22)], GREEN)
    f.circle("B", r1n.cx + 110, y0 + 38, GREEN)
    f.parts.append(f'<text x="{r1n.cx + 134}" y="{y0 + 44}" font-size="15" font-weight="700" fill="{GREEN}" text-anchor="start">confermati</text>')
    f.down("d9", "d10", "no")
    f.edge("d10", "r", "r2", "l", label="sì", lpos=(1030, f.nodes["d10"].cy - 10))
    f.exit_below("r2", "A")
    f.down("d10", "d11", "no")
    f.edge("d11", "r", "r3", "l", label="sì", lpos=(1030, f.nodes["d11"].cy - 10))
    f.exit_below("r3", "A")
    f.down("d11", "d12", "no")
    f.edge("d12", "r", "r4", "l", label="sì", lpos=(1030, f.nodes["d12"].cy - 10))
    f.exit_below("r4", "A")
    f.down("d12", "anon", "no")
    f.down("anon", "post")
    f.entry_left("post", "B")
    f.down("post", "be2"); f.down("be2", "sse"); f.down("sse", "d13")
    f.edge("d13", "r", "tg", "l", label="sì", lpos=(1030, f.nodes["d13"].cy - 10))
    f.edge("tg", "b", "rest", "r", via=[(COL["r"], f.nodes["rest"].cy)])
    f.down("d13", "rest", "no")
    f.down("rest", "tts"); f.down("tts", "out"); f.down("out", "d14")
    f.exit_left("d14", "A", "no")
    f.down("d14", "rep", "sì"); f.down("rep", "rep2"); f.down("rep2", "d15")
    f.exit_left("d15", "A", "no")
    f.down("d15", "end", "sì")
    return f


def main() -> None:
    here = pathlib.Path(__file__).resolve().parent
    out = here.parent
    flow = build_flow()
    svg = flow.svg()
    (out / "flowchart_flusso_codice.svg").write_text(svg, encoding="utf-8")
    h = int(flow.y + 20)
    page = (f'<!doctype html><html><head><meta charset="utf-8"><style>@page{{size:{W}px {h}px;margin:0}}'
            f'html,body{{margin:0;padding:0;background:#fffaf3}}svg{{display:block}}</style></head><body>{svg}</body></html>')
    html_path = here / "05_flowchart_verticale.html"
    html_path.write_text(page, encoding="utf-8")
    to_pdf(html_path, out / "05_flowchart_verticale.pdf")
    print(f"ok flowchart {W}x{h}px, {len(flow.nodes)} nodi")


if __name__ == "__main__":
    main()
