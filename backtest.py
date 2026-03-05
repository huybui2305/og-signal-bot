"""
OG Signal - Backtesting Utility
Compares AI signals with subsequent price action.
"""

import os
import json
import asyncio
from datetime import datetime, timedelta
import httpx
from typing import List, Dict, Any

async def simulate_backtest():
    """
    Simple backtest simulation:
    1. Define mock past signals.
    2. Fetch actual price movement from CoinGecko for those timeframes.
    3. Calculate accuracy.
    """
    print("🔮 OG Signal Backtester starting...")
    
    # Mock history of signals generated 24h ago
    # In a real app, you'd pull this from a database or on-chain events
    past_signals = [
        {"pair": "BTC/USDC", "signal": "BUY",  "entry": 64000, "confidence": 88},
        {"pair": "ETH/USDC", "signal": "HOLD", "entry": 3450,  "confidence": 72},
        {"pair": "SOL/USDC", "signal": "SELL", "entry": 195,   "confidence": 85},
        {"pair": "LINK/USDC", "signal": "BUY", "entry": 18.5, "confidence": 92}
    ]
    
    # Current prices (using CoinGecko)
    print("📡 Fetching current prices for verification...")
    async with httpx.AsyncClient() as client:
        r = await client.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana,chainlink&vs_currencies=usd")
        current_prices = r.json()
    
    price_map = {
        "BTC/USDC": current_prices["bitcoin"]["usd"],
        "ETH/USDC": current_prices["ethereum"]["usd"],
        "SOL/USDC": current_prices["solana"]["usd"],
        "LINK/USDC": current_prices["chainlink"]["usd"]
    }
    
    results = []
    correct = 0
    
    print("\n--- Backtest Results ---")
    for s in past_signals:
        pair = s["pair"]
        curr = price_map[pair]
        entry = s["entry"]
        change = (curr - entry) / entry * 100
        
        # Simple success metric
        success = False
        if s["signal"] == "BUY" and change > 0: success = True
        if s["signal"] == "SELL" and change < 0: success = True
        if s["signal"] == "HOLD" and abs(change) < 2: success = True
        
        if success: correct += 1
        
        print(f"[{pair}] Signal: {s['signal']} (Conf: {s['confidence']}%)")
        print(f"   Entry: ${entry:,.2f} -> Current: ${curr:,.2f} ({change:+.2f}%)")
        print(f"   Verdict: {'✅ CORRECT' if success else '❌ INCORRECT'}")
        
    accuracy = (correct / len(past_signals)) * 100
    print(f"\n📈 Final AI Accuracy Score: {accuracy:.1f}%")
    
if __name__ == "__main__":
    asyncio.run(simulate_backtest())
