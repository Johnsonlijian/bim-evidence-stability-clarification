"""Fetch the four pre-registered IFC-Bench v2 development models.

Raw IFC files are downloaded to data/external and are intentionally not included in this repository.
Check each model card and license before use or redistribution.
"""
import hashlib, json, sys, time, urllib.request
from pathlib import Path
BASE = "https://huggingface.co/datasets/sylvainHellin/ifc-bench/resolve/main/projects"
PROJECTS = ("city_house_munich", "duplex", "fantasy_office_building_1", "wbdg_office")
def fetch(url, dest):
    tmp = dest.with_suffix(dest.suffix + ".part")
    h = hashlib.sha256(); n = 0
    req = urllib.request.Request(url, headers={"User-Agent": "R10-study/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, tmp.open("wb") as fh:
        while True:
            chunk = r.read(1 << 20)
            if not chunk: break
            fh.write(chunk); h.update(chunk); n += len(chunk)
    tmp.replace(dest); return n, h.hexdigest()
def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "data/external/ifc-bench-v2")
    rows = []
    for project in PROJECTS:
        d = root / "projects" / project; d.mkdir(parents=True, exist_ok=True)
        for remote, local in (("model_card.md", "model_card.md"), ("license.txt", "license.txt"), ("arc.ifc", "arc.ifc")):
            dest = d / local; n, sha = fetch(f"{BASE}/{project}/{remote}?download=true", dest)
            rows.append({"project": project, "remote_file": remote, "local_file": str(dest.relative_to(root)), "bytes": n, "sha256": sha, "url": f"{BASE}/{project}/{remote}", "retrieved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            print(f"{project}/{remote}: {n:,} bytes")
    (root / "manifest_development.json").write_text(json.dumps({"dataset": "sylvainHellin/ifc-bench (v2)", "files": rows}, indent=1), encoding="utf-8")
if __name__ == "__main__": main()
