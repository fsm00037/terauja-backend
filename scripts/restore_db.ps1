# PostgreSQL Restore Script for Windows (PowerShell)
# This script restores a PostgreSQL custom-format dump (.dump) to the dockerized database.

param (
    [Parameter(Mandatory=$true)]
    [string]$BackupFile
)

# If path is relative, resolve it to an absolute path
$BackupFile = Resolve-Path $BackupFile

if (-not (Test-Path $BackupFile)) {
    Write-Host "Error: Backup file not found: $BackupFile" -ForegroundColor Red
    exit 1
}

# Load environment variables
$envFile = Join-Path $PSScriptRoot "..\.env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $key, $val = $line -split '=', 2
            $key = $key.Trim()
            $val = $val.Trim().Trim('"').Trim("'")
            [System.Environment]::SetEnvironmentVariable($key, $val)
        }
    }
}

$CONTAINER_NAME = "psicouja-postgres"
$DB_USER = [System.Environment]::GetEnvironmentVariable("POSTGRES_USER")
if (-not $DB_USER) { $DB_USER = "psicouja" }
$DB_NAME = [System.Environment]::GetEnvironmentVariable("POSTGRES_DB")
if (-not $DB_NAME) { $DB_NAME = "psicouja" }
$envPassword = [System.Environment]::GetEnvironmentVariable("POSTGRES_PASSWORD")
if (-not $envPassword) { $envPassword = "psicouja_secret" }

Write-Host "------------------------------------------------------------" -ForegroundColor Yellow
Write-Host "⚠️ WARNING: This will overwrite and restore database: $DB_NAME" -ForegroundColor Yellow
Write-Host "Backup file: $BackupFile" -ForegroundColor Yellow
Write-Host "------------------------------------------------------------" -ForegroundColor Yellow
$response = Read-Host "Are you sure you want to proceed? (Y/N)"
if ($response -ne "Y" -and $response -ne "y") {
    Write-Host "Restore canceled." -ForegroundColor Gray
    exit 0
}

# Check if docker container is running
$containerStatus = docker inspect -f '{{.State.Running}}' $CONTAINER_NAME 2>$null
if ($containerStatus -ne "true") {
    Write-Host "Error: Container $CONTAINER_NAME is not running! Please run 'docker compose up -d' first." -ForegroundColor Red
    exit 1
}

# Copy backup file into container
Write-Host "Copying backup file to container..." -ForegroundColor Cyan
docker cp $BackupFile "${CONTAINER_NAME}:/tmp/restore.dump"

# Restore using pg_restore
Write-Host "Restoring database (this may take a few moments)..." -ForegroundColor Cyan
# --clean drops database objects before recreating them, --no-owner avoids permission errors during restore
docker exec -e PGPASSWORD=$envPassword $CONTAINER_NAME pg_restore -U $DB_USER -d $DB_NAME --clean --no-owner -v /tmp/restore.dump

if ($LASTEXITCODE -eq 0) {
    Write-Host "Restore completed successfully!" -ForegroundColor Green
} else {
    Write-Host "Error: Restore failed." -ForegroundColor Red
}

# Clean up
docker exec $CONTAINER_NAME rm /tmp/restore.dump
