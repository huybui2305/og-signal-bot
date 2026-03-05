import httpx
import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class PriceFeedService:
    """
    Service to fetch price data from CoinGecko with basic caching.
    """
    COINGECKO_IDS = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "ARB": "arbitrum",
        "LINK": "chainlink",
        "OPG": "opengradient",
    }

    def __init__(self, cache_ttl: int = 60):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.cache_ttl = cache_ttl  # seconds
        self.client = httpx.AsyncClient(timeout=10)

    async def get_price_data(self, base_token: str) -> Dict[str, Any]:
        """Fetch real OHLCV + market data from CoinGecko with caching"""
        base_token = base_token.upper()
        
        # Check cache
        if base_token in self.cache:
            entry = self.cache[base_token]
            if time.time() - entry["timestamp"] < self.cache_ttl:
                logger.info(f"Returning cached price for {base_token}")
                return entry["data"]

        coin_id = self.COINGECKO_IDS.get(base_token, "bitcoin")
        try:
            # Market data
            r = await self.client.get(
                f"https://api.coingecko.com/api/v3/coins/{coin_id}",
                params={"localization": "false", "tickers": "false", "community_data": "false"}
            )
            r.raise_for_status()
            data = r.json()
            market = data.get("market_data", {})

            # OHLC (1D candle last 7 days)
            ohlc_r = await self.client.get(
                f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc",
                params={"vs_currency": "usd", "days": "7"}
            )
            ohlc_r.raise_for_status()
            ohlc = ohlc_r.json()

            result = {
                "price": market.get("current_price", {}).get("usd", 0),
                "price_change_24h": market.get("price_change_percentage_24h", 0),
                "price_change_7d":  market.get("price_change_percentage_7d",  0),
                "volume_24h":       market.get("total_volume", {}).get("usd", 0),
                "market_cap":       market.get("market_cap", {}).get("usd", 0),
                "high_24h":         market.get("high_24h", {}).get("usd", 0),
                "low_24h":          market.get("low_24h", {}).get("usd", 0),
                "ath":              market.get("ath", {}).get("usd", 0),
                "atl":              market.get("atl", {}).get("usd", 0),
                "ohlc_7d":          ohlc[-20:] if ohlc else [],
                "symbol":           data.get("symbol", base_token).upper(),
                "name":             data.get("name", base_token),
                "timestamp_fetched": time.time()
            }

            # Update cache
            self.cache[base_token] = {
                "timestamp": time.time(),
                "data": result
            }
            return result
        except Exception as e:
            logger.error(f"Price fetch error for {base_token}: {e}")
            if base_token in self.cache:
                logger.warning(f"Returning stale cache for {base_token} due to fetch error")
                return self.cache[base_token]["data"]
            return {"price": 0, "error": str(e)}

    async def close(self):
        await self.client.aclose()
