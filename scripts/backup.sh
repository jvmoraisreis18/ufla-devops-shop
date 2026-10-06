#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="/var/backups/ufla-shop"
TIMESTAMP="$(date '+%Y-%m-%d-%H%M')"
BACKUP_FILE="${BACKUP_DIR}/loja-${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

echo "==> Gerando backup: ${BACKUP_FILE}"

pg_dump "${DATABASE_URL}" | gzip > "${BACKUP_FILE}"

echo "==> Aplicando rotação"

mapfile -t BACKUPS < <(
    find "${BACKUP_DIR}" \
        -maxdepth 1 \
        -type f \
        -name 'loja-*.sql.gz' \
        -printf '%T@ %p\n' |
    sort -nr |
    cut -d' ' -f2-
)

if (( ${#BACKUPS[@]} > 7 )); then
    for OLD_BACKUP in "${BACKUPS[@]:7}"; do
        rm -f "${OLD_BACKUP}"
    done
fi

SIZE="$(stat -c '%s' "${BACKUP_FILE}")"

logger -t backup \
    "arquivo=${BACKUP_FILE} tamanho=${SIZE} bytes"

echo "Backup concluído: ${BACKUP_FILE} (${SIZE} bytes)"