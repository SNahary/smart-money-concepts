"""OANDA v20 REST API data provider — cross-platform, free practice account."""

import logging
from datetime import datetime, timezone

import pandas as pd
import requests
from zoneinfo import ZoneInfo

from .base import DataProvider

logger = logging.getLogger(__name__)

# OANDA uses underscore-separated instrument names.
_PAIR_MAP = {
    "EURUSD": "EUR_USD",
    "GBPUSD": "GBP_USD",
    "XAUUSD": "XAU_USD",
    "GBPJPY": "GBP_JPY",
    "USDJPY": "USD_JPY",
    "AUDUSD": "AUD_USD",
    "USDCAD": "USD_CAD",
    "USDCHF": "USD_CHF",
    "NZDUSD": "NZD_USD",
    "EURJPY": "EUR_JPY",
    "BTCUSD": "BTC_USD",
    "ETHUSD": "ETH_USD",
}

_GRANULARITY_MAP = {
    "5M": "M5",
    "15M": "M15",
    "30M": "M30",
    "1H": "H1",
    "4H": "H4",
    "1D": "D",
    "1W": "W",
    "1M": "M",
}

_BASE_URLS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}


class OandaProvider(DataProvider):
    def __init__(
        self,
        api_token: str,
        account_id: str,
        environment: str = "practice",
        timezone: str = "Europe/Helsinki",
    ):
        self.api_token = api_token
        self.account_id = account_id
        self.base_url = _BASE_URLS.get(environment, _BASE_URLS["practice"])
        self.tz = ZoneInfo(timezone)
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            }
        )

    # ------------------------------------------------------------------
    def connect(self) -> bool:
        try:
            resp = self._session.get(
                f"{self.base_url}/v3/accounts/{self.account_id}",
                timeout=10,
            )
            resp.raise_for_status()
            logger.info("OANDA connected — account %s", self.account_id)
            return True
        except requests.RequestException as exc:
            logger.error("OANDA connection failed: %s", exc)
            return False

    def disconnect(self) -> None:
        self._session.close()
        logger.info("OANDA session closed")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _resolve_instrument(self, symbol: str) -> str:
        return _PAIR_MAP.get(symbol, symbol.replace("/", "_"))

    def _resolve_granularity(self, timeframe: str) -> str:
        g = _GRANULARITY_MAP.get(timeframe)
        if g is None:
            raise ValueError(
                f"Unsupported timeframe '{timeframe}'. "
                f"Choose from: {list(_GRANULARITY_MAP.keys())}"
            )
        return g

    def _candles_to_df(self, candles: list) -> pd.DataFrame:
        rows = []
        for c in candles:
            if not c.get("complete", True):
                continue
            mid = c["mid"]
            rows.append(
                {
                    "time": c["time"],
                    "open": float(mid["o"]),
                    "high": float(mid["h"]),
                    "low": float(mid["l"]),
                    "close": float(mid["c"]),
                    "volume": int(c["volume"]),
                }
            )
        df = pd.DataFrame(rows)
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df["time"] = df["time"].dt.tz_convert(self.tz)
        df = df.set_index("time")
        return df[["open", "high", "low", "close", "volume"]]

    # ------------------------------------------------------------------
    # Live: latest N candles
    # ------------------------------------------------------------------
    def get_ohlcv(
        self, symbol: str, timeframe: str, count: int = 200
    ) -> pd.DataFrame:
        instrument = self._resolve_instrument(symbol)
        granularity = self._resolve_granularity(timeframe)

        resp = self._session.get(
            f"{self.base_url}/v3/instruments/{instrument}/candles",
            params={"granularity": granularity, "count": count, "price": "M"},
            timeout=15,
        )
        resp.raise_for_status()
        candles = resp.json().get("candles", [])
        if not candles:
            raise RuntimeError(f"OANDA returned no data for {symbol} {timeframe}")
        return self._candles_to_df(candles)

    # ------------------------------------------------------------------
    # Backtest: date range (paginated, max 5000 per request)
    # ------------------------------------------------------------------
    def get_ohlcv_range(
        self, symbol: str, timeframe: str, from_dt, to_dt,
    ) -> pd.DataFrame:
        instrument = self._resolve_instrument(symbol)
        granularity = self._resolve_granularity(timeframe)

        if isinstance(from_dt, datetime) and from_dt.tzinfo is None:
            from_dt = from_dt.replace(tzinfo=timezone.utc)
        if isinstance(to_dt, datetime) and to_dt.tzinfo is None:
            to_dt = to_dt.replace(tzinfo=timezone.utc)

        all_candles: list = []
        cursor = from_dt.isoformat()

        while True:
            resp = self._session.get(
                f"{self.base_url}/v3/instruments/{instrument}/candles",
                params={
                    "granularity": granularity,
                    "from": cursor,
                    "to": to_dt.isoformat(),
                    "price": "M",
                    "count": 5000,
                },
                timeout=30,
            )
            resp.raise_for_status()
            candles = resp.json().get("candles", [])
            if not candles:
                break
            all_candles.extend(candles)
            # If fewer than 5000 returned, we have all the data
            if len(candles) < 5000:
                break
            # Move cursor past the last candle
            cursor = candles[-1]["time"]

        if not all_candles:
            raise RuntimeError(
                f"OANDA returned no data for {symbol} {timeframe} "
                f"[{from_dt} → {to_dt}]"
            )
        df = self._candles_to_df(all_candles)
        # Remove duplicates from pagination overlap
        return df[~df.index.duplicated(keep="first")]
