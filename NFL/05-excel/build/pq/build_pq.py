"""Assemble 05-excel/powerquery/*.pq from templates plus shared snippets.

The data-location resolver (snippets/resolver.m) and the season window (snippets/window.m) must be
byte-identical in every query that reads published CSVs (firewall rule D-009 forbids sharing them through
another query). Edit the snippet or a template here, then run (from the NFL folder):  python3 05-excel/build/pq/build_pq.py
Never edit the generated .pq files by hand.
"""
import pathlib, sys
here = pathlib.Path(__file__).resolve().parent
out = here.parents[1] / "powerquery"
res = (here / "snippets/resolver.m").read_text(encoding="utf-8").rstrip("\n")
win = (here / "snippets/window.m").read_text(encoding="utf-8").rstrip("\n")
for t in sorted((here / "templates").glob("*.pq")):
    s = t.read_text(encoding="utf-8")
    s = s.replace("//@@RESOLVER@@", res).replace("//@@WINDOW@@", win)
    assert "@@" not in s, t.name
    (out / t.name).write_text(s if s.endswith("\n") else s + "\n", encoding="utf-8")
    print("wrote", t.name, "resolver" if res in s else "", "window" if win in s else "")
