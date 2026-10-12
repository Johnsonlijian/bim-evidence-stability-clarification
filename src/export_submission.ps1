# Assemble the CACAIE upload files: figures as separate PDF files in order of appearance, LaTeX source, tables.
# Usage: powershell -File export_submission.ps1
$r10 = Split-Path -Parent $PSScriptRoot
$m = Join-Path $r10 "manuscript"
$s = Join-Path $r10 "submission"
$up = Join-Path $s "upload"
New-Item -ItemType Directory -Force $up, (Join-Path $up "figures"), (Join-Path $up "tables") | Out-Null
# Figure 1: TikZ framework diagram compiled stand-alone
Push-Location $m
pdflatex -interaction=nonstopmode figure1_standalone.tex | Out-Null
Pop-Location
$order = @(
  @{ src = (Join-Path $m "figure1_standalone.pdf"); dst = "Figure_1.pdf" },
  @{ src = (Join-Path $r10 "figures\fig_e1_status.pdf"); dst = "Figure_2.pdf" },
  @{ src = (Join-Path $r10 "figures\fig_cases.pdf"); dst = "Figure_3.pdf" },
  @{ src = (Join-Path $r10 "figures\fig_e4_validation.pdf"); dst = "Figure_4.pdf" },
  @{ src = (Join-Path $r10 "figures\fig_e2_models.pdf"); dst = "Figure_5.pdf" },
  @{ src = (Join-Path $r10 "figures\fig_e2_anytime.pdf"); dst = "Figure_6.pdf" },
  @{ src = (Join-Path $r10 "figures\fig_e3_robustness.pdf"); dst = "Figure_7.pdf" }
)
foreach ($f in $order) { Copy-Item $f.src (Join-Path $up ("figures\" + $f.dst)) -Force }
foreach ($f in "manuscript.tex", "references.bib", "numbers.tex", "numbers_dialogue.tex", "numbers_runtime.tex",
               "fig_framework.tex", "manuscript.bbl", "manuscript.pdf") {
  Copy-Item (Join-Path $m $f) (Join-Path $up $f) -Force
}
Copy-Item (Join-Path $r10 "outputs\tables\*.tex") (Join-Path $up "tables") -Force
# the upload copy reads tables and figures from local folders
$tex = Join-Path $up "manuscript.tex"
(Get-Content $tex -Raw -Encoding utf8).Replace("../outputs/tables/", "tables/").Replace("\graphicspath{{../figures/}}", "\graphicspath{{figures/}}") |
  Set-Content $tex -Encoding utf8
foreach ($f in "fig_e1_status", "fig_cases", "fig_e4_validation", "fig_e2_models", "fig_e2_anytime", "fig_e3_robustness") {
  Copy-Item (Join-Path $r10 "figures\$f.pdf") (Join-Path $up "figures\$f.pdf") -Force
}
Get-ChildItem $up -Recurse -File | ForEach-Object { "{0,10:N0}  {1}" -f $_.Length, $_.FullName.Substring($up.Length + 1) }
