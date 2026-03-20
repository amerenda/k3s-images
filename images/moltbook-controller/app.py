"""
Moltbook Controller Pod.
Runs in k8s on murderbot (hostNetwork: true).
- Proxies /api/* → moltbook-backend at localhost:8081
- /control/start|stop|status → manages docker compose via docker socket
"""
import logging
import os
import subprocess

import docker
import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8081")
COMPOSE_FILE = os.environ.get("COMPOSE_FILE", "/moltbook/docker-compose.yml")
COMPOSE_PROJECT = os.environ.get("COMPOSE_PROJECT", "moltbook")

app = FastAPI(title="Moltbook Controller", docs_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _docker_client():
    return docker.from_env()


def _compose_cmd(args: list[str]) -> tuple[int, str, str]:
    cmd = ["docker", "compose", "-f", COMPOSE_FILE, "-p", COMPOSE_PROJECT] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return result.returncode, result.stdout, result.stderr


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Returns 200 only if backend is reachable."""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{BACKEND_URL}/health")
            r.raise_for_status()
            return {"ok": True, "backend": "up"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Backend unreachable: {e}")


@app.get("/readyz")
async def readyz():
    """Always 200 — used by k8s readiness probe for the controller itself."""
    return {"ok": True}


# ── Docker Compose Control ────────────────────────────────────────────────────

@app.get("/control/status")
async def stack_status():
    try:
        dc = _docker_client()
        containers = dc.containers.list(
            all=True, filters={"label": f"com.docker.compose.project={COMPOSE_PROJECT}"}
        )
        services = [
            {
                "name": c.labels.get("com.docker.compose.service", c.name),
                "status": c.status,
                "id": c.short_id,
            }
            for c in containers
        ]
        running = any(s["status"] == "running" for s in services)
        return {"running": running, "services": services}
    except Exception as e:
        return {"running": False, "error": str(e), "services": []}


@app.post("/control/start")
async def stack_start():
    code, out, err = _compose_cmd(["up", "-d", "--build"])
    if code != 0:
        raise HTTPException(status_code=500, detail=err or out)
    return {"ok": True, "output": out}


@app.post("/control/stop")
async def stack_stop():
    code, out, err = _compose_cmd(["down"])
    if code != 0:
        raise HTTPException(status_code=500, detail=err or out)
    return {"ok": True, "output": out}


@app.post("/control/restart")
async def stack_restart():
    _compose_cmd(["down"])
    code, out, err = _compose_cmd(["up", "-d", "--build"])
    if code != 0:
        raise HTTPException(status_code=500, detail=err or out)
    return {"ok": True, "output": out}


# ── Proxy to backend ──────────────────────────────────────────────────────────

@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(path: str, request: Request):
    url = f"{BACKEND_URL}/api/{path}"
    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.request(
                method=request.method,
                url=url,
                params=dict(request.query_params),
                headers={k: v for k, v in request.headers.items() if k.lower() != "host"},
                content=body,
            )
            return JSONResponse(
                content=r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text,
                status_code=r.status_code,
            )
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Backend is offline")
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8082, log_level="info")
