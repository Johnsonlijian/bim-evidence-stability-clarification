"""List macros used in the manuscript that numbers*.tex does not define (and vice versa for reference)."""
import re
import sys
from pathlib import Path

m = Path(sys.argv[1])
tex = (m / "manuscript.tex").read_text(encoding="utf-8")
defined = set()
for f in m.glob("numbers*.tex"):
    defined |= set(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}", f.read_text(encoding="utf-8")))
used = set(re.findall(r"\\((?:Eone|Etwo|Ethree|Efour|N|Rt|Dlg)[A-Z][A-Za-z]*)", tex))
missing = sorted(u for u in used if u not in defined)
print(f"used {len(used)} generated macros; missing {len(missing)}:")
for u in missing:
    print("  ", u)
