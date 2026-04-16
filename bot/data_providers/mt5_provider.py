"""MetaTrader 5 data provider — Windows only, local IPC, zero rate limits."""

import logging

import pandas as pd
from zoneinfo import ZoneInfo

from .base import DataProvider

logger = logging.getLogger(__name__)

# Mapping is deferred to avoid import error when MT5 is not installed.
_TIMEFRAME_MAP = None


def _get_timeframe_map() -> dict:
    global _TIMEFRAME_MAP
    if _TIMEFRAME_MAP is None:
        import MetaTrader5 as mt5

        _TIMEFRAME_MAP = {
            "1M": mt5.TIMEFRAME_MN1,
            "1W": mt5.TIMEFRAME_W1,
            "1D": mt5.TIMEFRAME_D1,
            "4H": mt5.TIMEFRAME_H4,
            "1H": mt5.TIMEFRAME_H1,
            "30M": mt5.TIMEFRAME_M30,
            "15M": mt5.TIMEFRAME_M15,
            "5M": mt5.TIMEFRAME_M5,
        }
    return _TIMEFRAME_MAP


class MT5Provider(DataProvider):
    def __init__(
        self,
        login: int,
        password: str,
        server: str,
        timezone: str = "Europe/Helsinki",
    ):
        self.login = login
        self.password = password
        self.server = server
        self.tz = ZoneInfo(timezone)
        self._connected = False

    # ------------------------------------------------------------------
    def connect(self) -> bool:
        """Must be called from the SAME thread that will call get_ohlcv()."""
        import MetaTrader5 as mt5

        if not mt5.initialize():
            logger.error("MT5 initialize() failed: %s", mt5.last_error())
            return False
        if not mt5.login(self.login, password=self.password, server=self.server):
            logger.error("MT5 login() failed: %s", mt5.last_error())
            return False

        # Log available symbols to help debugging name mismatches
        info = mt5.account_info()
        if info:
            logger.info(
                "MT5 connected — server %s, account %s, name %s",
                info.server, info.login, info.name,
            )

        self._connected = True
        return True

    def disconnect(self) -> None:
        import MetaTrader5 as mt5

        mt5.shutdown()
        self._connected = False
        logger.info("MT5 disconnected")

    # ------------------------------------------------------------------
    def _resolve_symbol(self, symbol: str) -> str:
        """Find the real broker symbol name.

        Brokers use different naming conventions:
          EURUSD, EURUSDm, EURUSD., EURUSD.a, EUR/USD …
        This method tries the given name first, then common variants.
        """
        import MetaTrader5 as mt5

        # Try exact name first
        info = mt5.symbol_info(symbol)
        if info is not None:
            # Activate in Market Watch if needed
            if not info.visible:
                mt5.symbol_select(symbol, True)
            return symbol

        # Try common broker suffixes
        for suffix in (".sml", "m", ".", ".a", ".i", "pro", "-a"):
            variant = symbol + suffix
            info = mt5.symbol_info(variant)
            if info is not None:
                if not info.visible:
                    mt5.symbol_select(variant, True)
                logger.info("Symbol resolved: %s → %s", symbol, variant)
                return variant

        # List some available symbols to help the user
        all_symbols = mt5.symbols_get()
        if all_symbols:
            # Filter symbols containing the base currency pair
            base = symbol[:3]
            quote = symbol[3:6] if len(symbol) >= 6 else ""
            matches = [
                s.name for s in all_symbols
                if base in s.name and quote in s.name
            ][:10]
            logger.error(
                "Symbol '%s' not found. Similar symbols on this broker: %s",
                symbol, matches or "(none)",
            )
        raise RuntimeError(
            f"Symbol '{symbol}' not found on this broker. "
            f"Check the Market Watch in MT5 for the correct name."
        )

    # ------------------------------------------------------------------
    def _to_dataframe(self, rates) -> pd.DataFrame:
        """Convert MT5 rates array to a standardised DataFrame."""
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df["time"] = df["time"].dt.tz_convert(self.tz)
        df = df.rename(columns={"tick_volume": "volume"})
        df = df.set_index("time")
        return df[["open", "high", "low", "close", "volume"]]

    # ------------------------------------------------------------------
    def get_ohlcv(
        self, symbol: str, timeframe: str, count: int = 200
    ) -> pd.DataFrame:
        import MetaTrader5 as mt5

        # Do NOT call mt5.initialize() here — it resets the session.
        # connect() must have been called first in this same thread.

        tf_map = _get_timeframe_map()
        mt5_tf = tf_map.get(timeframe)
        if mt5_tf is None:
            raise ValueError(
                f"Unsupported timeframe '{timeframe}'. "
                f"Choose from: {list(tf_map.keys())}"
            )

        # Resolve broker-specific symbol name
        real_symbol = self._resolve_symbol(symbol)

        rates = mt5.copy_rates_from_pos(real_symbol, mt5_tf, 0, count)
        if rates is None or len(rates) == 0:
            raise RuntimeError(
                f"MT5 returned no data for {real_symbol} {timeframe}: "
                f"{mt5.last_error()}"
            )
        return self._to_dataframe(rates)

    # ------------------------------------------------------------------
    def get_ohlcv_range(
        self, symbol: str, timeframe: str, from_dt, to_dt,
    ) -> "pd.DataFrame":
        import MetaTrader5 as mt5
        from datetime import datetime, timezone

        tf_map = _get_timeframe_map()
        mt5_tf = tf_map.get(timeframe)
        if mt5_tf is None:
            raise ValueError(
                f"Unsupported timeframe '{timeframe}'. "
                f"Choose from: {list(tf_map.keys())}"
            )

        real_symbol = self._resolve_symbol(symbol)

        # Ensure naive datetimes are treated as UTC
        if isinstance(from_dt, datetime) and from_dt.tzinfo is None:
            from_dt = from_dt.replace(tzinfo=timezone.utc)
        if isinstance(to_dt, datetime) and to_dt.tzinfo is None:
            to_dt = to_dt.replace(tzinfo=timezone.utc)

        rates = mt5.copy_rates_range(real_symbol, mt5_tf, from_dt, to_dt)
        if rates is None or len(rates) == 0:
            raise RuntimeError(
                f"MT5 returned no data for {real_symbol} {timeframe} "
                f"[{from_dt} → {to_dt}]: {mt5.last_error()}"
            )
        return self._to_dataframe(rates)
