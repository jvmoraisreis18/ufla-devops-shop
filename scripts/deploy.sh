#!/usr/bin/env bash
set -euo pipefail

APP_NAME="ufla-shop"
APP_USER="ufla-shop"
APP_DIR="/opt/ufla-shop"

ENV_FILE="/etc/ufla-shop.env"
ENV_EXAMPLE="/etc/ufla-shop.env.example"

BACKUP_DIR="/var/backups/ufla-shop"
SYSTEMD_DIR="/etc/systemd/system"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Execute como root: sudo $0"
    exit 1
fi

echo "==> Instalando dependências do sistema"
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 \
    python3-venv \
    postgresql \
    redis-server \
    nginx \
    openssl \
    rsync \
    curl

echo "==> Criando usuário da aplicação"
if ! id "${APP_USER}" &>/dev/null; then
    useradd \
        --system \
        --home "${APP_DIR}" \
        --shell /usr/sbin/nologin \
        "${APP_USER}"
fi

echo "==> Preparando diretórios"
install -d -o "${APP_USER}" -g "${APP_USER}" "${APP_DIR}"
install -d -o "${APP_USER}" -g "${APP_USER}" "${BACKUP_DIR}"

echo "==> Instalando arquivo de ambiente de exemplo"
install -m 0644 \
    "${REPO_DIR}/ufla-shop.env.example" \
    "${ENV_EXAMPLE}"

if [[ ! -f "${ENV_FILE}" ]]; then
    cp "${ENV_EXAMPLE}" "${ENV_FILE}"
    chmod 600 "${ENV_FILE}"
    echo "ATENÇÃO: ajuste a senha em ${ENV_FILE}"
fi

echo "==> Sincronizando aplicação"
rsync -a --delete \
    --exclude ".git/" \
    --exclude ".venv/" \
    --exclude "__pycache__/" \
    --exclude ".pytest_cache/" \
    --exclude ".ruff_cache/" \
    --exclude "*.db" \
    "${REPO_DIR}/" \
    "${APP_DIR}/"

chmod 755 "${APP_DIR}/scripts/"*.sh

echo "==> Criando ambiente virtual"
python3 -m venv "${APP_DIR}/.venv"

echo "==> Instalando dependências Python"
"${APP_DIR}/.venv/bin/pip" install --upgrade pip
"${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

echo "==> Instalando units do systemd"
install -m 0644 \
    "${REPO_DIR}/systemd/ufla-shop.service" \
    "${SYSTEMD_DIR}/ufla-shop.service"

install -m 0644 \
    "${REPO_DIR}/systemd/ufla-shop-backup.service" \
    "${SYSTEMD_DIR}/ufla-shop-backup.service"

install -m 0644 \
    "${REPO_DIR}/systemd/ufla-shop-backup.timer" \
    "${SYSTEMD_DIR}/ufla-shop-backup.timer"

systemctl daemon-reload

echo "==> Instalando configuração do Nginx"
install -d /etc/nginx/ssl/ufla-shop

if [[ ! -f /etc/nginx/ssl/ufla-shop/server.pem ||
      ! -f /etc/nginx/ssl/ufla-shop/server.key ]]; then

    openssl req \
        -x509 \
        -nodes \
        -days 365 \
        -newkey rsa:2048 \
        -keyout /etc/nginx/ssl/ufla-shop/server.key \
        -out /etc/nginx/ssl/ufla-shop/server.pem \
        -subj "/CN=localhost"

    chmod 600 /etc/nginx/ssl/ufla-shop/server.key
fi

install -m 0644 \
    "${REPO_DIR}/nginx/loja.conf" \
    /etc/nginx/sites-available/ufla-shop

ln -sfn \
    /etc/nginx/sites-available/ufla-shop \
    /etc/nginx/sites-enabled/ufla-shop

rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl enable --now nginx

echo "==> Iniciando aplicação"
systemctl enable ufla-shop
systemctl restart ufla-shop

echo "==> Habilitando timer de backup"
systemctl enable --now ufla-shop-backup.timer

echo "==> Healthcheck"
for attempt in {1..10}; do
    if curl -fsS -o /dev/null http://localhost:8000/ready; then
        echo "Aplicação pronta."
        exit 0
    fi

    echo "Aguardando aplicação... tentativa ${attempt}/10"
    sleep 1
done

echo "Healthcheck falhou."
exit 1