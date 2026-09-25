# Builds the Windows app into dist\R6MatchStats and dist\R6MatchStats-Windows.zip.
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File desktop\build.ps1
# Needs Python 3.10+ (uses .venv if present) and Go 1.23+ (or an existing r6-dissect.exe).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (Get-Command go -ErrorAction SilentlyContinue) {
    go build -o r6-dissect.exe .
    if ($LASTEXITCODE) { throw "go build failed" }
} elseif (-not (Test-Path r6-dissect.exe)) {
    throw "Install Go (https://go.dev/dl/) or build r6-dissect.exe first."
}

$python = if (Test-Path .venv\Scripts\python.exe) { ".venv\Scripts\python.exe" } else { "python" }
& $python -m pip install --quiet -r scripts\requirements.txt -r desktop\requirements-build.txt
if ($LASTEXITCODE) { throw "pip install failed" }

# the GitHub repo that the app's "check for a newer version" link points to
$repo = $env:GITHUB_REPOSITORY
if (-not $repo) { $repo = (git remote get-url origin) -replace '^.*github\.com[:/]', '' -replace '\.git$', '' }
New-Item -ItemType Directory -Force build | Out-Null
Set-Content -Path build\repo.txt -Value $repo -Encoding ascii

& $python -m PyInstaller --noconfirm --clean --distpath dist --workpath build\pyinstaller desktop\R6MatchStats.spec
if ($LASTEXITCODE) { throw "PyInstaller failed" }

# Python's zipfile, with retries: antivirus can briefly lock the files PyInstaller just wrote
foreach ($attempt in 1..3) {
    & $python -c "import shutil; shutil.make_archive('dist/R6MatchStats-Windows', 'zip', 'dist', 'R6MatchStats')"
    if (-not $LASTEXITCODE) { break }
    Start-Sleep -Seconds 5
}
if ($LASTEXITCODE) { throw "zipping dist\R6MatchStats failed" }
Write-Host "Built dist\R6MatchStats-Windows.zip"
