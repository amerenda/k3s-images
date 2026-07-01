FROM python:3.12-slim

RUN pip install --no-cache-dir fastapi uvicorn docker huggingface_hub

WORKDIR /app
COPY model_switcher.py .

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8091/health')"

CMD ["python", "model_switcher.py"]
