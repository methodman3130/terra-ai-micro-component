$ErrorActionPreference = "Stop"

# Keep the connection string out of source files. The user copies it from the
# Neon Connect dialog immediately before running the companion .bat file.
$connectionString = (Get-Clipboard -Raw).Trim()
if (-not $connectionString.StartsWith("postgresql://")) {
    throw "Copy only the Neon connection string (it starts with postgresql://), then run this file again."
}

$env:TERRA_DATABASE_URL = $connectionString -replace '^postgresql://', 'postgresql+psycopg://'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
Write-Host "Checking Python packages..." -ForegroundColor Cyan

# Dependencies were installed on the first run. Do not download them again
# unless Python cannot import the two packages this importer needs.
python -c "import sqlalchemy, psycopg" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing required Python packages (first run only)..." -ForegroundColor Yellow
    python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Python package installation failed." }
}

Write-Host "Uploading Production data to Neon..." -ForegroundColor Cyan
python scripts/load_crop_indicator_csv.py --variable production --table 0082E4EVCP3 --title "Vegetables and Root Crops: Volume of Production" --unit "metric tons" --csv data/raw/production.csv
if ($LASTEXITCODE -ne 0) { throw "Production import failed. Read the error above; no partial production import was saved." }

Write-Host "Uploading Area Harvested data to Neon..." -ForegroundColor Cyan
python scripts/load_crop_indicator_csv.py --variable area_harvested --table 0112E4EAHM3 --title "Vegetables and Root Crops: Area Harvested" --unit "hectares" --csv data/raw/area_harvested.csv
if ($LASTEXITCODE -ne 0) { throw "Area-harvested import failed. Read the error above; no partial area import was saved." }

Write-Host "Import complete. You can close this window." -ForegroundColor Green
