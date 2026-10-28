# Atividade 05 — A Stack Completa

## 1. Objetivo

Executar a aplicação `ufla-devops-shop` utilizando Docker Compose, integrando quatro serviços: API (FastAPI), PostgreSQL, Redis e Nginx.

A configuração utiliza volumes persistentes, verificações de saúde (*healthchecks*) e uma imagem Docker versionada e publicada no GitHub Container Registry (GHCR).

## 2. Serviços configurados

| Serviço | Imagem | Finalidade |
|---|---|---|
| banco | postgres:16-alpine | Persistência dos dados |
| cache | redis:7-alpine | Cache da aplicação |
| api | ghcr.io/jvmoraisreis18/ufla-shop:1.0.0 | Aplicação FastAPI |
| nginx | nginx:1.27-alpine | Proxy reverso HTTP |

Somente o Nginx publica a porta 80 no host. Os demais serviços comunicam-se pela rede interna do Docker Compose.

## 3. Evidência de execução

Comando utilizado:

```bash
docker compose up -d --wait
```

Resultado:

```text
[+] up 5/5
✔ Network ufla-devops-shop_default   Created
✔ Container ufla-devops-shop-banco-1 Healthy
✔ Container ufla-devops-shop-cache-1 Healthy
✔ Container ufla-devops-shop-api-1   Healthy
✔ Container ufla-devops-shop-nginx-1 Healthy
```

A execução de `docker compose ps` confirmou os quatro serviços com status `healthy`:

```text
SERVICE   STATUS                   PORTS
api       Up 2 minutes (healthy)   8000/tcp
banco     Up 2 minutes (healthy)   5432/tcp
cache     Up 2 minutes (healthy)   6379/tcp
nginx     Up 2 minutes (healthy)   0.0.0.0:80->80/tcp, [::]:80->80/tcp
```

### Verificação HTTP

Comando:

```bash
curl -I http://localhost
```

Resultado:

```text
HTTP/1.1 200 OK
Server: nginx/1.27.5
```

### Verificação da integração

Comando:

```bash
curl -s http://localhost/api/info
```

Resultado:

```json
{
  "aplicacao": "ufla-devops-shop",
  "versao": "1.0.0",
  "banco": "postgresql",
  "cache": "redis",
  "instancia": "a4a9d6064bdf"
}
```

## 4. Teste de persistência

Para verificar a persistência do PostgreSQL, foi criado um produto pela API.

### 4.1. Criação do produto

Comando:

```bash
curl -s -X POST http://localhost/api/produtos \
  -H 'Content-Type: application/json' \
  -d '{"nome":"Prova de persistencia","preco":9.9,"estoque":1}'
```

Resultado:

```json
{
  "id": 13,
  "nome": "Prova de persistencia",
  "descricao": "",
  "preco": 9.9,
  "estoque": 1,
  "criado_em": "2026-10-27T01:27:22.093873+00:00"
}
```

### 4.2. Remoção e recriação dos containers

Comandos executados:

```bash
docker compose down
docker compose up -d --wait
```

Após a recriação, os quatro containers retornaram ao estado `healthy`.

O comando `docker compose down` foi executado sem a opção `-v`, preservando o volume nomeado do PostgreSQL.

### 4.3. Verificação da persistência

Comando:

```bash
curl -s 'http://localhost/api/busca?q=persistencia'
```

Resultado:

```json
{
  "termo": "persistencia",
  "total": 1,
  "resultados": [
    {
      "id": 13,
      "nome": "Prova de persistencia",
      "descricao": "",
      "preco": 9.9,
      "estoque": 1,
      "criado_em": "2026-10-27T01:27:22.093873+00:00"
    }
  ]
}
```

O produto permaneceu disponível após a remoção e recriação dos containers, comprovando a persistência dos dados no volume nomeado `dados_postgres`.

## 5. Imagem publicada no GHCR

A imagem foi construída a partir do Dockerfile desenvolvido na Atividade 04 e publicada no GitHub Container Registry.

**Imagem:**

`ghcr.io/jvmoraisreis18/ufla-shop:1.0.0`

**Endereço público:**

https://github.com/jvmoraisreis18/ufla-shop/pkgs/container/ufla-shop

A imagem utiliza versionamento semântico (SemVer), com a tag `1.0.0`, e está configurada como pública.

O serviço `api` utiliza diretamente a imagem publicada, sem a instrução `build:` no Docker Compose.

## 6. depends_on e service_healthy

O `depends_on` sozinho controla apenas a ordem de inicialização dos containers, mas não garante que os serviços estejam prontos para receber conexões.

A condição `service_healthy` faz com que a API aguarde os healthchecks do PostgreSQL e do Redis serem aprovados antes de iniciar, evitando erros de conexão durante a subida da stack.

## 7. Conclusão

A stack foi executada com sucesso utilizando Docker Compose. Os quatro serviços apresentaram estado saudável, a API comunicou-se corretamente com PostgreSQL e Redis, e somente o Nginx publicou uma porta no host.

O teste de persistência confirmou que os dados armazenados no PostgreSQL sobreviveram à remoção e recriação dos containers.
