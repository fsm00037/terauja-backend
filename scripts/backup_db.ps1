# PostgreSQL Backup Script for Windows (PowerShell)
# This script dumps the dockerized PostgreSQL database to a local file.

# Load environment variables from .env
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

# Config
$CONTAINER_NAME = "psicouja-postgres"
$DB_USER = [System.Environment]::GetEnvironmentVariable("POSTGRES_USER")
if (-not $DB_USER) { $DB_USER = "psicouja" }
$DB_NAME = [System.Environment]::GetEnvironmentVariable("POSTGRES_DB")
if (-not $DB_NAME) { $DB_NAME = "psicouja" }

$BACKUP_DIR = Join-Path $PSScriptRoot "..\backups"
if (-not (Test-Path $BACKUP_DIR)) {
    New-Item -ItemType Directory -Path $BACKUP_DIR | Out-Null
}

$DATE = Get-Date -Format "yyyyMMdd_HHmmss"
$BACKUP_FILE = Join-Path $BACKUP_DIR "backup_${DB_NAME}_${DATE}.dump"

Write-Host "Starting backup for PostgreSQL database: $DB_NAME ..." -ForegroundColor Cyan

# Check if docker container is running
$containerStatus = docker inspect -f '{{.State.Running}}' $CONTAINER_NAME 2>$null
if ($containerStatus -ne "true") {
    Write-Host "Error: Container $CONTAINER_NAME is not running! Please run 'docker compose up -d' first." -ForegroundColor Red
    exit 1
}

# Run pg_dump inside the container and output to host file
# We use docker exec with env password to bypass password prompt
$envPassword = [System.Environment]::GetEnvironmentVariable("POSTGRES_PASSWORD")
if (-not $envPassword) { $envPassword = "psicouja_secret" }

Write-Host "Creating backup dump inside container..." -ForegroundColor Cyan
docker exec -e PGPASSWORD=$envPassword $CONTAINER_NAME pg_dump -U $DB_USER -d $DB_NAME -F c -b -v -f /tmp/temp_backup.dump

if ($LASTEXITCODE -eq 0) {
    # Copy from container to host
    Write-Host "Downloading backup file to host: $BACKUP_FILE ..." -ForegroundColor Cyan
    docker cp "${CONTAINER_NAME}:/tmp/temp_backup.dump" $BACKUP_FILE
    
    # Clean up temp file in container
    docker exec $CONTAINER_NAME rm /tmp/temp_backup.dump
    
    Write-Host "Backup completed successfully!" -ForegroundColor Green
    Write-Host "Saved to: $BACKUP_FILE" -ForegroundColor Yellow
} else {
    Write-Host "Error: Failed to create database backup." -ForegroundColor Red
    exit 1
}
