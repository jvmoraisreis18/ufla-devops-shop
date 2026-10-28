# Estágio 1: instalação das dependências
FROM python:3.12-alpine AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

COPY requirements.txt .

RUN python -m pip install --no-cache-dir --prefix=/install -r requirements.txt


# Estágio 2: imagem final
FROM python:3.12-alpine AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SQLITE_PATH=/app/loja.db

WORKDIR /app

# Copia apenas as dependências de execução
COPY --from=builder /install /usr/local

# Copia os arquivos necessários para executar a aplicação
COPY app/ ./app/
COPY static/ ./static/

# Cria um usuário sem privilégios administrativos
RUN addgroup -S appgroup \
    && adduser -S appuser -G appgroup \
    && chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

# Verifica a saúde sem instalar ferramentas adicionais
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" || exit 1

# Formato exec para permitir o recebimento correto dos sinais
CMD ["uvicorn", "app:api", "--host", "0.0.0.0", "--port", "8000"]
