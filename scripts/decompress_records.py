"""Restore compressed JSONL experiment records to the paths expected by the analysis scripts."""
from pathlib import Path
import gzip
import shutil
repo = Path(__file__).resolve().parents[1]
for src in (repo / "outputs" / "records").rglob("*.jsonl.gz"):
    rel = src.relative_to(repo / "outputs" / "records")
    dst = repo / "outputs" / rel.with_suffix("")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(src, "rb") as fsrc, dst.open("wb") as fdst:
        shutil.copyfileobj(fsrc, fdst)
    print(dst.relative_to(repo))
