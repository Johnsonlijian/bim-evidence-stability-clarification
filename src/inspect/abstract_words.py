"""Expand generated macros in the abstract and count words (CACAIE limit: 250).

Usage: python -E -P abstract_words.py <manuscript dir>
"""
import re
import sys
from pathlib import Path

m = Path(sys.argv[1])
tex = (m / "manuscript.tex").read_text(encoding="utf-8")
defs = {}
for f in m.glob("numbers*.tex"):
    for k, v in re.findall(r"\\newcommand\{\\([A-Za-z]+)\}\{(.*)\}", f.read_text(encoding="utf-8")):
        defs[k] = v
ab = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.S).group(1)
missing = set()


def rep(mo):
    k = mo.group(1)
    if k in defs:
        return defs[k]
    missing.add(k)
    return "XX"


txt = re.sub(r"\\([A-Za-z]+)\{\}", rep, ab)
txt = re.sub(r"\\([A-Za-z]+)(?![A-Za-z])", rep, txt)
txt = txt.replace("$-$", "-").replace("\\%", "%").replace("$", "").replace("~", " ").replace("--", "-")
words = re.findall(r"\S+", txt)
print(txt.strip())
print("\nwords:", len(words), " missing macros:", sorted(missing))
