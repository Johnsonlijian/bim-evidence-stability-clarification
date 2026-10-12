# Extract ledgers for the development (D) and held-out (H) sets, declared and widened catalogues, in parallel.
# Usage: powershell -File run_extract_all.ps1 -py <python.exe>
param([string]$py = "python")
$r10 = Split-Path -Parent $PSScriptRoot
$base = Split-Path -Parent $r10
$s = Join-Path $r10 "src"
$o = Join-Path $r10 "outputs"
$sets = @(
  @{ name = "dev"; root = (Join-Path $base "data\external\ifc-bench-v2");
     projects = @("city_house_munich", "duplex", "fantasy_office_building_1", "wbdg_office") },
  @{ name = "heldout"; root = (Join-Path $base "data\external\ifc-bench-v2-heldout");
     projects = @("fantasy_hotel_1", "fantasy_hotel_2", "fantasy_office_building_2", "fantasy_office_building_3",
                  "fantasy_residential_building_1", "hitos", "molio", "sixty5", "west_riverside_hospital") }
)
$variants = @(@{ dir = "ledgers"; w = "0" }, @{ dir = "ledgers_w050"; w = "0.5" }, @{ dir = "ledgers_w100"; w = "1.0" })
$logs = Join-Path $o "extract_logs"
New-Item -ItemType Directory -Force $logs | Out-Null
$procs = @()
foreach ($set in $sets) {
  foreach ($p in $set.projects) {
    foreach ($v in $variants) {
      $out = Join-Path $o (Join-Path $set.name $v.dir)
      $args = @("-E", "-P", "-X", "utf8", (Join-Path $s "run_extract.py"), "--root", $set.root, "--out", $out,
                "--projects", $p, "--widen", $v.w)
      $log = Join-Path $logs ("{0}_{1}_{2}.log" -f $set.name, $p, $v.dir)
      $procs += Start-Process -FilePath $py -ArgumentList $args -NoNewWindow -PassThru -RedirectStandardOutput $log `
                              -RedirectStandardError ($log + ".err")
    }
  }
}
$t0 = Get-Date
$procs | Wait-Process
"ALL EXTRACTIONS DONE in " + ((Get-Date) - $t0).TotalMinutes + " min; exit codes: " + (($procs | ForEach-Object { $_.ExitCode }) -join ",")
