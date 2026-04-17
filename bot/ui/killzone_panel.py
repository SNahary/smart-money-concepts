"""Kill Zone panel — display time intervals per killzone in user's timezone."""

from __future__ import annotations

import logging
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from nicegui import ui

from bot.config import EnvSettings, StrategyConfig
from bot.strategy.killzone import KILLZONES, is_in_killzone

logger = logging.getLogger(__name__)


def _parse(t: str) -> time:
    h, m = t.split(":")
    return time(int(h), int(m))


def _to_local(utc_time_str: str, tz: ZoneInfo) -> str:
    """Convert an UTC 'HH:MM' string to the target timezone 'HH:MM' string."""
    today = datetime.now(timezone.utc).date()
    utc_dt = datetime.combine(today, _parse(utc_time_str), tzinfo=timezone.utc)
    local_dt = utc_dt.astimezone(tz)
    return local_dt.strftime("%H:%M")


def build_killzone_panel(strategy: StrategyConfig) -> None:
    """Build the Kill Zones tab contents."""

    env = EnvSettings()
    tz = ZoneInfo(env.timezone)
    offset = datetime.now(tz).utcoffset()
    offset_h = int(offset.total_seconds() // 3600) if offset else 0
    tz_label = f"{env.timezone} (UTC{'+' if offset_h >= 0 else '-'}{abs(offset_h)})"

    ui.label("Kill Zones").classes("text-h5 q-mb-md")

    with ui.row().classes("items-center gap-4 q-mb-md"):
        ui.icon("schedule", size="1.5rem").classes("text-info")
        ui.label(f"Timezone d'affichage : {tz_label}").classes("text-subtitle1")

    # --- Current time display ---
    with ui.card().classes("q-pa-md q-mb-md"):
        now_label = ui.label("").classes("text-h6")
        active_label = ui.label("").classes("text-caption")

    # --- Table ---
    columns = [
        {"name": "name", "label": "Kill Zone", "field": "name", "align": "left"},
        {"name": "utc", "label": "Heure UTC", "field": "utc", "align": "center"},
        {"name": "local", "label": f"Heure locale ({env.timezone})", "field": "local", "align": "center"},
        {"name": "enabled", "label": "Configuree", "field": "enabled", "align": "center"},
        {"name": "status", "label": "Etat", "field": "status", "align": "center"},
    ]

    table = ui.table(columns=columns, rows=[], row_key="name").classes("w-full").props(
        "dense flat bordered"
    )

    # --- Legend ---
    with ui.row().classes("gap-4 q-mt-md"):
        ui.html('<span style="color:#22c55e;">\u25cf</span> ACTIVE maintenant').classes("text-caption")
        ui.html('<span style="color:#94a3b8;">\u25cb</span> Inactive').classes("text-caption")
        ui.html('<span style="color:#64748b;">\u2014</span> Non configuree').classes("text-caption")

    # --- Refresh every second ---
    def _refresh():
        now_utc = datetime.now(timezone.utc)
        now_local = now_utc.astimezone(tz)
        now_label.text = f"Heure actuelle : {now_local.strftime('%H:%M:%S')}  ({env.timezone})"

        active_kzs = [
            name for name in strategy.killzones
            if is_in_killzone(now_utc, [name])
        ]
        if active_kzs:
            active_label.text = f"Kill zone active : {', '.join(active_kzs)}"
            active_label.classes(replace="text-caption text-positive text-weight-bold")
        else:
            active_label.text = "Aucune kill zone active actuellement"
            active_label.classes(replace="text-caption text-grey")

        rows = []
        for name, (start, end) in KILLZONES.items():
            is_active = is_in_killzone(now_utc, [name])
            enabled = name in strategy.killzones

            if not enabled:
                status = "\U0001f6ab Non selectionnee"
            elif is_active:
                status = "\U0001f7e2 ACTIVE"
            else:
                status = "\u26aa Inactive"

            rows.append({
                "name": name,
                "utc": f"{start} \u2192 {end}",
                "local": f"{_to_local(start, tz)} \u2192 {_to_local(end, tz)}",
                "enabled": "\u2714" if enabled else "\u2716",
                "status": status,
            })
        table.rows = rows
        table.update()

    _refresh()
    ui.timer(1.0, _refresh)
