#!/bin/bash
# PostgreSQL Backup Script for Linux (Bash)
# This script dumps the dockerized PostgreSQL database to a local file.

# Get current directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Load environment variables from .env
if [ -f "$SCRIPT_DIR/../.env" ]; then
    export $(grep -v '^#' "$SCRIPT_DIR/../.env" | xargs)
fi

# Config
CONTAINER_NAME="psicouja-postgres"
DB_USER=${POSTGRES_USER:-psicouja}
DB_NAME=${POSTGRES_DB:-psicouja}
DB_PASSWORD=${POSTGRES_PASSWORD:-psicouja_secret}

BACKUP_DIR="$SCRIPT_DIR/../backups"
mkdir -p "$BACKUP_DIR"

DATE=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/backup_${DB_NAME}_${DATE}.dump"

echo "Starting backup for PostgreSQL database: $DB_NAME ..."

# Check if docker container is running
if [ "$(docker inspect -f '{{.State.Running}}' $CONTAINER_NAME 2>/dev/null)" != "true" ]; then
    echo "Error: Container $CONTAINER_NAME is not running! Please run 'docker compose up -d' first."
    exit 1
fi

echo "Creating backup dump inside container..."
docker exec -e PGPASSWORD="$DB_PASSWORD" $CONTAINER_NAME pg_dump -U "$DB_USER" -d "$DB_NAME" -F c -b -v -f /tmp/temp_backup.dump

if [ $? -eq 0 ]; then
    echo "Downloading backup file to host: $BACKUP_FILE ..."
    docker cp "$CONTAINER_NAME:/tmp/temp_backup.dump" "$BACKUP_FILE"
    
    # Clean up temp file in container
    docker exec $CONTAINER_NAME rm /tmp/temp_backup.dump
    
    echo "Backup completed successfully!"
    echo "Saved to: $BACKUP_FILE"
else
    echo "Error: Failed to create database backup."
    exit 1
fi
