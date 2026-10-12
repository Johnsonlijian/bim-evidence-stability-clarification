"""Data-lineage audit: compare candidate IFC models with every IFC file of a reference project tree.

A candidate matches a reference file when any of the following holds:
  * identical bytes (SHA-256),
  * identical content after line-ending normalisation (CRLF -> LF),
  * identical IfcProject GlobalId (same project, possibly a different export).

Usage:
  python -E -P lineage_audit.py index <reference_tree> <index.json>
  python -E -P lineage_audit.py check <index.json> <out_prefix> <candidate.ifc> [<candidate.ifc> ...]
"""
import hashlib
import json
import re
import sys
from pathlib import Path

PROJ = re.compile(rb"IFCPROJECT\(\s*'([0-9A-Za-z_$]{22})'\s*,[^,]*,\s*('(?:[^']|'')*'|\$)")
HDR_NAME = re.compile(rb"FILE_NAME\s*\(\s*'((?:[^']|'')*)'\s*,\s*'((?:[^']|'')*)'")
HDR_SCHEMA = re.compile(rb"FILE_SCHEMA\s*\(\s*\(\s*'([^']*)'")
HDR_SYS = re.compile(rb"FILE_NAME\s*\((?:[^;]*?),\s*'((?:[^']|'')*)'\s*,\s*'((?:[^']|'')*)'\s*,\s*'((?:[^']|'')*)'\s*\)\s*;",
                     re.S)


def describe(path: Path) -> dict:
    b = path.read_bytes()
    nb = b.replace(b"\r\n", b"\n")
    head = b[:20000]
    m = PROJ.search(b)
    hn = HDR_NAME.search(head)
    hs = HDR_SCHEMA.search(head)
    sysm = HDR_SYS.search(head)
    return {
        "path": str(path), "bytes": len(b),
        "sha256": hashlib.sha256(b).hexdigest(),
        "sha256_lf": hashlib.sha256(nb).hexdigest(),
        "project_gid": m.group(1).decode() if m else None,
        "project_name": m.group(2).decode("latin-1") if m else None,
        "header_name": hn.group(1).decode("latin-1") if hn else None,
        "header_time": hn.group(2).decode("latin-1") if hn else None,
        "schema": hs.group(1).decode("latin-1") if hs else None,
        "preprocessor": sysm.group(1).decode("latin-1") if sysm else None,
        "originating_system": sysm.group(2).decode("latin-1") if sysm else None,
    }


def cmd_index(tree: Path, out: Path):
    files = [p for p in tree.rglob("*") if p.is_file() and p.suffix.lower() == ".ifc" and ".venv" not in p.parts]
    rows = []
    for i, p in enumerate(sorted(files)):
        try:
            d = describe(p)
            d["path"] = str(p.relative_to(tree))
            rows.append(d)
        except OSError as e:
            rows.append({"path": str(p.relative_to(tree)), "error": str(e)})
        if (i + 1) % 100 == 0:
            print(f"{i + 1}/{len(files)}", flush=True)
    out.write_text(json.dumps({"tree": str(tree), "files": rows}, indent=1), encoding="utf-8")
    print(f"indexed {len(rows)} files -> {out}")


def cmd_check(index: Path, prefix: Path, cands):
    ref = json.loads(index.read_text(encoding="utf-8"))["files"]
    by = {"sha256": {}, "sha256_lf": {}, "project_gid": {}}
    for r in ref:
        for k in by:
            if r.get(k):
                by[k].setdefault(r[k], []).append(r["path"])
    res = []
    for c in cands:
        d = describe(Path(c))
        d["match_bytes"] = by["sha256"].get(d["sha256"], [])
        d["match_lf"] = by["sha256_lf"].get(d["sha256_lf"], [])
        d["match_project"] = by["project_gid"].get(d["project_gid"], []) if d["project_gid"] else []
        d["clean"] = not (d["match_bytes"] or d["match_lf"] or d["match_project"])
        res.append(d)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    Path(str(prefix) + ".json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    lines = ["| Model | Bytes | SHA-256 (first 16) | IfcProject | Schema | Originating system | Clean |",
             "|---|---:|---|---|---|---|---|"]
    for d in res:
        name = Path(d["path"]).parent.name
        lines.append(f"| {name} | {d['bytes']:,} | `{d['sha256'][:16]}` | `{d['project_gid']}` | {d['schema']} | "
                     f"{(d['originating_system'] or '')[:40]} | {'yes' if d['clean'] else 'NO: ' + '; '.join(sorted(set(d['match_bytes'] + d['match_lf'] + d['match_project'])))[:120]} |")
    Path(str(prefix) + ".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for d in res:
        print(Path(d["path"]).parent.name, "clean" if d["clean"] else "MATCH", d["project_gid"], d["schema"],
              (d["originating_system"] or "")[:50])


if __name__ == "__main__":
    if sys.argv[1] == "index":
        cmd_index(Path(sys.argv[2]), Path(sys.argv[3]))
    elif sys.argv[1] == "check":
        cmd_check(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4:])
    else:
        raise SystemExit(__doc__)
