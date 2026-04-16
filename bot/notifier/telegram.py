"""Telegram notification via raw HTTP — no SDK dependency."""

import html
import logging
import time
from datetime import datetime

import requests
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, timezone: str = "UTC"):
        self.token = token
        self.chat_id = chat_id
        self.tz = ZoneInfo(timezone)
        self._url = _API.format(token=token)

    # ------------------------------------------------------------------
    # Low-level send
    # ------------------------------------------------------------------
    def send(
        self,
        text: str,
        parse_mode: str = "HTML",
        max_retries: int = 3,
    ) -> bool:
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        for attempt in range(max_retries):
            try:
                r = requests.post(self._url, json=payload, timeout=10)
                if r.status_code == 429:
                    wait = r.json().get("parameters", {}).get("retry_after", 5)
                    logger.warning("Telegram rate-limited, waiting %ss", wait)
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                return r.json().get("ok", False)
            except requests.RequestException as exc:
                logger.error("Telegram send error (attempt %d): %s", attempt + 1, exc)
                time.sleep(1)
        return False

    # ------------------------------------------------------------------
    # Signal message
    # ------------------------------------------------------------------
    def send_signal(self, trade: dict, bias: dict) -> bool:
        """Format and send a complete trade signal."""
        is_buy = trade["direction"] == 1
        symbol = html.escape(trade["symbol"])

        # Signal time = candle that touched the OB, converted to display TZ
        sig_time = trade.get("signal_time")
        if sig_time:
            if hasattr(sig_time, "astimezone"):
                sig_time = sig_time.astimezone(self.tz)
                time_str = sig_time.strftime("%d %b %Y  %H:%M")
            elif hasattr(sig_time, "strftime"):
                time_str = sig_time.strftime("%d %b %Y  %H:%M")
            else:
                time_str = str(sig_time)[:16]
        else:
            time_str = datetime.now(self.tz).strftime("%d %b %Y  %H:%M")

        # OB formation time — also convert to display TZ
        ob_time_raw = trade.get("ob_time")
        if ob_time_raw and hasattr(ob_time_raw, "astimezone"):
            ob_time_raw = ob_time_raw.astimezone(self.tz)

        # Header
        if is_buy:
            header = f"\U0001f7e2 <b>SIGNAL ACHAT</b>  \u2014  <b>{symbol}</b>"
        else:
            header = f"\U0001f534 <b>SIGNAL VENTE</b>  \u2014  <b>{symbol}</b>"

        # Bias — "Haussier" / "Baissier" / "Range"
        bias_label = html.escape(bias.get("type", ""))
        if bias["direction"] == 1:
            bias_line = f"\U0001f4c8 Biais : <b>{bias_label}</b>"
        else:
            bias_line = f"\U0001f4c9 Biais : <b>{bias_label}</b>"

        # Trade info
        entry_icon = "\u27a1\ufe0f"
        sl_icon = "\U0001f6d1"
        tp_icon = "\U0001f3af"

        lines = [
            header,
            "\u2500" * 25,
            bias_line,
            "",
            f"{entry_icon} <b>Entry :</b>  <code>{trade['entry']}</code>",
            f"{sl_icon} <b>SL :</b>       <code>{trade['sl']}</code>  ({trade['sl_pips']} pips)",
        ]

        if trade.get("tp1") is not None:
            lines.append(
                f"{tp_icon} <b>TP1 :</b>     <code>{trade['tp1']}</code>  (+{trade['tp1_pips']} pips)"
            )
        if trade.get("tp2") is not None:
            lines.append(
                f"{tp_icon} <b>TP2 :</b>     <code>{trade['tp2']}</code>  (+{trade['tp2_pips']} pips)"
            )

        # R:R
        rr_parts = []
        if trade.get("rr1") is not None:
            rr_parts.append(f"1:{trade['rr1']}")
        if trade.get("rr2") is not None:
            rr_parts.append(f"1:{trade['rr2']}")
        if rr_parts:
            lines.append(f"\u2696\ufe0f <b>R:R :</b>     {' / '.join(rr_parts)}")

        lines.append("")

        # OB info
        strength = trade.get("ob_strength", 0)
        if strength >= 60:
            strength_bar = "\U0001f7e2\U0001f7e2\U0001f7e2"
        elif strength >= 30:
            strength_bar = "\U0001f7e1\U0001f7e1"
        else:
            strength_bar = "\U0001f534"
        lines.append(f"\U0001f4aa <b>Force OB :</b> {strength}% {strength_bar}")
        lines.append(f"\U0001f4cf <b>Taille OB :</b> {trade['ob_size_pips']} pips")

        # OB formation time (already converted to display TZ above)
        ob_time = ob_time_raw
        if ob_time:
            ob_time_str = ob_time.strftime("%d %b %H:%M") if hasattr(ob_time, "strftime") else str(ob_time)[:16]
            lines.append(f"\U0001f4c5 <b>OB cloture :</b> {ob_time_str}")

        # Footer
        lines += [
            "\u2500" * 25,
            f"\U0001f552 <b>Retour sur OB :</b> <i>{time_str}</i>",
            "\U0001f916 <i>SMC Signal Bot</i>",
        ]

        return self.send("\n".join(lines))

    # ------------------------------------------------------------------
    # Status / health messages
    # ------------------------------------------------------------------
    def send_status(self, message: str) -> bool:
        return self.send(f"<b>BOT</b> — {html.escape(message)}")
