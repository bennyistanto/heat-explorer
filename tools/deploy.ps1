# Publish the built dashboard (dist/) to the gh-pages branch on GitHub.
#
#   npm run deploy            build, stage, show what will be pushed, ask, then push
#   npm run deploy:check      the same without the push (nothing leaves this machine)
#   pwsh tools/deploy.ps1 -SkipBuild     publish dist/ as it is
#
# How it works, and why:
#   - The site cannot be built on GitHub: the pipeline reads AgERA5 files and derived stores on local drives. So it is built here.
#   - dist/ is copied to a folder OUTSIDE OneDrive and committed there, in a throwaway repository, as one
#     commit with no parent. That commit is force-pushed to gh-pages. This repository's own .git never
#     receives the 450 MB of built files (see the OneDrive and git section of the parent CLAUDE.md), and
#     gh-pages always holds exactly one commit, so the remote does not grow with every publish.
#   - .nojekyll is added: without it GitHub Pages runs Jekyll, which drops every folder whose name starts
#     with an underscore, and Observable Framework puts everything in _file, _import, _npm, _observablehq.
#
# The push is a FORCE push to gh-pages only. It never touches main.
# One-time setup on GitHub: Settings > Pages > Source "Deploy from a branch", branch gh-pages, folder / (root).
param(
  [switch]$SkipBuild,
  [switch]$DryRun,
  [switch]$Yes
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

function Fail($msg) { Write-Host "STOP: $msg" -ForegroundColor Red; exit 1 }

$remote = (git remote get-url origin).Trim()
if (-not $remote) { Fail "no 'origin' remote" }
$sha = (git rev-parse --short HEAD).Trim()
$dirty = [bool](git status --porcelain)

if (-not $SkipBuild) {
  Write-Host "Building the site (npm run build) ..."
  npm run build
  if ($LASTEXITCODE -ne 0) { Fail "the build failed" }
}
$dist = Join-Path $repo "dist"
if (-not (Test-Path (Join-Path $dist "index.html"))) { Fail "dist/index.html not found. Run without -SkipBuild." }

# ---- checks against GitHub's limits (docs.github.com: Pages limits; About large files)
$files = Get-ChildItem $dist -Recurse -File
$totalMB = [math]::Round(($files | Measure-Object Length -Sum).Sum / 1MB, 1)
$largest = $files | Sort-Object Length -Descending | Select-Object -First 1
$largestMB = [math]::Round($largest.Length / 1MB, 1)
Write-Host ("Site: {0} files, {1} MB; largest file {2} MB ({3})" -f $files.Count, $totalMB, $largestMB, $largest.Name)
if ($totalMB -gt 1000) { Fail "the site is over GitHub Pages' 1 GB limit" }
if ($largestMB -ge 100) { Fail "a file is over GitHub's 100 MiB limit: $($largest.FullName)" }
if ($largestMB -ge 50) { Write-Host "Note: a file is over 50 MiB; GitHub will warn about it." -ForegroundColor Yellow }
# Framework must have written relative links, or nothing loads under /<repository name>/
$html = Get-Content (Join-Path $dist "index.html") -Raw
if ($html -match '(href|src)="/[^/"]') { Fail "dist/index.html has absolute links; they break under a project page" }

# ---- stage outside OneDrive
$stage = Join-Path $env:TEMP "heat-explorer-pages"
if ($stage -like "*OneDrive*") { Fail "the staging folder is inside OneDrive: $stage" }
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path $stage | Out-Null
robocopy $dist $stage /E /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { Fail "copying dist failed (robocopy $LASTEXITCODE)" }
New-Item -ItemType File -Path (Join-Path $stage ".nojekyll") | Out-Null

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
$message = "Publish site built from $sha" + $(if ($dirty) { " plus uncommitted changes" } else { "" }) + ", $stamp"
Set-Location $stage
git init --quiet --initial-branch gh-pages
git config gc.auto 0
git config core.autocrlf false          # built files are published byte for byte
git add -A
git commit --quiet -m $message
$staged = (git ls-files | Measure-Object).Count
Write-Host "Staged $staged files in $stage"
Write-Host "Commit message: $message"
if ($dirty) { Write-Host "Note: the working tree has uncommitted changes, so the published site matches no commit exactly." -ForegroundColor Yellow }

if ($DryRun) {
  Write-Host "Dry run: nothing pushed. The staged site is in $stage" -ForegroundColor Cyan
  Set-Location $repo
  exit 0
}
if (-not $Yes) {
  $answer = Read-Host "Force-push this to gh-pages on $remote ? Type yes to continue"
  if ($answer -ne "yes") { Write-Host "Nothing pushed."; Set-Location $repo; exit 0 }
}
git push --force $remote gh-pages
if ($LASTEXITCODE -ne 0) { Set-Location $repo; Fail "the push failed" }
Set-Location $repo
Remove-Item $stage -Recurse -Force
Write-Host "Published. GitHub Pages takes a few minutes to serve a new version." -ForegroundColor Green
