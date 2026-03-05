import os
import json
import time
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import httpx
from dotenv import load_dotenv

# --- LẤY LOGIC TỪ CÁC MODULE CŨ VÀO ĐÂY ĐỂ VERCEL KHÔNG LỖI ---

try:
    import opengradient as og
    OG_AVAILABLE = True
except ImportError:
    OG_AVAILABLE = False

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── CONFIG ───
OG_PRIVATE_KEY = os.getenv("OG_PRIVATE_KEY", "")
OG_EMAIL       = os.getenv("OG_EMAIL", "")
OG_PASSWORD    = os.getenv("OG_PASSWORD", "")
ANTHROPIC_KEY  = os.getenv("ANTHROPIC_API_KEY", "")

_og_client = None

def get_og_client(pk: str = None):
    """Khởi tạo client OpenGradient"""
    if pk: # Nếu người dùng tự nhập key
        try:
            return og.Client(private_key=pk, email=OG_EMAIL, password=OG_PASSWORD)
        except: return None
    
    global _og_client
    if _og_client is None and OG_AVAILABLE and OG_PRIVATE_KEY:
        try:
            _og_client = og.Client(private_key=OG_PRIVATE_KEY, email=OG_EMAIL, password=OG_PASSWORD)
        except: pass
    return _og_client

# ─── MODELS ───
class AnalysisRequest(BaseModel):
    pair: str = "BTC/USDC"
    timeframe: str = "1H"
    risk: str = "moderate"
    indicators: str = "RSI + MACD + Volume"
    private_key: Optional[str] = None
    inference_mode: str = "VANILLA"

class ReasoningStep(BaseModel):
    step: str
    icon: str
    analysis: str

class SignalResult(BaseModel):
    signal: str
    strength: str
    confidence: int
    target: str
    stop_loss: str
    reasoning: List[ReasoningStep]
    tx_hash: Optional[str] = None
    model_used: str
    inference_mode: str
    timestamp: str
    on_chain_verified: bool

# ─── API ROUTES ───

@app.get("/")
async def serve_home():
    # Trả về giao diện trực tiếp từ Vercel
    if os.path.exists("api/index.html"):
        return FileResponse("api/index.html")
    return {"status": "Frontend file missing", "please": "Check api/index.html"}

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "og": OG_AVAILABLE,
        "wallet": "active" if OG_PRIVATE_KEY else "demo_mode"
    }

@app.get("/api/prices")
async def get_all_prices():
    pairs = ["bitcoin", "ethereum", "solana", "arbitrum", "chainlink"]
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"https://api.coingecko.com/api/v3/simple/price?ids={','.join(pairs)}&vs_currencies=usd&include_24hr_change=true")
            data = r.json()
            mapping = {"bitcoin":"BTC", "ethereum":"ETH", "solana":"SOL", "arbitrum":"ARB", "chainlink":"LINK"}
            res = {}
            for k, v in data.items():
                sym = mapping[k]
                res[f"{sym}/USDC"] = {"price": v["usd"], "price_change_24h": v["usd_24h_change"]}
            return res
        except:
            return {"error": "CoinGecko unreachable"}

@app.post("/api/analyze", response_model=SignalResult)
async def analyze(req: AnalysisRequest):
    # Prompt building logic (simplified for one file)
    prompt = f"Analyze {req.pair} for {req.timeframe} timeframe with {req.risk} risk using {req.indicators}."
    
    tx_hash = None
    raw_response = None
    model_used = "demo-mode"
    on_chain = False

    # 1. Thử OpenGradient
    client = get_og_client(req.private_key)
    if client:
        try:
            inference_mode = og.LlmInferenceMode.TEE if req.inference_mode == "TEE" else og.LlmInferenceMode.VANILLA
            tx_hash, _, message = client.llm_chat(
                model_cid=og.LLM.MISTRAL_7B_INSTRUCT_V3,
                messages=[{"role": "user", "content": prompt}],
                inference_mode=inference_mode
            )
            raw_response = message.get("content", "")
            model_used = "og.Mistral-7B"
            on_chain = True
        except: pass

    # 2. Fallback Claude
    if not raw_response and ANTHROPIC_KEY:
        try:
            async with httpx.AsyncClient() as c:
                r = await c.post("https://api.anthropic.com/v1/messages", 
                    headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01"},
                    json={"model": "claude-3-sonnet-20240229", "max_tokens": 1000, "messages": [{"role": "user", "content": prompt}]}
                )
                raw_response = r.json()["content"][0]["text"]
                model_used = "claude-3-sonnet"
                tx_hash = f"demo-{int(time.time())}"
        except: pass

    # 3. Parse JSON & Return
    if not raw_response:
        raise HTTPException(status_code=500, detail="Inference failed")
    
    try:
        # Simple extraction if it has markdown
        clean = raw_response.strip()
        if "```" in clean:
            import re
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", clean)
            clean = match.group(1).strip() if match else clean
        result = json.loads(clean)
    except:
        # Mock result if parsing fails
        result = {"signal": "HOLD", "strength": "STABLE", "confidence": 70, "target_price": "$0", "stop_loss": "$0", "reasoning_steps": []}

    return SignalResult(
        signal=result.get("signal", "HOLD"),
        strength=result.get("strength", "HOLD"),
        confidence=result.get("confidence", 70),
        target=result.get("target_price", "N/A"),
        stop_loss=result.get("stop_loss", "N/A"),
        reasoning=result.get("reasoning_steps", []),
        tx_hash=tx_hash,
        model_used=model_used,
        inference_mode=req.inference_mode if on_chain else "demo",
        timestamp=datetime.now(timezone.utc).isoformat(),
        on_chain_verified=on_chain
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
