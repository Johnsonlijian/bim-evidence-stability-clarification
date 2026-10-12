"""Experiments 2-3: evidence acquisition under hidden states drawn from a full-information version space.

Usage (examples)
  python -E -P run_e2_acquisition.py --ledgers ../outputs/ledgers --out ../outputs/e2/e2_main.jsonl --seeds 200
  python -E -P run_e2_acquisition.py ... --cost-value 6 --tag cost6
  python -E -P run_e2_acquisition.py ... --truth-ledgers ../outputs/ledgers_w050 --tag mis050
  python -E -P run_e2_acquisition.py ... --nogeom --tag nogeom
Each task = (project, seed): one hidden state, evaluated at evidence levels min/std/full for all policies.
"""
import argparse
import json
import sys
import time
import zlib
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

from bimev import catalog as C  # noqa: E402
from bimev.engine import build_clusters  # noqa: E402
from bimev.planner import run_complete, run_naive, run_oracle, run_policy, sample_truth  # noqa: E402

ALL_POLICIES = ["value", "random", "fixed", "degree", "ec2", "sv", "conf"]
TRAJ_POLICIES = {"value", "random", "fixed", "degree", "ec2", "sv"}
_CACHE = {}


def _load(path):
    if path not in _CACHE:
        _CACHE[path] = json.loads(Path(path).read_text(encoding="utf-8"))
    return _CACHE[path]


def _compact(traj):
    return [[round(c, 2), round(f, 4), round(fw, 4)] for c, f, fw in traj]


def task(args):
    (led_dir, truth_dir, proj, seed, rulebook, costs, taus, policies, levels, nogeom, oracle, keep_traj) = args
    L = _load(str(Path(led_dir) / f"ledger_{proj}.json"))
    LT = _load(str(Path(truth_dir) / f"ledger_{proj}.json")) if truth_dir else L
    base = zlib.crc32(f"{proj}|{seed}".encode()) & 0x7FFFFFFF
    rng = np.random.default_rng(base)
    full = build_clusters(LT, "full", rulebook)
    tv, tq = sample_truth(full, rng)
    out = []
    for level in levels:
        row = {"project": proj, "seed": seed, "level": level, "rulebook": rulebook, "costs": costs,
               "truth": "declared" if not truth_dir else Path(truth_dir).name, "nogeom": nogeom}
        out.append({**row, "policy": "naive", **run_naive(L, level, rulebook, tv, tq, drop_geometry=nogeom)})
        out.append({**row, "policy": "complete",
                    **run_complete(L, level, rulebook, tv, tq, costs=costs, drop_geometry=nogeom)})
        for pol in policies:
            for tau in (taus if pol == "conf" else [None]):
                t0 = time.time()
                s, traj, _ = run_policy(L, level, rulebook, tv, tq, pol, np.random.default_rng(base + 17),
                                        costs=costs, tau=tau, drop_geometry=nogeom)
                name = pol if tau is None else f"conf{tau}"
                out.append({**row, "policy": name, **s, "secs": round(time.time() - t0, 3),
                            "traj": _compact(traj) if (keep_traj and pol in TRAJ_POLICIES) else None})
        if oracle:
            t0 = time.time()
            o = run_oracle(L, level, rulebook, tv, tq, costs=costs, drop_geometry=nogeom)
            out.append({**row, "policy": "oracle", **o, "secs": round(time.time() - t0, 3)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledgers", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--procs", type=int, default=24)
    ap.add_argument("--rulebook", default="US")
    ap.add_argument("--cost-value", type=float, default=C.COST["VALUE"])
    ap.add_argument("--cost-clarify", type=float, default=C.COST["CLARIFY"])
    ap.add_argument("--truth-ledgers", default=None)
    ap.add_argument("--nogeom", action="store_true")
    ap.add_argument("--policies", default=",".join(ALL_POLICIES))
    ap.add_argument("--levels", default="min,std,full")
    ap.add_argument("--no-oracle", action="store_true")
    ap.add_argument("--no-traj", action="store_true")
    a = ap.parse_args()
    costs = {"CLARIFY": a.cost_clarify, "VALUE": a.cost_value}
    taus = [0.8, 0.9, 0.95, 0.99]
    projects = sorted(p.stem.replace("ledger_", "") for p in Path(a.ledgers).glob("ledger_*.json"))
    tasks = [(a.ledgers, a.truth_ledgers, p, s, a.rulebook, costs, taus, a.policies.split(","),
              a.levels.split(","), a.nogeom, not a.no_oracle, not a.no_traj)
             for s in range(a.seeds) for p in projects]
    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    done = 0
    with out_path.open("w", encoding="utf-8") as fh, Pool(a.procs) as pool:
        for res in pool.imap_unordered(task, tasks, chunksize=1):
            for r in res:
                fh.write(json.dumps(r) + "\n")
            done += 1
            if done % 200 == 0 or done == len(tasks):
                print(f"{done}/{len(tasks)} tasks  {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
