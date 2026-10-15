"""Genera i PDF delle mini presentazioni in docs/studio/voice (da lanciare dalla cartella _sorgenti)."""
import importlib
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent
sys.path.insert(0, str(HERE))

DECKS = ["deck01_stack", "deck02_flusso", "deck03_storia", "deck04_be"]

for name in (sys.argv[1:] or DECKS):
    if not (HERE / f"{name}.py").exists():
        print("manca", name)
        continue
    deck = importlib.import_module(name).build()
    pdf = deck.build(OUT, HERE)
    print("ok", pdf.name, f"{pdf.stat().st_size // 1024} KB", f"{len(deck.slides)} slide")

# PDF unico con tutte le slide, nell'ordine dei mini-deck
if not sys.argv[1:]:
    from lib import Deck, to_pdf

    all_deck = Deck("Voice · presentazione completa", "00_presentazione_completa")
    for name in DECKS:
        all_deck.slides += importlib.import_module(name).build().slides
    html_path = HERE / "00_presentazione_completa.html"
    html_path.write_text(all_deck.html(), encoding="utf-8")
    to_pdf(html_path, OUT / "00_presentazione_completa.pdf")
    print("ok 00_presentazione_completa.pdf", len(all_deck.slides), "slide")

# flowchart verticale (SVG + PDF) e manuale con indice
if not sys.argv[1:]:
    import flowchart
    import gen_manual  # noqa: F401  (genera MANUALE_TECNICO.md all'import)

    flowchart.main()
