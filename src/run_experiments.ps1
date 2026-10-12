# Experiments E1-E4 for the development (dev) and held-out (heldout) sets, pre-registered parameters.
# Usage: powershell -File run_experiments.ps1 -py <python.exe> [-sets dev,heldout] [-procs 30]
param([string]$py = "python", [string]$sets = "dev,heldout", [int]$procs = 30)
$r10 = Split-Path -Parent $PSScriptRoot
$s = Join-Path $r10 "src"
$t0 = Get-Date
foreach ($set in $sets.Split(",")) {
  $o = Join-Path $r10 ("outputs\" + $set)
  $L = Join-Path $o "ledgers"; $L50 = Join-Path $o "ledgers_w050"; $L100 = Join-Path $o "ledgers_w100"
  "[$set] E1 " + (Get-Date)
  & $py -E -P -X utf8 "$s\run_e1_audit.py" $L (Join-Path $o "e1")
  "[$set] E4 " + (Get-Date)
  & $py -E -P -X utf8 "$s\run_e4_validation.py" $L (Join-Path $o "e4\e4_rows.jsonl") US DE_DOOR
  "[$set] E2 main " + (Get-Date)
  & $py -E -P -X utf8 "$s\run_e2_acquisition.py" --ledgers $L --out (Join-Path $o "e2\e2_main.jsonl") --seeds 200 --procs $procs
  $e3 = Join-Path $o "e3"
  "[$set] E3 " + (Get-Date)
  & $py -E -P -X utf8 "$s\run_e2_acquisition.py" --ledgers $L --out "$e3\e3_cost1.5.jsonl" --seeds 100 --cost-value 1.5 --no-traj --procs $procs
  & $py -E -P -X utf8 "$s\run_e2_acquisition.py" --ledgers $L --out "$e3\e3_cost6.jsonl" --seeds 100 --cost-value 6 --no-traj --procs $procs
  & $py -E -P -X utf8 "$s\run_e2_acquisition.py" --ledgers $L --out "$e3\e3_de_door.jsonl" --seeds 100 --rulebook DE_DOOR --no-traj --procs $procs
  & $py -E -P -X utf8 "$s\run_e2_acquisition.py" --ledgers $L --out "$e3\e3_mis050.jsonl" --seeds 100 --truth-ledgers $L50 --no-traj --procs $procs
  & $py -E -P -X utf8 "$s\run_e2_acquisition.py" --ledgers $L --out "$e3\e3_mis100.jsonl" --seeds 100 --truth-ledgers $L100 --no-traj --procs $procs
  & $py -E -P -X utf8 "$s\run_e2_acquisition.py" --ledgers $L50 --out "$e3\e3_cons050.jsonl" --seeds 100 --no-traj --procs $procs
  & $py -E -P -X utf8 "$s\run_e2_acquisition.py" --ledgers $L100 --out "$e3\e3_cons100.jsonl" --seeds 100 --no-traj --procs $procs
  & $py -E -P -X utf8 "$s\run_e2_acquisition.py" --ledgers $L50 --out "$e3\e3_cons050_decl.jsonl" --seeds 100 --truth-ledgers $L --no-traj --procs $procs
  & $py -E -P -X utf8 "$s\run_e2_acquisition.py" --ledgers $L --out "$e3\e3_nogeom.jsonl" --seeds 100 --nogeom --no-traj --procs $procs
}
"ALL EXPERIMENTS DONE in " + ((Get-Date) - $t0).TotalMinutes + " min"
