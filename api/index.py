import os
import json
import time
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import httpx
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="OG Signal Vercel")

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
GEMINI_KEY     = os.getenv("GEMINI_API_KEY", "")

_og_client = None
_og_available = None
_og_module = None

def get_og_client(pk: str = None):
    global _og_client, _og_available, _og_module
    
    if _og_available is None:
        try:
            import opengradient as og
            _og_module = og
            _og_available = True
            logger.info("OpenGradient imported.")
        except ImportError:
            _og_available = False
            logger.warning("OpenGradient SDK not found.")

    if not _og_available:
        return None

    # Determine which key to use
    active_pk = pk if pk else OG_PRIVATE_KEY
    if not active_pk:
        return None

    # For global client, cache it
    if not pk and _og_client:
        return _og_client

    try:
        # Initialize with only what's available
        kwargs = {"private_key": active_pk}
        if OG_EMAIL: kwargs["email"] = OG_EMAIL
        if OG_PASSWORD: kwargs["password"] = OG_PASSWORD
        
        client = _og_module.Client(**kwargs)
        
        if not pk: # Cache global client
            _og_client = client
        return client
    except Exception as e: 
        logger.error(f"OG Client init failed: {e}")
        return None

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
    html_path = "og-signal-frontend.html"
    if not os.path.exists(html_path):
        html_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "og-signal-frontend.html")
        
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
        return HTMLResponse(content=content)
    except Exception as e:
        return HTMLResponse(content=f"<h1>Setup Guide</h1><p>Vercel Path: {os.getcwd()}</p><p>Error: {str(e)}</p>")

@app.get("/api/health")
def health():
    return {"status": "ok", "lazy_load": True, "ver": "1.0.2"}

@app.get("/api/prices")
async def get_all_prices():
    pairs = ["bitcoin", "ethereum", "solana", "arbitrum", "chainlink"]
    async with httpx.AsyncClient(timeout=10) as client:
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
            return {"BTC/USDC": {"price": 65000, "price_change_24h": 0}}

@app.post("/api/analyze", response_model=SignalResult)
async def analyze(req: AnalysisRequest):
    prompt = f"""Analyze {req.pair} for {req.timeframe} timeframe with {req.risk} risk using {req.indicators}.
Respond strictly with a JSON object. The JSON must contain these exact keys:
"signal": "BUY", "SELL", or "HOLD"
"strength": "STRONG", "STABLE", or "WEAK"
"confidence": integer between 1-100 indicating percentage confidence
"target_price": string (e.g. "$70k")
"stop_loss": string (e.g. "$60k")
"reasoning_steps": an array of objects, where each object has "step" (string), "icon" (string emoji like 📊), and "analysis" (string).
Do NOT include markdown block markers (like ```json), just the raw JSON object. Make sure the JSON is valid."""
    tx_hash = None
    raw_response = None
    model_used = "demo-mode"
    on_chain = False

    # 1. Primary Analysis: OpenGradient
    og_error = None
    start_time = time.time()
    
    # Check if SDK is available
    client = get_og_client(req.private_key)
    if not _og_available:
        og_error = "OpenGradient SDK not found in environment (check requirements.txt)"
    elif not client:
        # Detailed feedback on why initialization failed
        has_server_key = bool(OG_PRIVATE_KEY)
        has_user_key = bool(req.private_key)
        
        if not has_user_key and not has_server_key:
            og_error = "No Private Key found (Server Key is missing in Vercel Env AND Sidebar is empty)."
        elif has_user_key or has_server_key:
            og_error = f"Client init failed. (Server Key: {'Yes' if has_server_key else 'No'}, User Key: {'Yes' if has_user_key else 'No'}). Please check Key validity and $OPG balance."
    
    if client and _og_module:
        try:
            inference_mode = _og_module.LlmInferenceMode.TEE if req.inference_mode == "TEE" else _og_module.LlmInferenceMode.VANILLA
            tx_hash_og, _, message = client.llm_chat(
                model_cid=_og_module.LLM.MISTRAL_7B_INSTRUCT_V3,
                messages=[{"role": "user", "content": prompt}],
                inference_mode=inference_mode
            )
            raw_response = message.get("content", "")
            if raw_response:
                model_used = "og.Mistral-7B"
                tx_hash = tx_hash_og
                on_chain = True
            else:
                og_error = "OpenGradient returned empty response (Check $OPG balance)"
        except Exception as e:
            og_error = f"OpenGradient API Error: {str(e)}"
            logger.error(og_error)

    # Use a safe rounding or float formatting
    og_duration = float(f"{(time.time() - start_time):.2f}")
    logger.info(f"OpenGradient took {og_duration} seconds")

    # 2. Fallback Google Gemini
    if not raw_response and GEMINI_KEY:
        try:
            async with httpx.AsyncClient(timeout=30) as c:
                r = await c.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}", 
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts":[{"text": prompt}]}]}
                )
                if r.status_code == 200:
                    data = r.json()
                    if "candidates" in data:
                        raw_response = data["candidates"][0]["content"]["parts"][0]["text"]
                        model_used = "gemini-2.5-flash"
                        tx_hash = f"demo-{int(time.time())}"
                    else:
                        gemini_err = "No candidates in response: " + r.text
                else:
                    gemini_err = f"API Error {r.status_code}: {r.text}"
        except Exception as e:
            logger.error(f"Gemini Fallback Error: {e}")
            if 'gemini_err' not in locals():
                gemini_err = str(e)
    if not raw_response:
        msg = f"Could not connect to external AIs. Gemini Error: {gemini_err}" if 'gemini_err' in locals() else "Could not connect to external AIs."
        raw_response = json.dumps({
            "target_price": "$70k", "stop_loss": "$60k", 
            "reasoning_steps": [
                {"step": "OpenGradient Analysis", "icon": "❌" if og_error else "✅", "analysis": og_error if og_error else f"Completed in {og_duration}s"},
                {"step": "Gemini Fallback", "icon": "⚠️", "analysis": msg}
            ]
        })

    try:
        clean = raw_response.strip()
        if "```" in clean:
            import re
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", clean)
            clean = match.group(1).strip() if match else clean
        result = json.loads(clean)
    except:
        result = {"signal": "HOLD", "strength": "STABLE", "confidence": 70, "target_price": "$0", "stop_loss": "$0", "reasoning_steps": []}

    final_reasoning = result.get("reasoning_steps", [])
    if not isinstance(final_reasoning, list):
        final_reasoning = [{"step": "Analysis Details", "icon": "📝", "analysis": str(final_reasoning)}]
        
    # Chèn trạng thái OpenGradient vào đầu danh sách để người dùng biết tình trạng
    og_status_step = {
        "step": "OpenGradient Analysis", 
        "icon": "❌" if og_error else "✅", 
        "analysis": og_error if og_error else f"Completed successfully in {og_duration}s"
    }
    final_reasoning.insert(0, og_status_step)

    return SignalResult(
        signal=result.get("signal", "HOLD"),
        strength=result.get("strength", "HOLD"),
        confidence=result.get("confidence", 70),
        target=result.get("target_price", "N/A"),
        stop_loss=result.get("stop_loss", "N/A"),
        reasoning=final_reasoning,
        tx_hash=tx_hash,
        model_used=model_used,
        inference_mode=req.inference_mode if on_chain else "demo",
        timestamp=datetime.now(timezone.utc).isoformat(),
        on_chain_verified=on_chain
    )
