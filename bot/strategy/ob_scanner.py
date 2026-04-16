"""Scan for Order Blocks in confluence with the HTF bias and detect price return."""

import logging
from typing import List

import numpy as np
import pandas as pd
from smartmoneyconcepts import smc

logger = logging.getLogger(__name__)


def find_active_obs(
    ohlcv: pd.DataFrame,
    bias_direction: int,
    swing_length: int = 10,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Find unmitigated OBs matching the bias direction.

    Returns
    -------
    (active_obs, swings)
        active_obs — filtered DataFrame rows from smc.ob() where:
            • OB direction == bias_direction
            • MitigatedIndex == 0 (not yet mitigated)
        swings — full swing_highs_lows result (used later for TP calc)
    """
    swings = smc.swing_highs_lows(ohlcv, swing_length=swing_length)
    obs = smc.ob(ohlcv, swings)

    mask = (obs["OB"] == bias_direction) & (
        obs["MitigatedIndex"].isna() | (obs["MitigatedIndex"] == 0)
    )
    active_obs = obs[mask].copy()

    logger.debug(
        "Found %d active OB(s) matching bias %s",
        len(active_obs),
        "BULL" if bias_direction == 1 else "BEAR",
    )
    return active_obs, swings


def detect_price_return(
    ohlcv: pd.DataFrame,
    active_obs: pd.DataFrame,
    bias_direction: int,
) -> List[dict]:
    """Check if the latest candle's price has entered any active OB zone.

    For bullish OB → price drops into zone: candle low  <= OB Top
    For bearish OB → price rises into zone:  candle high >= OB Bottom

    Returns a list of triggered OBs as dicts with index, top, bottom, percentage.
    """
    if active_obs.empty:
        return []

    last = ohlcv.iloc[-1]
    triggered: List[dict] = []

    for idx, ob in active_obs.iterrows():
        ob_top = ob["Top"]
        ob_bottom = ob["Bottom"]

        if bias_direction == 1:
            # Bullish: price descends into OB zone
            in_zone = last["low"] <= ob_top and last["close"] >= ob_bottom
        else:
            # Bearish: price ascends into OB zone
            in_zone = last["high"] >= ob_bottom and last["close"] <= ob_top

        if in_zone:
            ob_time = ohlcv.index[int(idx)] if int(idx) < len(ohlcv) else None
            triggered.append(
                {
                    "ob_index": int(idx),
                    "top": float(ob_top),
                    "bottom": float(ob_bottom),
                    "ob_time": ob_time,
                    "percentage": float(ob["Percentage"]),
                    "volume": float(ob["OBVolume"]),
                }
            )

    logger.debug("%d OB(s) triggered by current price", len(triggered))
    return triggered
