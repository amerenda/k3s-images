FROM python:3.12-slim

# Clone upstream mem0 server source; explicit psycopg[binary] ensures
# it's present regardless of whether the upstream requirements.txt includes it
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    git clone --depth 1 https://github.com/mem0ai/mem0.git /tmp/mem0 && \
    mkdir -p /app && \
    cp -r /tmp/mem0/server/* /app/ && \
    rm -rf /tmp/mem0 && \
    apt-get purge -y git && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir -r requirements.txt psycopg[binary]

# PostgreSQL history manager + startup patch (replaces SQLiteManager)
COPY history_pg.py startup_patch.py ./

EXPOSE 8000
CMD ["python", "-c", "import startup_patch; import uvicorn; uvicorn.run('main:app', host='0.0.0.0', port=8000)"]
