FROM python:3.12-slim

RUN pip install --no-cache-dir fastapi uvicorn httpx

WORKDIR /app
COPY imggen.py .

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

EXPOSE 8000
CMD ["uvicorn", "imggen:app", "--host", "0.0.0.0", "--port", "8000"]
