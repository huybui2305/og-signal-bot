# OG Signal 🔮
> On-Chain AI Trading Signal Bot powered by OpenGradient SDK

A full-stack trading signal app that uses **OpenGradient's verifiable LLM inference** to generate cryptographically-verified AI trading signals. Every signal is tied to an on-chain transaction hash — fully auditable.

## Architecture

```
frontend/index.html   ← Pure HTML/JS UI (no framework, fully self-contained)
backend/app.py        ← FastAPI server wrapping the OpenGradient Python SDK
```

## Quick Start

### 1. Prerequisites

```bash
pip install opengradient fastapi uvicorn httpx python-dotenv
```

> Windows users: enable WSL first (`opengradient` requires it temporarily)

### 2. Get $OPG Testnet Tokens

1. Create/import a wallet in MetaMask
2. Add Base Sepolia network (Chain ID: 84532)
3. Visit https://faucet.opengradient.ai to get $OPG tokens
4. These tokens pay for LLM inference on the OpenGradient network

### 3. Configure Environment

```bash
cd backend
cp .env.example .env
# Edit .env and add your private key
```

Or just export directly:
```bash
export OG_PRIVATE_KEY=0x_your_private_key
export OG_EMAIL=your@email.com       # optional (for ML inference)
export OG_PASSWORD=your_password     # optional (for ML inference)
```

### 4. Start Backend

```bash
cd backend
python app.py
# → Server running at http://localhost:8000
# → Docs at http://localhost:8000/docs
```

### 5. Open Frontend

Open `frontend/index.html` in your browser.

Click **"Test"** in the sidebar to verify backend connection, then click **"Run OpenGradient Analysis"**.

---

## How It Works

### OpenGradient SDK Usage

```python
import opengradient as og

# Initialize with your funded wallet
og.init(private_key="0x...")

# Run verifiable LLM inference
tx_hash, finish_reason, message = og.llm_chat(
    model_cid=og.LLM.MISTRAL_7B_INSTRUCT_V3,
    messages=[
        {"role": "system", "content": "You are a trading analyst..."},
        {"role": "user", "content": "Analyze BTC/USDC..."}
    ],
    inference_mode=og.LlmInferenceMode.VANILLA,  # or TEE
    max_tokens=800,
)

# tx_hash = on-chain proof that this exact inference ran
print("On-chain proof:", tx_hash)
print("Signal:", message["content"])
```

### What Makes This Different

| Feature | Traditional AI API | OpenGradient |
|---------|-------------------|--------------|
| Verifiability | ❌ Black box | ✅ On-chain TX hash |
| Censorship resistance | ❌ Centralized | ✅ Decentralized nodes |
| Payment | 💳 Credit card | $OPG tokens |
| TEE mode | ❌ No | ✅ Intel TDX + H100 |
| Audit trail | ❌ None | ✅ Block explorer |

### Inference Modes

- **VANILLA**: Standard inference on OpenGradient network
- **TEE**: Trusted Execution Environment — hardware-attested inference inside Intel TDX enclave with NVIDIA H100 confidential compute

---

## API Reference

### `GET /api/health`
Check backend + SDK status

### `GET /api/prices`
Fetch live prices for all tracked pairs (via CoinGecko)

### `GET /api/price/{pair}`
Fetch live price for a specific pair (e.g., `/api/price/BTC-USDC`)

### `POST /api/analyze`
Run AI analysis via OpenGradient SDK

**Request body:**
```json
{
  "pair": "BTC/USDC",
  "timeframe": "1H",
  "risk": "moderate",
  "indicators": "RSI + MACD + Volume",
  "inference_mode": "VANILLA",
  "private_key": "0x..." // optional, uses server key if not provided
}
```

**Response:**
```json
{
  "signal": "BUY",
  "strength": "STRONG BUY",
  "confidence": 84,
  "target": "$69,200",
  "stop_loss": "$66,400",
  "reasoning": [...],
  "tx_hash": "0xabc...",
  "model_used": "og.LLM.MISTRAL_7B_INSTRUCT_V3",
  "inference_mode": "VANILLA",
  "timestamp": "2026-03-05T14:31:00+00:00",
  "on_chain_verified": true
}
```

### `GET /api/signals/history`
Get recent signal history

---

## Deploy on OpenGradient

To deploy the backend to the OpenGradient network (not just local):

1. Use any cloud host (Railway, Render, Fly.io) or VPS
2. Set `OG_PRIVATE_KEY` as environment variable
3. Update the backend URL in the frontend settings
4. The app will use real OpenGradient inference with all signals verifiable on-chain

---

## Resources

- 📚 OpenGradient Docs: https://docs.opengradient.ai/developers/sdk/
- 🔑 Testnet Faucet: https://faucet.opengradient.ai
- 🔍 Block Explorer: https://explorer.opengradient.ai
- 💬 Discord: https://discord.gg/SC45QNNMsB
