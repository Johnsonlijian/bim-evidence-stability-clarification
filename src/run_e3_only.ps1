# Experiment 4 (code: E3) variants only, same parameters as run_experiments.ps1; used to resume after E2 main.
# Usage: powershell -File run_e3_only.ps1 -py <python.exe> [-set heldout] [-procs 24] [-only cost1.5,cost6,...]
param([string]$py = "python", [string]$set = "heldout", [int]$procs = 24,
      [string]$only = "cost1.5,cost6,de_door,mis050,mis100,cons050,cons100,cons050_decl,nogeom")
$r10 = Split-Path -Parent $PSScriptRoot
$s = Join-Path $r10 "src"
$o = Join-Path $r10 ("outputs\" + $set)
$L = Join-Path $o "ledgers"; $L50 = Join-Path $o "ledgers_w050"; $L100 = Join-Path $o "ledgers_w100"
$e3 = Join-Path $o "e3"
New-Item -ItemType Directory -Force $e3 | Out-Null
$variants = [ordered]@{
  "cost1.5"      = @("--ledgers", $L, "--cost-value", "1.5")
  "cost6"        = @("--ledgers", $L, "--cost-value", "6")
  "de_door"      = @("--ledgers", $L, "--rulebook", "DE_DOOR")
  "mis050"       = @("--ledgers", $L, "--truth-ledgers", $L50)
  "mis100"       = @("--ledgers", $L, "--truth-ledgers", $L100)
  "cons050"      = @("--ledgers", $L50)
  "cons100"      = @("--ledgers", $L100)
  "cons050_decl" = @("--ledgers", $L50, "--truth-ledgers", $L)
  "nogeom"       = @("--ledgers", $L, "--nogeom")
}
$want = $only.Split(",")
$t0 = Get-Date
"[$set] E3 " + (Get-Date)
foreach ($k in $variants.Keys) {
  if ($want -notcontains $k) { continue }
  "[$set] E3 $k " + (Get-Date)
  $argv = $variants[$k] + @("--out", "$e3\e3_$k.jsonl", "--seeds", "100", "--no-traj", "--procs", "$procs")
  & $py -E -P -X utf8 "$s\run_e2_acquisition.py" @argv
}
"E3 DONE in " + ((Get-Date) - $t0).TotalMinutes + " min"
