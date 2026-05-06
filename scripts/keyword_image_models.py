"""
關鍵詞生圖 — 多模型同時生成
==========================
3 個模型同時接收關鍵詞，一起生圖。

模型:
  1. OpenAI DALL-E 3
  2. Google Imagen 3 (via Gemini)
  3. NVIDIA NIM (Flux)

架構:
  HTML 前端 → FastAPI 後端 → 3 個模型同時呼叫 → 回傳圖片
"""

import os
import asyncio
import base64
import time
import json
import httpx
from pathlib import Path
from datetime import datetime

# ─── 載入 API Keys ───────────────────────────────────────
def load_env():
    env_path = Path.home() / "projects" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

load_env()

OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")
GOOGLE_KEY = os.environ.get("GOOGLE_API_KEY", "")
NVIDIA_KEY = os.environ.get("NVIDIA_API_KEY", "")


# ══════════════════════════════════════════════════════════
#  模型 1: OpenAI DALL-E 3
# ══════════════════════════════════════════════════════════

async def generate_dalle(prompt: str) -> dict:
    """用 DALL-E 3 生圖"""
    if not OPENAI_KEY:
        return {"model": "DALL-E 3", "error": "No API key", "image": None}
    
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "dall-e-3",
                    "prompt": prompt,
                    "n": 1,
                    "size": "1024x1024",
                    "response_format": "b64_json"
                }
            )
            
            if resp.status_code == 200:
                data = resp.json()
                img_b64 = data["data"][0]["b64_json"]
                return {
                    "model": "DALL-E 3",
                    "image": f"data:image/png;base64,{img_b64}",
                    "time": round(time.time() - start, 1),
                    "revised_prompt": data["data"][0].get("revised_prompt", ""),
                    "error": None
                }
            else:
                return {"model": "DALL-E 3", "error": f"HTTP {resp.status_code}: {resp.text[:200]}", "image": None}
    except Exception as e:
        return {"model": "DALL-E 3", "error": str(e), "image": None}


# ══════════════════════════════════════════════════════════
#  模型 2: Google Imagen 3 (via Gemini API)
# ══════════════════════════════════════════════════════════

async def generate_imagen(prompt: str) -> dict:
    """用 Google Imagen 3 生圖"""
    if not GOOGLE_KEY:
        return {"model": "Imagen 3", "error": "No API key", "image": None}
    
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            # 用 Gemini 的 imagen-3.0-generate-002 模型
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={GOOGLE_KEY}",
                headers={"Content-Type": "application/json"},
                json={
                    "instances": [{"prompt": prompt}],
                    "parameters": {"sampleCount": 1}
                }
            )
            
            if resp.status_code == 200:
                data = resp.json()
                predictions = data.get("predictions", [])
                if predictions:
                    img_b64 = predictions[0].get("bytesBase64Encoded", "")
                    mime = predictions[0].get("mimeType", "image/png")
                    return {
                        "model": "Imagen 3",
                        "image": f"data:{mime};base64,{img_b64}",
                        "time": round(time.time() - start, 1),
                        "error": None
                    }
                else:
                    return {"model": "Imagen 3", "error": "No predictions returned", "image": None}
            else:
                return {"model": "Imagen 3", "error": f"HTTP {resp.status_code}: {resp.text[:200]}", "image": None}
    except Exception as e:
        return {"model": "Imagen 3", "error": str(e), "image": None}


# ══════════════════════════════════════════════════════════
#  模型 3: NVIDIA NIM (Flux)
# ══════════════════════════════════════════════════════════

async def generate_flux(prompt: str) -> dict:
    """用 NVIDIA NIM 的 Flux 模型生圖"""
    if not NVIDIA_KEY:
        return {"model": "Flux (NIM)", "error": "No API key", "image": None}
    
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux-schnell",
                headers={
                    "Authorization": f"Bearer {NVIDIA_KEY}",
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                json={
                    "prompt": prompt,
                    "seed": 0,
                    "steps": 4,
                    "width": 1024,
                    "height": 1024
                }
            )
            
            if resp.status_code == 200:
                data = resp.json()
                artifacts = data.get("artifacts", [])
                if artifacts:
                    img_b64 = artifacts[0].get("base64", "")
                    return {
                        "model": "Flux (NIM)",
                        "image": f"data:image/png;base64,{img_b64}",
                        "time": round(time.time() - start, 1),
                        "error": None
                    }
                else:
                    return {"model": "Flux (NIM)", "error": "No artifacts returned", "image": None}
            else:
                return {"model": "Flux (NIM)", "error": f"HTTP {resp.status_code}: {resp.text[:200]}", "image": None}
    except Exception as e:
        return {"model": "Flux (NIM)", "error": str(e), "image": None}


# ══════════════════════════════════════════════════════════
#  同時呼叫 3 個模型
# ══════════════════════════════════════════════════════════

async def generate_all(prompt: str) -> dict:
    """同時呼叫 3 個模型生圖"""
    start = time.time()
    
    results = await asyncio.gather(
        generate_dalle(prompt),
        generate_imagen(prompt),
        generate_flux(prompt),
        return_exceptions=True
    )
    
    # 處理例外
    processed = []
    for r in results:
        if isinstance(r, Exception):
            processed.append({"model": "unknown", "error": str(r), "image": None})
        else:
            processed.append(r)
    
    return {
        "prompt": prompt,
        "timestamp": datetime.now().isoformat(),
        "total_time": round(time.time() - start, 1),
        "results": processed
    }
