"""Unit and regression tests for model_switcher.py.

Run with: pytest test_model_switcher.py -v
Requires: pytest httpx fastapi uvicorn docker huggingface_hub
"""
import os
import threading
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Patch env vars before importing the module so module-level globals are set
os.environ.setdefault("SWITCH_PSK", "test-psk")
os.environ.setdefault("MODEL_BASE_DIR", "/tmp/models")
os.environ.setdefault("MANAGED_IMAGE", "test-image:latest")
os.environ.setdefault("MODEL_VOLUME", "/tmp/models:/mnt/models")

import model_switcher as ms  # noqa: E402 — env must be set first

PSK = "test-psk"
HEADERS = {"x-psk": PSK}


@pytest.fixture(autouse=True)
def reset_state():
    """Reset module state between tests."""
    with ms._state_lock:
        ms._state.update({
            "state": "ready",
            "model_path": None,
            "prev_model_path": None,
            "switch_started_at": None,
            "updated_at": ms._now(),
            "error": None,
            "error_detail": None,
            "prod_model_path": None,
        })
    with ms._pull_state_lock:
        ms._pull_state.update({
            "pull_state": "idle",
            "pull_repo": None,
            "pull_filename": None,
            "pull_bytes_downloaded": None,
            "pull_bytes_total": None,
            "pull_pct": None,
            "pull_started_at": None,
            "pull_completed_path": None,
            "pull_error": None,
        })
    yield


@pytest.fixture()
def client():
    # Patch startup event so it doesn't try to connect to Docker
    with patch.object(ms.app.router, "on_startup", []):
        with TestClient(ms.app, raise_server_exceptions=True) as c:
            yield c


# ---------------------------------------------------------------------------
# GET /health

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "prod_model_path" in data


# ---------------------------------------------------------------------------
# GET /status — base fields always present

def test_status_base_fields_idle(client):
    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.json()

    # Switch fields
    assert data["state"] == "ready"
    assert data["switch_elapsed_s"] is None
    assert "switch_timeout_s" in data
    assert data["switch_timeout_s"] == ms._HEALTH_TIMEOUT

    # Pull fields
    assert data["pull_state"] == "idle"
    assert data["pull_repo"] is None
    assert data["pull_filename"] is None
    assert data["pull_bytes_downloaded"] is None
    assert data["pull_bytes_total"] is None
    assert data["pull_pct"] is None
    assert data["pull_started_at"] is None
    assert data["pull_completed_path"] is None
    assert data["pull_error"] is None


def test_status_switch_elapsed_during_loading(client):
    started = ms._now()
    with ms._state_lock:
        ms._state.update({
            "state": "loading",
            "switch_started_at": started,
        })

    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "loading"
    assert data["switch_elapsed_s"] is not None
    assert data["switch_elapsed_s"] >= 0
    assert data["switch_timeout_s"] == ms._HEALTH_TIMEOUT


def test_status_switch_elapsed_null_when_not_loading(client):
    for state in ("ready", "unloading", "unloaded", "error_unknown"):
        with ms._state_lock:
            ms._state["state"] = state
        resp = client.get("/status")
        assert resp.json()["switch_elapsed_s"] is None, f"Expected None for state={state}"


def test_status_shows_pull_state_downloading(client):
    with ms._pull_state_lock:
        ms._pull_state.update({
            "pull_state": "downloading",
            "pull_repo": "org/repo",
            "pull_filename": "model.gguf",
            "pull_bytes_downloaded": 500_000_000,
            "pull_bytes_total": 1_000_000_000,
            "pull_pct": 50.0,
            "pull_started_at": ms._now(),
        })

    resp = client.get("/status")
    data = resp.json()
    assert data["pull_state"] == "downloading"
    assert data["pull_repo"] == "org/repo"
    assert data["pull_filename"] == "model.gguf"
    assert data["pull_bytes_downloaded"] == 500_000_000
    assert data["pull_bytes_total"] == 1_000_000_000
    assert data["pull_pct"] == 50.0


# ---------------------------------------------------------------------------
# POST /pull — async behaviour

def test_pull_returns_202_immediately(client):
    mock_t = MagicMock()
    mock_t.start = MagicMock()
    with (
        patch.object(ms, "_get_hf_file_size", return_value=1_000_000),
        patch.object(ms, "_do_pull"),
        patch("model_switcher.threading.Thread", return_value=mock_t),
    ):
        resp = client.post(
            "/pull",
            json={"hf_repo": "org/repo", "filename": "model.gguf"},
            headers=HEADERS,
        )

    assert resp.status_code == 202
    data = resp.json()
    assert data["pull_state"] == "downloading"
    assert data["pull_repo"] == "org/repo"
    assert data["pull_filename"] == "model.gguf"
    assert data["pull_started_at"] is not None


def test_pull_409_when_pull_already_in_progress(client):
    with ms._pull_state_lock:
        ms._pull_state["pull_state"] = "downloading"

    resp = client.post(
        "/pull",
        json={"hf_repo": "org/repo", "filename": "model.gguf"},
        headers=HEADERS,
    )
    assert resp.status_code == 409
    assert "already in progress" in resp.json()["detail"]


def test_pull_409_when_switch_in_progress(client):
    with ms._state_lock:
        ms._state["state"] = "loading"

    resp = client.post(
        "/pull",
        json={"hf_repo": "org/repo", "filename": "model.gguf"},
        headers=HEADERS,
    )
    assert resp.status_code == 409
    assert "Switch in progress" in resp.json()["detail"]


def test_pull_401_bad_psk(client):
    resp = client.post(
        "/pull",
        json={"hf_repo": "org/repo", "filename": "model.gguf"},
        headers={"x-psk": "wrong"},
    )
    assert resp.status_code == 401


def test_pull_500_no_model_base_dir(client):
    old = ms._MODEL_BASE_DIR
    ms._MODEL_BASE_DIR = ""
    try:
        resp = client.post(
            "/pull",
            json={"hf_repo": "org/repo", "filename": "model.gguf"},
            headers=HEADERS,
        )
        assert resp.status_code == 500
    finally:
        ms._MODEL_BASE_DIR = old


# ---------------------------------------------------------------------------
# _do_pull — background function

def test_do_pull_success():
    result_path = "/tmp/models/model.gguf"
    with (
        patch.object(ms, "_get_hf_file_size", return_value=2_000_000),
        patch.object(ms, "hf_hub_download", return_value=result_path),
    ):
        ms._set_pull_state(
            pull_state="downloading",
            pull_repo="org/repo",
            pull_filename="model.gguf",
            pull_bytes_downloaded=0,
            pull_bytes_total=None,
            pull_pct=None,
            pull_started_at=ms._now(),
            pull_completed_path=None,
            pull_error=None,
        )
        ms._do_pull("org/repo", "model.gguf", None)

    state = ms._get_pull_state()
    assert state["pull_state"] == "complete"
    assert state["pull_completed_path"] == result_path
    assert state["pull_pct"] == 100.0
    assert state["pull_bytes_downloaded"] == 2_000_000


def test_do_pull_failure():
    with (
        patch.object(ms, "_get_hf_file_size", return_value=None),
        patch.object(ms, "hf_hub_download", side_effect=RuntimeError("download failed")),
    ):
        ms._set_pull_state(
            pull_state="downloading",
            pull_repo="org/repo",
            pull_filename="model.gguf",
            pull_bytes_downloaded=0,
            pull_bytes_total=None,
            pull_pct=None,
            pull_started_at=ms._now(),
            pull_completed_path=None,
            pull_error=None,
        )
        ms._do_pull("org/repo", "model.gguf", None)

    state = ms._get_pull_state()
    assert state["pull_state"] == "error_pull_failed"
    assert "download failed" in state["pull_error"]


# ---------------------------------------------------------------------------
# _poll_download_progress

def test_poll_download_progress_updates_bytes(tmp_path):
    model_base = str(tmp_path)
    old_base = ms._MODEL_BASE_DIR
    ms._MODEL_BASE_DIR = model_base

    partial_file = tmp_path / "model.gguf"
    partial_file.write_bytes(b"x" * 512_000)

    ms._set_pull_state(
        pull_state="downloading",
        pull_bytes_total=1_000_000,
        pull_bytes_downloaded=0,
        pull_pct=None,
    )

    stop_event = threading.Event()
    t = threading.Thread(
        target=ms._poll_download_progress,
        args=("model.gguf", stop_event),
        daemon=True,
    )
    t.start()
    time.sleep(0.05)  # first check is immediate; this is enough for one iteration
    stop_event.set()
    t.join(timeout=5)

    state = ms._get_pull_state()
    assert state["pull_bytes_downloaded"] == 512_000
    assert state["pull_pct"] == pytest.approx(51.2, abs=0.1)

    ms._MODEL_BASE_DIR = old_base


# ---------------------------------------------------------------------------
# POST /switch — regression: existing behaviour unchanged

def test_switch_409_when_already_switching(client):
    with ms._state_lock:
        ms._state["state"] = "loading"

    resp = client.post(
        "/switch",
        json={"path": "/mnt/models/model.gguf"},
        headers=HEADERS,
    )
    assert resp.status_code == 409


def test_switch_422_missing_path(client):
    resp = client.post(
        "/switch",
        json={"path": ""},
        headers=HEADERS,
    )
    assert resp.status_code == 422


def test_switch_401_bad_psk(client):
    resp = client.post(
        "/switch",
        json={"path": "/mnt/models/model.gguf"},
        headers={"x-psk": "wrong"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# _get_hf_file_size

def test_get_hf_file_size_returns_size():
    mock_info = MagicMock()
    mock_info.size = 1_234_567
    with patch.object(ms, "HfApi") as MockApi:
        MockApi.return_value.get_paths_info.return_value = [mock_info]
        size = ms._get_hf_file_size("org/repo", "model.gguf", None)
    assert size == 1_234_567


def test_get_hf_file_size_returns_none_on_error():
    with patch.object(ms, "HfApi", side_effect=Exception("network error")):
        size = ms._get_hf_file_size("org/repo", "model.gguf", None)
    assert size is None


def test_get_hf_file_size_returns_none_empty_response():
    with patch.object(ms, "HfApi") as MockApi:
        MockApi.return_value.get_paths_info.return_value = []
        size = ms._get_hf_file_size("org/repo", "model.gguf", None)
    assert size is None
