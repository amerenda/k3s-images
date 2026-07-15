"""imggen — LiteLLM-compatible image generation proxy.

Receives OpenAI chat completions requests, expands the user prompt via
qwen3:14b on archlinux, generates an image via ComfyUI on murderbot,
and returns the image as a base64 data URI embedded in markdown.

Supports both streaming (SSE) and non-streaming responses. OWU and most
clients send stream=true; this service sends progress chunks to keep the
connection alive during the ~90s generation time.
"""
import asyncio
import base64
import json
import logging
import os
import random
import time
import uuid

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

COMFYUI_URL = os.getenv("COMFYUI_URL", "http://10.100.20.19:8188")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://10.100.20.25:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:14b")
LANGFUSE_BASE_URL = os.getenv("LANGFUSE_BASE_URL", "https://langfuse.amer.dev")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_PROMPT_NAME = os.getenv("LANGFUSE_PROMPT_NAME", "imggen-expansion-system")
COMFYUI_POLL_INTERVAL = float(os.getenv("COMFYUI_POLL_INTERVAL", "2"))

_LOGGING_MODE = os.getenv("LOGGING_MODE", "none").lower()
if _LOGGING_MODE not in ("none", "full"):
    raise RuntimeError(f"LOGGING_MODE must be 'none' or 'full', got {_LOGGING_MODE!r}")
_LOG_USER_DATA = _LOGGING_MODE == "full"
COMFYUI_TIMEOUT = float(os.getenv("COMFYUI_TIMEOUT", "300"))

_sessions: dict[str, dict] = {}
_system_prompt_cache: str | None = None

app = FastAPI(title="imggen")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

FALLBACK_SYSTEM_PROMPT = (
    "You are a FLUX image generation prompt engineer specializing in photorealistic human "
    "photography. Expand the given description into a detailed FLUX prompt using natural "
    "prose sentences. Output exactly three lines:\n"
    "POSITIVE: <expanded prompt>\nNEGATIVE: <negative prompt>\nSEED: <random integer>"
)


async def get_system_prompt() -> str:
    global _system_prompt_cache
    if _system_prompt_cache:
        return _system_prompt_cache
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{LANGFUSE_BASE_URL}/api/public/v2/prompts/{LANGFUSE_PROMPT_NAME}",
                auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
            )
            resp.raise_for_status()
            data = resp.json()
            _system_prompt_cache = data["prompt"]
            log.info("Loaded Langfuse prompt %s v%s", LANGFUSE_PROMPT_NAME, data.get("version"))
            return _system_prompt_cache
    except Exception as exc:
        log.warning("Langfuse prompt fetch failed (%s), using fallback", exc)
        return FALLBACK_SYSTEM_PROMPT


async def expand_prompt(description: str, prev_context: str | None, system_prompt: str) -> tuple[str, str, int]:
    messages = [{"role": "system", "content": system_prompt}]
    if prev_context:
        messages.append({
            "role": "user",
            "content": f"Previous expanded prompt:\n{prev_context}\n\nModification request:\n{description}",
        })
    else:
        messages.append({"role": "user", "content": description})

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"num_ctx": 4096, "temperature": 0.7},
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{OLLAMA_URL}/v1/chat/completions", json=payload)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

    positive = negative = ""
    seed = random.randint(1, 2147483647)

    for line in content.splitlines():
        line = line.strip()
        if line.upper().startswith("POSITIVE:"):
            positive = line[9:].strip()
        elif line.upper().startswith("NEGATIVE:"):
            negative = line[9:].strip()
        elif line.upper().startswith("SEED:"):
            try:
                seed = int(line[5:].strip())
            except ValueError:
                pass

    if not positive:
        positive = description

    if not negative:
        negative = (
            "deformed hands, extra fingers, fused fingers, missing fingers, bad anatomy, "
            "distorted proportions, blurry, overexposed, cartoon, illustration, watermark, "
            "text, low quality"
        )

    return positive, negative, seed


def build_workflow(positive: str, negative: str, seed: int, width: int = 1024, height: int = 1024) -> dict:
    return {
        # --- Model loading ---
        "1": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "fluxedUpFluxNSFW_90FP8.safetensors",
                "weight_dtype": "fp8_e4m3fn",
            },
        },
        "2": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["1", 0],
                "lora_name": "klein_anatomy_fixer.safetensors",
                "strength_model": 0.7,
            },
        },
        "3": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["2", 0],
                "lora_name": "Flux_Skin_Texture_V2.safetensors",
                "strength_model": 0.6,
            },
        },
        "4": {
            "class_type": "LoraLoaderModelOnly",
            "inputs": {
                "model": ["3", 0],
                "lora_name": "Flux_Portrait_Realism.safetensors",
                "strength_model": 0.5,
            },
        },
        "5": {
            "class_type": "DualCLIPLoader",
            "inputs": {
                "clip_name1": "clip_l.safetensors",
                "clip_name2": "t5xxl_fp8_e4m3fn.safetensors",
                "type": "flux",
            },
        },
        "6": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "ae.safetensors"},
        },
        # --- Text encoding ---
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": positive, "clip": ["5", 0]},
        },
        "8": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative, "clip": ["5", 0]},
        },
        # --- Generation ---
        "9": {
            "class_type": "EmptySD3LatentImage",
            "inputs": {"width": width, "height": height, "batch_size": 1},
        },
        "10": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["4", 0],
                "positive": ["7", 0],
                "negative": ["8", 0],
                "latent_image": ["9", 0],
                "seed": seed,
                "steps": 30,
                "cfg": 1.0,
                "sampler_name": "dpmpp_2m",
                "scheduler": "karras",
                "denoise": 1.0,
            },
        },
        "11": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["10", 0], "vae": ["6", 0]},
        },
        # --- ESRGAN 4x upscale then downscale to 2048 for streaming ---
        # Full 4096 is also saved (imggen_hq prefix) for ComfyUI History access.
        # Both live in the container tmpfs — never written to disk.
        "13": {
            "class_type": "UpscaleModelLoader",
            "inputs": {"model_name": "4x_NMKD-Siax_200k.pth"},
        },
        "14": {
            "class_type": "ImageUpscaleWithModel",
            "inputs": {"upscale_model": ["13", 0], "image": ["11", 0]},
        },
        # Full 4096×4096 HQ copy — viewable/downloadable via ComfyUI History tab
        "16": {
            "class_type": "SaveImage",
            "inputs": {"images": ["14", 0], "filename_prefix": "imggen_hq"},
        },
        # 2048×2048 downscaled version — streamed to OWU as base64
        "15": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["14", 0],
                "upscale_method": "lanczos",
                "width": 2048,
                "height": 2048,
                "crop": "disabled",
            },
        },
        "12": {
            "class_type": "SaveImage",
            "inputs": {"images": ["15", 0], "filename_prefix": "imggen"},
        },
    }


async def generate_image(positive: str, negative: str, seed: int) -> bytes:
    workflow = build_workflow(positive, negative, seed)
    client_id = str(uuid.uuid4())

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{COMFYUI_URL}/prompt",
                json={"prompt": workflow, "client_id": client_id},
            )
    except httpx.ConnectError:
        raise HTTPException(
            503,
            "ComfyUI is not reachable. Switch to image mode first: run switch-llm-to-image.sh",
        )

    if resp.status_code != 200:
        raise HTTPException(503, f"ComfyUI rejected prompt: {resp.status_code} {resp.text[:200]}")

    prompt_id = resp.json()["prompt_id"]
    log.info("ComfyUI prompt submitted: %s seed=%d", prompt_id, seed)

    deadline = time.time() + COMFYUI_TIMEOUT
    async with httpx.AsyncClient(timeout=15) as client:
        while time.time() < deadline:
            await asyncio.sleep(COMFYUI_POLL_INTERVAL)
            try:
                hist = await client.get(f"{COMFYUI_URL}/history/{prompt_id}")
            except Exception:
                continue
            if hist.status_code != 200:
                continue
            data = hist.json()
            if prompt_id not in data:
                continue

            status_data = data[prompt_id].get("status", {})
            if status_data.get("status_str") == "error":
                msgs = status_data.get("messages", [])
                raise HTTPException(500, f"ComfyUI error: {msgs}")

            for node_out in data[prompt_id].get("outputs", {}).values():
                for img_info in node_out.get("images", []):
                    img_resp = await client.get(
                        f"{COMFYUI_URL}/view",
                        params={
                            "filename": img_info["filename"],
                            "subfolder": img_info.get("subfolder", ""),
                            "type": "output",
                        },
                    )
                    img_resp.raise_for_status()
                    log.info("Image downloaded: %s (%d bytes)", img_info["filename"], len(img_resp.content))
                    return img_resp.content

    raise HTTPException(504, f"ComfyUI generation timed out after {int(COMFYUI_TIMEOUT)}s")


def _sse_chunk(content: str, chunk_id: str, finish_reason=None) -> str:
    delta = {"content": content} if content else {"role": "assistant", "content": ""}
    chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "model": "image-gen",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(chunk)}\n\n"


async def _stream_generate(user_msg: str, conv_id: str, session: dict):
    chunk_id = f"imggen-{uuid.uuid4().hex[:8]}"

    yield _sse_chunk("", chunk_id)
    yield _sse_chunk("*Expanding prompt...*", chunk_id)

    system_prompt = await get_system_prompt()
    prev_context = None
    if session:
        prev_context = (
            f"POSITIVE: {session['positive']}\n"
            f"NEGATIVE: {session['negative']}\n"
            f"SEED: {session['seed']}"
        )

    try:
        positive, negative, seed = await expand_prompt(user_msg, prev_context, system_prompt)
        if _LOG_USER_DATA:
            log.info("Expanded prompt seed=%d: %s...", seed, positive[:80])
        yield _sse_chunk(f"\n*Generating image (seed `{seed}`)...*", chunk_id)
    except Exception as exc:
        log.error("Prompt expansion failed: %s — using raw description", exc)
        positive = user_msg
        negative = "deformed hands, extra fingers, bad anatomy, blurry, watermark, low quality"
        seed = random.randint(1, 2147483647)
        yield _sse_chunk(f"\n*Prompt expansion failed, using raw prompt (seed `{seed}`)...*", chunk_id)

    try:
        image_bytes = await generate_image(positive, negative, seed)
    except HTTPException as exc:
        yield _sse_chunk(f"\n\n**Error:** {exc.detail}", chunk_id)
        yield _sse_chunk("", chunk_id, finish_reason="stop")
        yield "data: [DONE]\n\n"
        return

    _sessions[conv_id] = {"positive": positive, "negative": negative, "seed": seed}

    b64 = base64.b64encode(image_bytes).decode()
    content = (
        f"\n\n![generated image](data:image/png;base64,{b64})\n\n"
        f"**Seed:** `{seed}`  \n"
        f"**Prompt:** {positive[:300]}{'…' if len(positive) > 300 else ''}"
    )

    # Send in chunks to avoid buffering the full 2MB base64 string at once
    chunk_size = 8192
    for i in range(0, len(content), chunk_size):
        yield _sse_chunk(content[i:i + chunk_size], chunk_id)

    yield _sse_chunk("", chunk_id, finish_reason="stop")
    yield "data: [DONE]\n\n"


@app.get("/health")
async def health():
    return {"status": "ok", "service": "imggen"}


@app.get("/status", response_class=HTMLResponse)
async def status_page():
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{COMFYUI_URL}/system_stats")
        comfy_up = r.status_code == 200
    except Exception:
        comfy_up = False

    color = "#22c55e" if comfy_up else "#6b7280"
    mode = "IMAGE MODE" if comfy_up else "LLM MODE"
    subtitle = "ComfyUI running — image generation active" if comfy_up else "ComfyUI offline — LLM is active"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>imggen status</title>
  <meta http-equiv="refresh" content="10">
  <style>
    body {{
      background: #111; display: flex; align-items: center;
      justify-content: center; height: 100vh; margin: 0;
      font-family: 'SF Mono', monospace;
    }}
    .card {{
      text-align: center; padding: 48px 96px;
      background: {color}; border-radius: 20px;
      box-shadow: 0 0 60px {color}88;
    }}
    .mode {{ font-size: 52px; font-weight: 700; color: white; letter-spacing: 2px; }}
    .sub {{ font-size: 18px; color: rgba(255,255,255,0.75); margin-top: 14px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="mode">{mode}</div>
    <div class="sub">{subtitle}</div>
  </div>
</body>
</html>"""


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(400, "No messages")

    conv_id = body.get("user") or body.get("conversation_id") or "default"
    session = _sessions.get(conv_id, {})

    user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_msg = m.get("content", "")
            if isinstance(user_msg, list):
                user_msg = " ".join(p.get("text", "") for p in user_msg if isinstance(p, dict))
            break

    if not user_msg:
        raise HTTPException(400, "No user message found")

    if _LOG_USER_DATA:
        log.info("conv=%s: %s", conv_id, user_msg[:100])
    else:
        log.info("conv=%s: [redacted — LOGGING_MODE=none]", conv_id)

    if body.get("stream", False):
        return StreamingResponse(
            _stream_generate(user_msg, conv_id, session),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )

    # Non-streaming path
    system_prompt = await get_system_prompt()
    prev_context = None
    if session:
        prev_context = (
            f"POSITIVE: {session['positive']}\n"
            f"NEGATIVE: {session['negative']}\n"
            f"SEED: {session['seed']}"
        )

    try:
        positive, negative, seed = await expand_prompt(user_msg, prev_context, system_prompt)
        if _LOG_USER_DATA:
            log.info("Expanded prompt seed=%d: %s...", seed, positive[:80])
    except Exception as exc:
        log.error("Prompt expansion failed: %s — using raw description", exc)
        positive = user_msg
        negative = "deformed hands, extra fingers, bad anatomy, blurry, watermark, low quality"
        seed = random.randint(1, 2147483647)

    image_bytes = await generate_image(positive, negative, seed)
    _sessions[conv_id] = {"positive": positive, "negative": negative, "seed": seed}

    b64 = base64.b64encode(image_bytes).decode()
    content = (
        f"![generated image](data:image/png;base64,{b64})\n\n"
        f"**Seed:** `{seed}`  \n"
        f"**Prompt:** {positive[:300]}{'…' if len(positive) > 300 else ''}"
    )

    return JSONResponse({
        "id": f"imggen-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "model": "image-gen",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    })
