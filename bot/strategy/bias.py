"""Determine market bias from higher-timeframe structure (BOS / CHoCH)."""

import logging

import numpy as np
import pandas as pd
from smartmoneyconcepts import smc

logger = logging.getLogger(__name__)


def get_bias(ohlcv: pd.DataFrame, swing_length: int = 10) -> dict:
    """Analyse the HTF OHLCV and return the current market bias.

    Returns
    -------
    dict with keys:
        direction : int   — 1 (bullish), -1 (bearish), 0 (neutral)
        type      : str   — "BOS" or "CHOCH" or ""
        level     : float — the structure level that was broken
    """
    swings = smc.swing_highs_lows(ohlcv, swing_length=swing_length)
    structure = smc.bos_choch(ohlcv, swings)

    # Find the last non-NaN CHoCH and BOS
    last_choch_idx = structure["CHOCH"].last_valid_index()
    last_bos_idx = structure["BOS"].last_valid_index()

    direction = 0
    bias_type = ""
    level = np.nan

    # Pick whichever is most recent; CHoCH wins if at the same index
    if last_choch_idx is not None and last_bos_idx is not None:
        if last_choch_idx >= last_bos_idx:
            direction = int(structure["CHOCH"].iloc[last_choch_idx])
            bias_type = "CHOCH"
            level = float(structure["Level"].iloc[last_choch_idx])
        else:
            direction = int(structure["BOS"].iloc[last_bos_idx])
            bias_type = "BOS"
            level = float(structure["Level"].iloc[last_bos_idx])
    elif last_choch_idx is not None:
        direction = int(structure["CHOCH"].iloc[last_choch_idx])
        bias_type = "CHOCH"
        level = float(structure["Level"].iloc[last_choch_idx])
    elif last_bos_idx is not None:
        direction = int(structure["BOS"].iloc[last_bos_idx])
        bias_type = "BOS"
        level = float(structure["Level"].iloc[last_bos_idx])

    # Wording: Haussier / Baissier / Range (not BOS/CHOCH)
    if direction == 1:
        bias_label = "Haussier"
    elif direction == -1:
        bias_label = "Baissier"
    else:
        bias_label = "Range"

    logger.debug(
        "Bias → %s (via %s)  level=%s",
        bias_label,
        bias_type,
        level,
    )
    return {"direction": direction, "type": bias_label, "level": level}
