"""
OG Signal - AI Trading Signal Bot
Backend: Optimized FastAPI server with modular components
"""

import os
import json
import time
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx
from dotenv import load_dotenv

# Import modular components
from core.og_client import OGClient
from services.price_feed import PriceFeedService

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = FastAPI(title="OG Signal API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── CONFIG & SERVICES ───
OG_PRIVATE_KEY = os.getenv("OG_PRIVATE_KEY", "")
OG_EMAIL       = os.getenv("OG_EMAIL", "")
OG_PASSWORD    = os.getenv("OG_PASSWORD", "")

# Initialize services (Price feed stays global)
price_service = PriceFeedService(cache_ttl=300)
_og_client = None

def get_og_client():
    """Lazily initialize OG client to avoid cold start timeouts"""
    global _og_client
    if _og_client is None and OG_PRIVATE_KEY:
        try:
            _og_client = OGClient(
                private_key=OG_PRIVATE_KEY,
                email=OG_EMAIL,
                password=OG_PASSWORD
            )
            logger.info("✅ OpenGradient Client initialized lazily")
        except Exception as e:
            logger.error(f"⚠️ Lazy OG init failed: {e}")
    return _og_client

# ─── MODELS ───
class AnalysisRequest(BaseModel):
    pair: str = Field(default="BTC/USDC", description="Trading pair to analyze")
    timeframe: str = Field(default="1H", description="Timeframe for analysis")
    risk: str = Field(default="moderate", description="Risk tolerance level")
    indicators: str = Field(default="RSI + MACD + Volume", description="Indicators to use")
    private_key: Optional[str] = Field(default=None, description="Optional user private key")
    inference_mode: str = Field(default="VANILLA", description="Inference mode (VANILLA or TEE)")

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

# ─── UTILS ───
def build_analysis_prompt(pair: str, timeframe: str, risk: str, indicators: str, price_data: Dict[str, Any]) -> str:
    """Build a detailed prompt for trading signal analysis"""
    price = price_data.get("price", "N/A")
    change_24h = price_data.get("price_change_24h", 0)
    change_7d  = price_data.get("price_change_7d", 0)
    vol        = price_data.get("volume_24h", 0)
    high       = price_data.get("high_24h", 0)
    low        = price_data.get("low_24h", 0)

    ohlc_summary = ""
    if price_data.get("ohlc_7d"):
        ohlc = price_data["ohlc_7d"]
        opens  = [c[1] for c in ohlc]
        highs  = [c[2] for c in ohlc]
        lows   = [c[3] for c in ohlc]
        closes = [c[4] for c in ohlc]
        trend = "↑ Uptrend" if closes[-1] > closes[0] else "↓ Downtrend"
        perf = ((closes[-1]-closes[0])/closes[0]*100)
        ohlc_summary = f"""
Recent OHLC (last {len(ohlc)} candles):
- Opens range: ${min(opens):,.0f} - ${max(opens):,.0f}
- Highs range: ${min(highs):,.0f} - ${max(highs):,.0f}
- Lows range:  ${min(lows):,.0f} - ${max(lows):,.0f}
- Trend: {trend} (close moved {perf:+.1f}%)
"""

    return f"""You are an expert crypto quant analyst. Analyze the following market data and produce a detailed trading signal.

=== MARKET DATA (LIVE) ===
Pair: {pair}
Current Price: ${price:,.2f}
24H Change: {change_24h:+.2f}%
7D Change: {change_7d:+.2f}%
24H Volume: ${vol:,.0f}
24H High: ${high:,.2f}
24H Low: ${low:,.2f}
{ohlc_summary}

=== ANALYSIS PARAMETERS ===
Timeframe: {timeframe}
Risk Tolerance: {risk}
Indicators: {indicators}

=== INSTRUCTIONS ===
Analyze the data above and respond ONLY with a valid JSON object (no markdown):

{{
  "signal": "BUY" | "SELL" | "HOLD",
  "strength": "STRONG BUY" | "BUY" | "HOLD" | "SELL" | "STRONG SELL",
  "confidence": <integer 55-95>,
  "target_price": "<price with $ sign>",
  "stop_loss": "<price with $ sign>",
  "reasoning_steps": [
    {{ "step": "MARKET CONTEXT", "icon": "🌐", "analysis": "..." }},
    {{ "step": "TECHNICAL ANALYSIS", "icon": "📊", "analysis": "..." }},
    {{ "step": "VOLUME & MOMENTUM", "icon": "⚡", "analysis": "..." }},
    {{ "step": "RISK ASSESSMENT", "icon": "🛡", "analysis": "..." }},
    {{ "step": "SIGNAL VERDICT", "icon": "🎯", "analysis": "..." }}
  ]
}}"""

# ─── API ROUTES ───

@app.get("/")
def root():
    client = get_og_client()
    return {
        "app": "OG Signal",
        "version": "0.2.1 (Vercel-Optimized)",
        "og_initialized": client is not None,
        "docs": "https://docs.opengradient.ai/developers/sdk/",
    }

@app.get("/api/health")
def health():
    client = get_og_client()
    return {
        "status": "ok",
        "og_client": "initialized" if client else "waiting_or_failed",
        "network": "Base Sepolia (testnet)",
        "token": "$OPG",
    }

@app.get("/api/price/{pair}")
async def get_price(pair: str):
    base = pair.replace("-", "/").split("/")[0].upper()
    data = await price_service.get_price_data(base)
    return {"pair": pair.replace("-", "/").upper(), "data": data}

@app.get("/api/prices")
async def get_all_prices():
    pairs = ["BTC", "ETH", "SOL", "ARB", "LINK"]
    results = {}
    tasks = [price_service.get_price_data(p) for p in pairs]
    data_list = await asyncio.gather(*tasks)
    for p, data in zip(pairs, data_list):
        results[f"{p}/USDC"] = data
    return results

@app.post("/api/analyze", response_model=SignalResult)
async def analyze(req: AnalysisRequest):
    base = req.pair.split("/")[0].upper()

    # 1. Fetch live price data
    price_data = await price_service.get_price_data(base)

    # 2. Build prompt
    prompt = build_analysis_prompt(
        req.pair, req.timeframe, req.risk, req.indicators, price_data
    )

    tx_hash = None
    model_used = "demo-mode"
    on_chain = False
    raw_response = None

    # 3. Handle inference (User key or Server key)
    client_to_use = get_og_client()
    if req.private_key and (not client_to_use or req.private_key != OG_PRIVATE_KEY):
        try:
            client_to_use = OGClient(private_key=req.private_key, email=OG_EMAIL, password=OG_PASSWORD)
        except Exception as e:
            logger.error(f"Failed to init user OG Client: {e}")
            client_to_use = None

    # 4. Call OpenGradient
    if client_to_use:
        try:
            tx_hash, raw_response, model_used = client_to_use.llm_chat(
                prompt, req.inference_mode
            )
            on_chain = True
            logger.info(f"✅ OG inference tx: {tx_hash}")
        except Exception as e:
            logger.warning(f"⚠️ OG inference failed: {e}, falling back to Claude")

    # 5. Fallback: Claude API (Demo Mode)
    if not raw_response:
        # Check if Claude is even available or if we should just fail
        if not os.getenv("ANTHROPIC_API_KEY") and not on_chain:
            raise HTTPException(
                status_code=403, 
                detail="No inference power available. Please provide your OpenGradient Private Key in the sidebar or check server configuration."
            )
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 1000,
                        "messages": [{"role": "user", "content": prompt}]
                    }
                )
                resp_data = r.json()
                raw_response = resp_data["content"][0]["text"]
                model_used = "claude-sonnet-4 (demo)"
                tx_hash = f"demo-{int(time.time())}"
        except Exception as e:
            raise HTTPException(500, f"All inference backends failed: {e}")

    # 6. Parse JSON
    try:
        clean = raw_response.strip()
        if "```" in clean:
            import re
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", clean)
            clean = match.group(1).strip() if match else clean
        result = json.loads(clean)
    except Exception as e:
        raise HTTPException(500, f"Failed to parse LLM response: {e}")

    return SignalResult(
        signal=result.get("signal", "HOLD"),
        strength=result.get("strength", result.get("signal", "HOLD")),
        confidence=result.get("confidence", 70),
        target=result.get("target_price", "N/A"),
        stop_loss=result.get("stop_loss", "N/A"),
        reasoning=result.get("reasoning_steps", []),
        tx_hash=tx_hash,
        model_used=model_used,
        inference_mode=req.inference_mode if on_chain else "demo",
        timestamp=datetime.now(timezone.utc).isoformat(),
        on_chain_verified=on_chain,
    )

@app.get("/api/signals/history")
async def signal_history():
    # In production, this might query on-chain events via SDK
    return {
        "history": [
            {"pair": "BTC/USDC", "signal": "BUY",  "confidence": 84, "price": "$67,240", "time": "14:22 UTC", "tx_hash": "0x7f3a...e291", "verified": True},
            {"pair": "ETH/USDC", "signal": "HOLD", "confidence": 71, "price": "$3,480",  "time": "13:05 UTC", "tx_hash": "0x2b9c...f104", "verified": True},
        ]
    }

@app.on_event("shutdown")
async def shutdown_event():
    await price_service.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
