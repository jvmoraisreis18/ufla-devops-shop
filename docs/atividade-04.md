# Atividade 04 — Containerizar a aplicação

## 1. Construção da imagem

A aplicação foi containerizada utilizando Docker e Python 3.12 Alpine.

A construção utiliza duas etapas:
- **builder:** instala as dependências definidas em requirements.txt.
- **runtime:** contém a aplicação e as dependências necessárias para executá-la.

## 2. Tamanho da imagem

As imagens foram construídas e medidas localmente com Docker.

| Métrica | Imagem inicial | Imagem final |
|---|---:|---:|
| Imagem-base | python:3.12-slim | python:3.12-alpine |
| Estratégia | Etapa única | Multi-stage build |
| Tamanho em disco | 236 MB | 140 MB |

A imagem final atende ao limite de 150 MB estabelecido na atividade.

A redução foi de 96 MB, aproximadamente 40,7% em relação à imagem inicial.

Comando utilizado para comparar os tamanhos:

    docker images ufla-devops-shop

## 3. Otimizações aplicadas

- Utilização da imagem-base python:3.12-alpine.
- Construção em múltiplas etapas (multi-stage build).
- Instalação apenas das dependências de execução.
- Utilização do .dockerignore para excluir arquivos desnecessários, como .git, .venv, testes, caches e arquivos de ambiente.
- Execução da aplicação com o usuário não privilegiado appuser.
- Utilização do formato exec no comando CMD.
- Configuração de HEALTHCHECK para consultar o endpoint /health.

## 4. Verificações realizadas

### Construção da imagem

Comando:

    docker build -t ufla-devops-shop:atividade-04 .

Resultado: construção concluída com sucesso.

### Endpoint de saúde

Comando:

    curl -i http://localhost:8001/health

Resultado: HTTP 200 OK.

### Estado de saúde do contêiner

Comando:

    docker inspect --format='{{.State.Health.Status}}' ufla-shop-atividade-04

Resultado: healthy.

### Listagem de produtos

Comando:

    curl -s http://localhost:8001/api/produtos

Resultado: a API retornou 12 produtos.

### Usuário de execução

Comando:

    docker exec ufla-shop-atividade-04 id

Resultado:

    uid=100(appuser) gid=101(appgroup) groups=101(appgroup)

A aplicação foi executada sem utilizar o usuário root.

### Tempo de encerramento

Comando:

    time docker stop ufla-shop-atividade-04

Resultado observado:

    real    0m0,411s

O contêiner foi encerrado em aproximadamente 0,411 segundo, abaixo do limite de 2 segundos.

## 5. Por que utilizar /health em vez de /ready?

O endpoint /health verifica se a aplicação está viva sem consultar suas dependências. Por isso, é adequado para o HEALTHCHECK, que deve identificar se o processo da aplicação continua funcionando.

Já o endpoint /ready verifica a disponibilidade das dependências, como o banco de dados e o cache. Uma falha em uma dessas dependências não significa necessariamente que o processo da aplicação esteja parado; por isso, os dois endpoints têm finalidades diferentes.
