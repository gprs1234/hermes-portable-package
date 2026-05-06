"""
關鍵詞生圖 Server（無依賴版）
==============================
用 Python 內建 http.server，不需要安裝任何套件。

啟動: python3 server.py
網址: http://localhost:8888
"""

import http.server
import json
import asyncio
import os
import time
from pathlib import Path
from datetime import datetime
from urllib.parse import parse_qs

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


# ─── 生圖函式（用 urllib，不依賴 httpx）────────────────────

def http_post(url, headers, body, timeout=60):
    """用 urllib 發 POST 請求"""
    import urllib.request
    import ssl
    
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8")), resp.status
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode("utf-8")[:500]}, e.code
    except Exception as e:
        return {"error": str(e)}, 0


def generate_dalle(prompt):
    """DALL-E 3"""
    if not OPENAI_KEY:
        return {"model": "DALL-E 3", "error": "No API key", "image": None}
    
    start = time.time()
    result, status = http_post(
        "https://api.openai.com/v1/images/generations",
        {"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
        {"model": "dall-e-3", "prompt": prompt, "n": 1, "size": "1024x1024", "response_format": "b64_json"}
    )
    
    if status == 200 and "data" in result:
        img_b64 = result["data"][0].get("b64_json", "")
        return {
            "model": "DALL-E 3",
            "image": f"data:image/png;base64,{img_b64}",
            "time": round(time.time() - start, 1),
            "error": None
        }
    return {"model": "DALL-E 3", "error": result.get("error", f"HTTP {status}")[:200], "image": None}


def generate_imagen(prompt):
    """Google Imagen 3"""
    if not GOOGLE_KEY:
        return {"model": "Imagen 3", "error": "No API key", "image": None}
    
    start = time.time()
    result, status = http_post(
        f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict?key={GOOGLE_KEY}",
        {"Content-Type": "application/json"},
        {"instances": [{"prompt": prompt}], "parameters": {"sampleCount": 1}}
    )
    
    if status == 200:
        predictions = result.get("predictions", [])
        if predictions:
            img_b64 = predictions[0].get("bytesBase64Encoded", "")
            mime = predictions[0].get("mimeType", "image/png")
            return {
                "model": "Imagen 3",
                "image": f"data:{mime};base64,{img_b64}",
                "time": round(time.time() - start, 1),
                "error": None
            }
    return {"model": "Imagen 3", "error": result.get("error", f"HTTP {status}")[:200], "image": None}


def generate_flux(prompt):
    """NVIDIA NIM Flux"""
    if not NVIDIA_KEY:
        return {"model": "Flux (NIM)", "error": "No API key", "image": None}
    
    start = time.time()
    result, status = http_post(
        "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux-schnell",
        {
            "Authorization": f"Bearer {NVIDIA_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        {"prompt": prompt, "seed": 0, "steps": 4, "width": 1024, "height": 1024}
    )
    
    if status == 200:
        artifacts = result.get("artifacts", [])
        if artifacts:
            img_b64 = artifacts[0].get("base64", "")
            return {
                "model": "Flux (NIM)",
                "image": f"data:image/png;base64,{img_b64}",
                "time": round(time.time() - start, 1),
                "error": None
            }
    return {"model": "Flux (NIM)", "error": result.get("error", f"HTTP {status}")[:200], "image": None}


def generate_all(prompt):
    """依序呼叫 3 個模型（Python 內建不支援 async，改用依序）"""
    start = time.time()
    results = [
        generate_dalle(prompt),
        generate_imagen(prompt),
        generate_flux(prompt),
    ]
    return {
        "prompt": prompt,
        "timestamp": datetime.now().isoformat(),
        "total_time": round(time.time() - start, 1),
        "results": results
    }


# ─── HTTP Server ─────────────────────────────────────────

class ImageGenHandler(http.server.SimpleHTTPRequestHandler):
    
    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            html = (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")
            self.wfile.write(html.encode("utf-8"))
        
        elif self.path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            health = {
                "status": "ok",
                "models": {
                    "dalle": bool(OPENAI_KEY),
                    "imagen": bool(GOOGLE_KEY),
                    "flux": bool(NVIDIA_KEY)
                }
            }
            self.wfile.write(json.dumps(health).encode("utf-8"))
        
        else:
            self.send_error(404)
    
    def do_POST(self):
        if self.path == "/api/generate":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            
            try:
                data = json.loads(body)
                prompt = data.get("prompt", "").strip()
                
                if not prompt:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "請輸入關鍵詞"}).encode("utf-8"))
                    return
                
                result = generate_all(prompt)
                
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
            
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        else:
            self.send_error(404)
    
    def log_message(self, format, *args):
        """自訂日誌格式"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {args[0]}")


if __name__ == "__main__":
    PORT = 8888
    print(f"🎨 關鍵詞生圖 Server 啟動中...")
    print(f"   網址: http://0.0.0.0:{PORT}")
    print(f"   DALL-E 3: {'✅' if OPENAI_KEY else '❌'}")
    print(f"   Imagen 3: {'✅' if GOOGLE_KEY else '❌'}")
    print(f"   Flux NIM: {'✅' if NVIDIA_KEY else '❌'}")
    
    server = http.server.HTTPServer(("0.0.0.0", PORT), ImageGenHandler)
    server.serve_forever()
