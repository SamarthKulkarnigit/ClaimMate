"""Central config. Reads .env from the repo root."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE_DIR = ROOT / "cache"
UPLOADS = DATA / "uploads"
OUTPUTS = ROOT / "outputs"

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:  # dotenv is optional
    pass

OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "https://ollama.com")

# Model choices (override in .env without touching code)
VISION_MODELS = [m.strip() for m in os.getenv(
    "VISION_MODELS", "gemma4:31b,mistral-large-3:675b,kimi-k3").split(",") if m.strip()]
TEXT_MODELS = [m.strip() for m in os.getenv(
    "TEXT_MODELS", "gpt-oss:120b,deepseek-v4.1-flash").split(",") if m.strip()]
FAST_MODELS = [m.strip() for m in os.getenv(
    "FAST_MODELS", "gpt-oss:20b,glm-5.3-flash").split(",") if m.strip()]

# LLM_MOCK=1 -> no network calls; agents use the "mock" block in demo claim.json
LLM_MOCK = os.getenv("LLM_MOCK", "0") == "1"
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "180"))

MAX_SEND_BACKS = int(os.getenv("MAX_SEND_BACKS", "1"))  # auditor send-backs before escalation
LOW_CONFIDENCE = 0.6

for d in (CACHE_DIR, UPLOADS, OUTPUTS):
    d.mkdir(parents=True, exist_ok=True)
