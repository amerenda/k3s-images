"""model-switcher — sidecar for llama.cpp hosts.

Manages the inference container lifecycle and handles model downloads from
Hugging Face. Fully parameterized via env vars — no host-specific code.

POST /switch starts an async switch and returns immediately. Callers poll
GET /status until state is "ready" or an "error_*" state.

States (machine-readable, stable):
  ready                 — model loaded and serving
  unloading             — stopping previous inference container
  unloaded              — previous container stopped, starting new one
  loading               — new container started, awaiting health check
  error_model_not_found — GGUF path does not exist or is not readable
  error_container_stop  — failed to stop previous container
  error_image_not_found — Docker image for inference server not found
  error_port_conflict   — inference port already in use by another process
  error_container_start — generic container start failure
  error_oom             — GPU out of memory during model load
  error_load_model      — llama.cpp reported a model load failure
  error_invalid_model   — model file appears corrupt or unsupported
  error_container_exited — container started but immediately exited
  error_container_missing — container disappeared during health check
  error_load_timeout    — health check timed out (> HEALTH_TIMEOUT seconds)
  error_unknown         — unclassified error; see error_detail

Endpoints:
  GET  /health   liveness; includes prod_model_path for restore reference
  GET  /status   current switch state — always available, poll this
  GET  /models   list GGUFs on disk under MODEL_BASE_DIR
  POST /switch   start async model switch; 409 if switch already in progress
  POST /pull     download a GGUF from Hugging Face (synchronous; can be long)

Environment:
  SWITCH_PSK            required — shared secret for mutating endpoints
  MANAGED_CONTAINER     inference container name        (default: llama-server)
  MANAGED_IMAGE         Docker image to run             (required)
  MODEL_BASE_DIR        host path where GGUFs are stored (required)
  MODEL_VOLUME          volume spec host:container[:mode] (required)
  INFERENCE_PORT        inference server port            (default: 8088)
  GPU_DRIVER            "nvidia" or "amd"               (default: nvidia)
  PROD_MODEL_PATH       production GGUF path; exposed via /health and /status
  NGL                   GPU layers to offload            (default: 99)
  CTX                   context window size              (default: 131072)
  HEALTH_TIMEOUT        seconds to wait for healthy      (default: 300)
  HF_TOKEN              Hugging Face token for gated models (optional)
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import docker as docker_sdk
import uvicorn
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="model-switcher")

_PSK = os.environ.get("SWITCH_PSK", "")
_CONTAINER = os.environ.get("MANAGED_CONTAINER", "llama-server")
_IMAGE = os.environ.get("MANAGED_IMAGE", "")
_MODEL_BASE_DIR = os.environ.get("MODEL_BASE_DIR", "")
_MODEL_VOLUME = os.environ.get("MODEL_VOLUME", "")
_INFERENCE_PORT = int(os.environ.get("INFERENCE_PORT", "8088"))
_GPU_DRIVER = os.environ.get("GPU_DRIVER", "nvidia").lower()
_PROD_MODEL_PATH = os.environ.get("PROD_MODEL_PATH", "")
_NGL = os.environ.get("NGL", "99")
_CTX = os.environ.get("CTX", "131072")
_HEALTH_TIMEOUT = int(os.environ.get("HEALTH_TIMEOUT", "300"))
# Compose project name used as a label on managed containers so Komodo/compose can track them.
_COMPOSE_PROJECT = os.environ.get("COMPOSE_PROJECT_NAME", f"llm-{_CONTAINER.replace('-', '')}")


# ---------------------------------------------------------------------------
# State

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_state_lock = threading.Lock()
_state: dict = {
    "state": "ready",
    "model_path": _PROD_MODEL_PATH or None,
    "prev_model_path": None,
    "switch_started_at": None,
    "updated_at": _now(),
    "error": None,
    "error_detail": None,
    "prod_model_path": _PROD_MODEL_PATH or None,
}


def _set_state(**kwargs: object) -> dict:
    with _state_lock:
        _state.update(kwargs)
        _state["updated_at"] = _now()
        logger.info("state → %s  model=%s", _state["state"], _state.get("model_path", ""))
        return dict(_state)


def _get_state() -> dict:
    with _state_lock:
        return dict(_state)


def _is_terminal(state: str) -> bool:
    return state == "ready" or state.startswith("error_")


# ---------------------------------------------------------------------------
# Docker helpers

def _docker() -> docker_sdk.DockerClient:
    return docker_sdk.DockerClient(base_url="unix:///var/run/docker.sock")


def _parse_volume(spec: str) -> tuple[str, str, str]:
    parts = spec.split(":", 2)
    host = parts[0]
    container = parts[1] if len(parts) > 1 else host
    mode = parts[2] if len(parts) > 2 else "rw"
    return host, container, mode


def _stop_container(client: docker_sdk.DockerClient) -> None:
    try:
        c = client.containers.get(_CONTAINER)
        logger.info("Stopping %s", _CONTAINER)
        c.stop(timeout=30)
        c.remove()
        logger.info("Stopped and removed %s", _CONTAINER)
    except docker_sdk.errors.NotFound:
        logger.info("%s not found — nothing to stop", _CONTAINER)


def _start_container(client: docker_sdk.DockerClient, model_path: str) -> None:
    host_vol, container_vol, vol_mode = _parse_volume(_MODEL_VOLUME)

    kwargs: dict = dict(
        detach=True,
        name=_CONTAINER,
        restart_policy={"Name": "unless-stopped"},
        volumes={host_vol: {"bind": container_vol, "mode": vol_mode}},
        ports={f"{_INFERENCE_PORT}/tcp": _INFERENCE_PORT},
        environment={
            "MODEL": model_path,
            "NGL": _NGL,
            "CTX": _CTX,
            "PORT": str(_INFERENCE_PORT),
        },
        labels={
            "com.docker.compose.project": _COMPOSE_PROJECT,
            "com.docker.compose.service": _CONTAINER,
            "com.docker.compose.container-number": "1",
            "com.docker.compose.oneoff": "False",
        },
    )

    if _GPU_DRIVER == "nvidia":
        kwargs["environment"].update({
            "NVIDIA_VISIBLE_DEVICES": "all",
            "NVIDIA_DRIVER_CAPABILITIES": "compute,utility",
        })
        kwargs["device_requests"] = [
            docker_sdk.types.DeviceRequest(count=-1, capabilities=[["gpu"]])
        ]
    elif _GPU_DRIVER == "amd":
        kwargs["devices"] = ["/dev/kfd:/dev/kfd", "/dev/dri:/dev/dri"]
        kwargs["group_add"] = ["video", "render"]
    else:
        raise ValueError(f"Unknown GPU_DRIVER: {_GPU_DRIVER!r}")

    client.containers.run(_IMAGE, **kwargs)
    logger.info("Container %s started", _CONTAINER)


def _container_logs_tail(client: docker_sdk.DockerClient, n: int = 80) -> str:
    try:
        c = client.containers.get(_CONTAINER)
        return c.logs(tail=n).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _classify_failure(client: docker_sdk.DockerClient, timed_out: bool = False) -> tuple[str, str]:
    """Inspect the container to produce a specific error state + human detail."""
    try:
        c = client.containers.get(_CONTAINER)
        logs = c.logs(tail=100).decode("utf-8", errors="replace")
        low = logs.lower()
        status = c.status
    except docker_sdk.errors.NotFound:
        return "error_container_missing", (
            f"Container {_CONTAINER!r} disappeared during health check."
        )
    except Exception as exc:
        return "error_unknown", f"Could not inspect container: {exc}"

    # OOM — check before generic load failures
    if "cuda out of memory" in low or "out of gpu memory" in low or "cudamalloc failed" in low:
        return "error_oom", (
            f"GPU out of memory loading model. "
            f"Try a smaller quantization or reduce CTX (current={_CTX}).\n"
            f"Tail logs:\n{logs[-600:]}"
        )

    # llama.cpp model file errors
    if "error loading model" in low or "llama_model_load" in low and "error" in low:
        return "error_load_model", (
            f"llama.cpp failed to load the model file.\n"
            f"Tail logs:\n{logs[-600:]}"
        )

    # File access issues (inside the container)
    if (
        "no such file or directory" in low
        or "cannot open" in low
        or "failed to open" in low
        or "file not found" in low
    ):
        return "error_model_not_found", (
            f"Model file not accessible inside container. "
            f"Check MODEL_VOLUME mapping and that the file exists at the given path.\n"
            f"Tail logs:\n{logs[-400:]}"
        )

    # Corrupt / unsupported format
    if "invalid magic" in low or "unsupported model" in low or "bad magic" in low:
        return "error_invalid_model", (
            f"Model file appears corrupt or uses an unsupported format.\n"
            f"Tail logs:\n{logs[-400:]}"
        )

    # Container exited early
    if status in ("exited", "dead"):
        exit_code = ""
        try:
            exit_code = f" (exit code {c.attrs['State']['ExitCode']})"
        except Exception:
            pass
        return "error_container_exited", (
            f"Container exited unexpectedly{exit_code}.\n"
            f"Tail logs:\n{logs[-600:]}"
        )

    # Timeout catchall — container is running but not healthy
    if timed_out:
        return "error_load_timeout", (
            f"Model did not become healthy within {_HEALTH_TIMEOUT}s. "
            f"Container is still running — may need more time or more VRAM.\n"
            f"Tail logs:\n{logs[-400:]}"
        )

    return "error_unknown", f"Unclassified failure. Container status={status!r}.\nLogs:\n{logs[-400:]}"


def _wait_healthy(client: docker_sdk.DockerClient) -> bool:
    """Poll :INFERENCE_PORT/health until ok or timeout. Returns True if healthy."""
    deadline = time.monotonic() + _HEALTH_TIMEOUT
    url = f"http://localhost:{_INFERENCE_PORT}/health"
    while time.monotonic() < deadline:
        # If container exited, fail fast
        try:
            c = client.containers.get(_CONTAINER)
            if c.status in ("exited", "dead"):
                logger.warning("Container %s exited during health wait", _CONTAINER)
                return False
        except docker_sdk.errors.NotFound:
            logger.warning("Container %s disappeared during health wait", _CONTAINER)
            return False

        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if json.loads(resp.read()).get("status") == "ok":
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(5)

    return False


# ---------------------------------------------------------------------------
# Switch logic (runs in background thread)

def _do_switch(path: str) -> None:
    client = _docker()

    # --- Unloading ---
    _set_state(state="unloading")
    try:
        _stop_container(client)
    except Exception as exc:
        _set_state(
            state="error_container_stop",
            error="error_container_stop",
            error_detail=f"Failed to stop container {_CONTAINER!r}: {exc}",
        )
        return

    _set_state(state="unloaded")

    # --- Loading ---
    _set_state(state="loading")
    try:
        _start_container(client, path)
    except docker_sdk.errors.ImageNotFound:
        _set_state(
            state="error_image_not_found",
            error="error_image_not_found",
            error_detail=f"Docker image not found: {_IMAGE!r}. Run 'docker pull {_IMAGE}' on the host.",
        )
        return
    except Exception as exc:
        detail = str(exc)
        if "port is already allocated" in detail or "address already in use" in detail:
            _set_state(
                state="error_port_conflict",
                error="error_port_conflict",
                error_detail=(
                    f"Port {_INFERENCE_PORT} is already in use. "
                    f"Another process may be running on that port."
                ),
            )
        else:
            _set_state(
                state="error_container_start",
                error="error_container_start",
                error_detail=f"Failed to start container: {exc}",
            )
        return

    # --- Health check ---
    healthy = _wait_healthy(client)
    if not healthy:
        error, detail = _classify_failure(client, timed_out=True)
        _set_state(state=error, error=error, error_detail=detail)
        return

    _set_state(state="ready", error=None, error_detail=None, switch_started_at=None)
    logger.info("Switch complete — model ready: %s", path)


# ---------------------------------------------------------------------------
# Startup manager

def _startup_manager() -> None:
    """On startup, ensure the managed container is running with PROD_MODEL_PATH.

    Runs in a background thread so the FastAPI app becomes available immediately.
    If the managed container is already running (e.g. after a model-switcher restart),
    we read its MODEL env var to restore accurate state without disrupting inference.
    """
    if not _PROD_MODEL_PATH:
        logger.info("Startup: PROD_MODEL_PATH not set — skipping managed container check")
        return

    client = _docker()
    try:
        c = client.containers.get(_CONTAINER)
        if c.status == "running":
            # Already running — read which model is loaded from the container env
            env = {}
            for item in c.attrs.get("Config", {}).get("Env", []):
                k, _, v = item.partition("=")
                env[k] = v
            current = env.get("MODEL", _PROD_MODEL_PATH)
            logger.info("Startup: %s already running with model=%s", _CONTAINER, current)
            _set_state(state="ready", model_path=current)
            return
        else:
            logger.info("Startup: %s found but status=%s — removing and restarting", _CONTAINER, c.status)
            c.remove(force=True)
    except docker_sdk.errors.NotFound:
        logger.info("Startup: %s not found — starting with prod model", _CONTAINER)

    _set_state(state="loading", model_path=_PROD_MODEL_PATH, switch_started_at=_now())
    try:
        _start_container(client, _PROD_MODEL_PATH)
    except Exception as exc:
        _set_state(state="error_container_start", error="error_container_start",
                   error_detail=f"Startup failed to start container: {exc}")
        return

    if _wait_healthy(client):
        _set_state(state="ready", error=None, error_detail=None, switch_started_at=None)
        logger.info("Startup: prod model ready")
    else:
        error, detail = _classify_failure(client, timed_out=True)
        _set_state(state=error, error=error, error_detail=detail)
        logger.error("Startup: managed container failed to become healthy: %s", error)


# ---------------------------------------------------------------------------
# Request/response models

class SwitchRequest(BaseModel):
    path: str


class PullRequest(BaseModel):
    hf_repo: str
    filename: str
    hf_token: Optional[str] = None


# ---------------------------------------------------------------------------
# PSK check

def _psk_check(x_psk: str) -> None:
    if not _PSK:
        raise HTTPException(status_code=500, detail="SWITCH_PSK not configured")
    if x_psk != _PSK:
        raise HTTPException(status_code=401, detail="Invalid PSK")


# ---------------------------------------------------------------------------
# Endpoints

@app.on_event("startup")
async def on_startup() -> None:
    threading.Thread(target=_startup_manager, daemon=True).start()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "prod_model_path": _PROD_MODEL_PATH}


@app.get("/status")
def status() -> dict:
    return _get_state()


@app.get("/models")
def list_models() -> dict:
    if not _MODEL_BASE_DIR:
        return {"models": [], "base_dir": None}
    base = Path(_MODEL_BASE_DIR)
    if not base.exists():
        return {"models": [], "base_dir": str(base)}
    gguf_files = sorted(str(p.relative_to(base)) for p in base.rglob("*.gguf"))
    return {"models": gguf_files, "base_dir": str(base)}


@app.post("/switch")
def switch_model(
    req: SwitchRequest,
    background_tasks: BackgroundTasks,
    x_psk: str = Header(...),
) -> dict:
    _psk_check(x_psk)

    if not req.path:
        raise HTTPException(status_code=422, detail="path is required")

    with _state_lock:
        current = _state["state"]
        if not _is_terminal(current):
            raise HTTPException(
                status_code=409,
                detail=f"Switch already in progress (state={current!r}). "
                       f"Poll GET /status until terminal state before switching again.",
            )
        # Transition immediately so concurrent requests get 409
        _state.update(
            state="unloading",
            model_path=req.path,
            prev_model_path=_state.get("model_path"),
            switch_started_at=_now(),
            updated_at=_now(),
            error=None,
            error_detail=None,
        )

    logger.info("Switch initiated → %s", req.path)
    background_tasks.add_task(_do_switch, req.path)
    return _get_state()


@app.post("/pull")
def pull_model(req: PullRequest, x_psk: str = Header(...)) -> dict:
    _psk_check(x_psk)

    if not _MODEL_BASE_DIR:
        raise HTTPException(status_code=500, detail="MODEL_BASE_DIR not configured")

    from huggingface_hub import hf_hub_download

    logger.info("Pulling %s / %s → %s", req.hf_repo, req.filename, _MODEL_BASE_DIR)
    try:
        local_path = hf_hub_download(
            repo_id=req.hf_repo,
            filename=req.filename,
            local_dir=_MODEL_BASE_DIR,
            token=req.hf_token or os.environ.get("HF_TOKEN") or None,
        )
    except Exception as exc:
        logger.error("Pull failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info("Downloaded to %s", local_path)
    return {"status": "ok", "path": local_path}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8091)
