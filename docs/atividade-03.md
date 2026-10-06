# Atividade 3 — Automatizar de verdade

## 1. Objetivo

Nesta atividade, a aplicação `ufla-devops-shop` foi configurada para funcionar como um serviço Linux, com gerenciamento pelo `systemd`, backup periódico do banco PostgreSQL e Nginx como proxy reverso com TLS.

A solução foi implementada com:

* `scripts/deploy.sh`: instalação e configuração idempotente da aplicação;
* `scripts/backup.sh`: backup compactado do PostgreSQL com rotação;
* `systemd/ufla-shop.service`: gerenciamento da aplicação;
* `systemd/ufla-shop-backup.service`: execução do backup;
* `systemd/ufla-shop-backup.timer`: agendamento diário do backup;
* `nginx/loja.conf`: proxy reverso com HTTPS.

---

## 2. Execução do deploy

Em uma máquina Linux com `systemd`, o deploy pode ser executado a partir da raiz do projeto com:

```bash
chmod +x scripts/deploy.sh
sudo ./scripts/deploy.sh
```

O script realiza a instalação das dependências, prepara o diretório `/opt/ufla-shop`, cria o ambiente virtual Python, instala os requisitos, instala as units do `systemd`, configura o Nginx, habilita o timer de backup e realiza um healthcheck da aplicação.

O healthcheck consulta:

```text
http://localhost:8000/ready
```

até que a aplicação esteja disponível.

---

## 3. Serviço systemd e reinício automático

O serviço foi configurado para executar a aplicação com o usuário `ufla-shop`, utilizando o arquivo `/etc/ufla-shop.env` para as variáveis de ambiente.

A configuração utiliza:

```ini
User=ufla-shop
WorkingDirectory=/opt/ufla-shop
EnvironmentFile=/etc/ufla-shop.env
ExecStart=/opt/ufla-shop/.venv/bin/uvicorn app:api --port 8000
Restart=on-failure
```

A aplicação permaneceu em execução após o deploy:

```text
● ufla-shop.service - ufla-devops-shop
     Loaded: loaded (/etc/systemd/system/ufla-shop.service; enabled; preset: enabled)
     Active: active (running)
     Main PID: 77952 (uvicorn)
```

Também foi realizado o teste de reinício automático.

Com o serviço em execução, foi utilizado:

```bash
sudo systemctl kill -s SIGKILL ufla-shop.service
sleep 5
sudo systemctl status ufla-shop --no-pager
```

Resultado:

```text
● ufla-shop.service - ufla-devops-shop
     Loaded: loaded (/etc/systemd/system/ufla-shop.service; enabled; preset: enabled)
     Active: active (running) since Mon 2026-10-05 21:28:33 -03
     Main PID: 74063 (uvicorn)
```

O journal também registrou o reinício automático:

```text
ufla-shop.service: Scheduled restart job
Started ufla-shop.service
```

Isso comprova o funcionamento de `Restart=on-failure`.

---

## 4. Backup do banco de dados

O backup do banco PostgreSQL é realizado pelo script:

```text
scripts/backup.sh
```

Os arquivos são armazenados em:

```text
/var/backups/ufla-shop/
```

no formato:

```text
loja-AAAA-MM-DD-HHMM.sql.gz
```

Foi realizada a execução do backup três vezes, resultando nos seguintes arquivos:

```bash
sudo ls -la /var/backups/ufla-shop
```

Saída:

```text
total 32
drwxr-xr-x 2 ufla-shop ufla-shop 4096 Oct  5 21:55 .
drwxr-xr-x 3 root      root      4096 Oct  5 21:09 ..
-rw-r--r-- 1 ufla-shop ufla-shop 1624 Oct  5 21:16 loja-2026-10-05-2116.sql.gz
-rw-r--r-- 1 ufla-shop ufla-shop 1625 Oct  5 21:20 loja-2026-10-05-2120.sql.gz
-rw-r--r-- 1 ufla-shop ufla-shop 1625 Oct  5 21:21 loja-2026-10-05-2121.sql.gz
-rw-r--r-- 1 ufla-shop ufla-shop 1626 Oct  5 21:53 loja-2026-10-05-2153.sql.gz
-rw-r--r-- 1 ufla-shop ufla-shop 1626 Oct  5 21:54 loja-2026-10-05-2154.sql.gz
-rw-r--r-- 1 ufla-shop ufla-shop 1622 Oct  5 21:55 loja-2026-10-05-2155.sql.gz
```

As três últimas execuções registraram os respectivos backups no journal:

```bash
sudo journalctl -t backup -n 10 --no-pager
```

```text
out 05 21:53:00 joao-Inspiron-15-3530 backup[78261]: arquivo=/var/backups/ufla-shop/loja-2026-10-05-2153.sql.gz tamanho=1626 bytes
out 05 21:54:09 joao-Inspiron-15-3530 backup[79426]: arquivo=/var/backups/ufla-shop/loja-2026-10-05-2154.sql.gz tamanho=1626 bytes
out 05 21:55:02 joao-Inspiron-15-3530 backup[79585]: arquivo=/var/backups/ufla-shop/loja-2026-10-05-2155.sql.gz tamanho=1622 bytes
```

Também foi validada a integridade de um dos arquivos com:

```bash
sudo gzip -t /var/backups/ufla-shop/loja-2026-10-05-2116.sql.gz
```

e seu conteúdo foi conferido com:

```bash
sudo zcat /var/backups/ufla-shop/loja-2026-10-05-2116.sql.gz | head
```

O arquivo continha um dump PostgreSQL válido.

---

## 5. Timer de backup

O backup foi configurado para execução diária às 03:00.

A unit está configurada com:

```ini
[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true
Unit=ufla-shop-backup.service
```

O timer está habilitado e aguardando sua próxima execução:

```text
● ufla-shop-backup.timer - Backup diário do ufla-devops-shop
     Loaded: loaded (/etc/systemd/system/ufla-shop-backup.timer; enabled; preset: enabled)
     Active: active (waiting)
     Trigger: Tue 2026-10-06 03:00:00 -03
   Triggers: ● ufla-shop-backup.service
```

A confirmação pelo `systemctl list-timers` foi:

```text
Tue 2026-10-06 03:00:00 -03      5h 14min -                                      - ufla-shop-backup.timer         ufla-shop-backup.service
```

---

## 6. Nginx e TLS

O Nginx foi configurado como proxy reverso, com certificado autoassinado para HTTPS.

A configuração utiliza:

```nginx
proxy_pass http://127.0.0.1:8000;

proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```

A configuração foi validada com:

```bash
sudo nginx -t
```

Resultado:

```text
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

### HTTPS

Teste:

```bash
curl -kI https://localhost
```

Resultado:

```text
HTTP/1.1 200 OK
Server: nginx/1.28.3 (Ubuntu)
Date: Tue, 06 Oct 2026 00:44:39 GMT
Content-Type: text/html; charset=utf-8
Content-Length: 1262
Connection: keep-alive
accept-ranges: bytes
last-modified: Mon, 05 Oct 2026 23:48:25 GMT
etag: "138f1fe33fd39f7904910e4abc467f39"
```

### HTTP → HTTPS

Teste:

```bash
curl -I http://localhost
```

Resultado:

```text
HTTP/1.1 301 Moved Permanently
Server: nginx/1.28.3 (Ubuntu)
Date: Tue, 06 Oct 2026 00:44:49 GMT
Content-Type: text/html
Content-Length: 178
Connection: keep-alive
Location: https://localhost/
```

### Healthcheck através do Nginx

Também foi validado:

```bash
curl -k https://localhost/ready
```

Resultado:

```json
{"status":"ok","banco":"ok","cache":"ok"}
```

Isso confirma que o Nginx está encaminhando as requisições para a aplicação e que PostgreSQL e Redis estão disponíveis.

---

## 7. Idempotência do deploy

O `deploy.sh` foi executado duas vezes consecutivamente, sem alterações entre as execuções.

### Primeira execução

```bash
sudo ./scripts/deploy.sh 2>&1 | tee /tmp/deploy-run-1.log
```

Código de saída:

```text
0
```

Últimas linhas:

```text
==> Instalando units do systemd
==> Instalando configuração do Nginx
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
Synchronizing state of nginx.service with SysV service script with /usr/lib/systemd/systemd-sysv-install.
Executing: /usr/lib/systemd/systemd-sysv-install enable nginx
==> Iniciando aplicação
==> Habilitando timer de backup
==> Healthcheck
curl: (7) Failed to connect to localhost port 8000 after 0 ms: Could not connect to server
Aguardando aplicação... tentativa 1/10
Aplicação pronta.
```

### Segunda execução

```bash
sudo ./scripts/deploy.sh 2>&1 | tee /tmp/deploy-run-2.log
```

Código de saída:

```text
0
```

Últimas linhas:

```text
==> Instalando units do systemd
==> Instalando configuração do Nginx
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
Synchronizing state of nginx.service with SysV service script with /usr/lib/systemd/systemd-sysv-install.
Executing: /usr/lib/systemd/systemd-sysv-install enable nginx
==> Iniciando aplicação
==> Habilitando timer de backup
==> Healthcheck
curl: (7) Failed to connect to localhost port 8000 after 0 ms: Could not connect to server
Aguardando aplicação... tentativa 1/10
Aplicação pronta.
```

As duas execuções terminaram com código `0`, demonstrando que o script pode ser executado novamente sem falhar.

---

## 8. Verificação de segurança

Foi verificado que não existem arquivos de ambiente, certificados ou chaves privadas versionados no Git.

Comando utilizado:

```bash
git ls-files | grep -E '(^|/)(.*\.env$|.*\.pem$|.*\.key$)'
```

O comando não retornou nenhum arquivo.

O arquivo de ambiente real utilizado pela aplicação permanece em:

```text
/etc/ufla-shop.env
```

e não é versionado no repositório.

---

## 9. Estado final

Ao final da atividade, o serviço da aplicação estava em execução:

```text
● ufla-shop.service - ufla-devops-shop
     Loaded: loaded (/etc/systemd/system/ufla-shop.service; enabled; preset: enabled)
     Active: active (running)
     Main PID: 77952 (uvicorn)
```

A aplicação também respondeu corretamente ao endpoint de prontidão:

```text
curl -s http://localhost:8000/ready
```

com:

```json
{"status":"ok","banco":"ok","cache":"ok"}
```

Os principais requisitos da atividade foram validados: deploy idempotente, serviço `systemd`, reinício automático, backup PostgreSQL, timer diário, Nginx com TLS, redirecionamento HTTP para HTTPS e healthcheck.
