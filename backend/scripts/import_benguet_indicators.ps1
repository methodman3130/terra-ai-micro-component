$ErrorActionPreference = "Stop"

# Keep the connection string out of source files. The user copies it from the
# Neon Connect dialog immediately before running the companion .bat file.
$connectionString = (Get-Clipboard -Raw).Trim()
if (-not $connectionString.StartsWith("postgresql://")) {
    throw "Copy only the Neon connection string (it starts with postgresql://), then run this file again."
}

$env:TERRA_DATABASE_URL = $connectionString -replace '^postgresql://', 'postgresql+psycopg://'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))

python -m pip install -r requirements.txt
python scripts/load_crop_indicator_csv.py --variable production --table 0082E4EVCP3 --title "Vegetables and Root Crops: Volume of Production" --unit "metric tons" --csv data/raw/production.csv
python scripts/load_crop_indicator_csv.py --variable area_harvested --table 0112E4EAHM3 --title "Vegetables and Root Crops: Area Harvested" --unit "hectares" --csv data/raw/area_harvested.csv

Write-Host "Import complete. You can close this window." -ForegroundColor Green
