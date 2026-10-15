"""Genera MANUALE_TECNICO.md dal sorgente manuale_src.md, costruendo l'indice dai titoli (## e ###)."""
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
src = (HERE / "manuale_src.md").read_text(encoding="utf-8")


def slug(title: str) -> str:
    """Stessa regola degli anchor di GitHub: minuscolo, via la punteggiatura, spazi -> trattini."""
    t = re.sub(r"[^\w\- ]", "", title.strip().lower())
    return t.replace(" ", "-")


toc = ["## Indice", ""]
in_code = False
for line in src.splitlines():
    if line.startswith("```"):
        in_code = not in_code
        continue
    if in_code:
        continue
    m = re.match(r"^(##|###) (.+)$", line)
    if not m or m.group(2).strip() == "Indice":
        continue
    level, title = m.groups()
    indent = "" if level == "##" else "    "
    toc.append(f"{indent}- [{title}](#{slug(title)})")
out = src.replace("{{TOC}}", "\n".join(toc))
(HERE.parent / "MANUALE_TECNICO.md").write_text(out, encoding="utf-8")
print("ok MANUALE_TECNICO.md", len(out.splitlines()), "righe")
