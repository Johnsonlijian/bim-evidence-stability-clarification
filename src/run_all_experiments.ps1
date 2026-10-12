# Runs Experiments 1-3 end to end (Windows PowerShell). Usage: powershell -File run_all_experiments.ps1 <python.exe>
param([string]$py = "python")
$r9 = Split-Path -Parent $PSScriptRoot
$proj = Split-Path -Parent $r9
$src = Join-Path $proj "data\external\ifc-bench-v2"
$s = Join-Path $r9 "src"
$o = Join-Path $r9 "outputs"
$t0 = Get-Date
& $py -E -P -X utf8 "$s\run_extract.py" $src "$o\ledgers"
& $py -E -P -X utf8 "$s\run_extract.py" $src "$o\ledgers_w050" 0.5
& $py -E -P -X utf8 "$s\run_extract.py" $src "$o\ledgers_w100" 1.0
& $py -E -P -X utf8 "$s\run_e1_audit.py" "$o\ledgers" "$o\e1"
& $py -E -P -X utf8 "$s\run_e2_acquisition.py" --ledgers "$o\ledgers" --out "$o\e2\e2_main.jsonl" --seeds 200
& $py -E -P -X utf8 "$s\run_e2_acquisition.py" --ledgers "$o\ledgers" --out "$o\e3\e3_cost1.5.jsonl" --seeds 100 --cost-value 1.5 --no-traj
& $py -E -P -X utf8 "$s\run_e2_acquisition.py" --ledgers "$o\ledgers" --out "$o\e3\e3_cost6.jsonl" --seeds 100 --cost-value 6 --no-traj
& $py -E -P -X utf8 "$s\run_e2_acquisition.py" --ledgers "$o\ledgers" --out "$o\e3\e3_de_door.jsonl" --seeds 100 --rulebook DE_DOOR --no-traj
& $py -E -P -X utf8 "$s\run_e2_acquisition.py" --ledgers "$o\ledgers" --out "$o\e3\e3_mis050.jsonl" --seeds 100 --truth-ledgers "$o\ledgers_w050" --no-traj
& $py -E -P -X utf8 "$s\run_e2_acquisition.py" --ledgers "$o\ledgers" --out "$o\e3\e3_mis100.jsonl" --seeds 100 --truth-ledgers "$o\ledgers_w100" --no-traj
& $py -E -P -X utf8 "$s\run_e2_acquisition.py" --ledgers "$o\ledgers" --out "$o\e3\e3_nogeom.jsonl" --seeds 100 --nogeom --no-traj
# conservative catalogue: the planner itself uses the widened catalogue (truth from the same or from the declared one)
& $py -E -P -X utf8 "$s\run_e2_acquisition.py" --ledgers "$o\ledgers_w050" --out "$o\e3\e3_cons050.jsonl" --seeds 100 --no-traj
& $py -E -P -X utf8 "$s\run_e2_acquisition.py" --ledgers "$o\ledgers_w100" --out "$o\e3\e3_cons100.jsonl" --seeds 100 --no-traj
& $py -E -P -X utf8 "$s\run_e2_acquisition.py" --ledgers "$o\ledgers_w050" --out "$o\e3\e3_cons050_decl.jsonl" --seeds 100 --truth-ledgers "$o\ledgers" --no-traj
"ALL DONE in " + ((Get-Date) - $t0).TotalMinutes + " min"
