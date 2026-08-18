#!/bin/bash
# WYDT Backup Script
# Backs up the database and copies it to OMV via scp

set -e

DATE=$(date +%Y%m%d_%H%M%S)
DB_PATH="/home/tom/dev/wydt/instance/wydt.db"
BACKUP_DIR="/srv/dev-disk-by-uuid-7e649ba9-55cf-448b-8441-f65ea5d4984b/backup/wydt"
REMOTE="omv"
LOG_FILE="/home/tom/dev/wydt/logs/backup.log"

log() {
    echo "$(date +%Y-%m-%d\ %H:%M:%S) $1" | tee -a "$LOG_FILE"
}

log "Backing up WYDT database..."

# Create backup filename with timestamp
BACKUP_FILE="wydt_${DATE}.db"

# Copy to OMV
scp "$DB_PATH" "$REMOTE:$BACKUP_DIR/$BACKUP_FILE"

log "Backup complete: $BACKUP_FILE"