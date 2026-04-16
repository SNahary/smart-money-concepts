"""Abstract base class for OHLCV data providers."""

from abc import ABC, abstractmethod
from datetime import datetime

import pandas as pd


class DataProvider(ABC):
    """Interface that every data provider must implement."""

    @abstractmethod
    def connect(self) -> bool:
        """Open connection. Return True on success."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close connection gracefully."""

    @abstractmethod
    def get_ohlcv(
        self, symbol: str, timeframe: str, count: int = 200
    ) -> pd.DataFrame:
        """Fetch the latest *count* OHLCV candles.

        Returns a DataFrame with:
          - DatetimeIndex (timezone-aware)
          - Columns: open, high, low, close, volume
        """

    @abstractmethod
    def get_ohlcv_range(
        self,
        symbol: str,
        timeframe: str,
        from_dt: datetime,
        to_dt: datetime,
    ) -> pd.DataFrame:
        """Fetch OHLCV candles for a specific date range (backtest).

        Returns the same DataFrame format as get_ohlcv().
        """
