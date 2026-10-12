from pathlib import Path
import gzip
import shutil
import subprocess
import sys

repo = Path(__file__).resolve().parents[1]
py = sys.executable
restored = []
for src in (repo / "outputs" / "records").rglob("*.jsonl.gz"):
    rel = src.relative_to(repo / "outputs" / "records")
    dst = repo / "outputs" / rel.with_suffix("")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        raise RuntimeError(f"refusing to overwrite existing record: {dst}")
    with gzip.open(src, "rb") as fsrc, dst.open("wb") as fdst:
        shutil.copyfileobj(fsrc, fdst)
    restored.append(dst)

man = repo / "manuscript"
man.mkdir(exist_ok=True)
try:
    subprocess.run([py, "-E", "-P", str(repo / "src" / "make_results.py"), str(repo)], check=True)
    subprocess.run([py, "-E", "-P", str(repo / "src" / "make_dialogue.py"), str(repo), "10"], check=True)
    subprocess.run([py, "-E", "-P", str(repo / "src" / "make_figures.py"), str(repo)], check=True)
    out = repo / "outputs" / "generated_numbers"
    out.mkdir(parents=True, exist_ok=True)
    for p in man.glob("numbers*.tex"):
        shutil.copy2(p, out / p.name)
finally:
    for dst in restored:
        dst.unlink(missing_ok=True)
    shutil.rmtree(man, ignore_errors=True)
