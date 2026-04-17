"""Trading journal panel — manual trade logging form + history table."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from nicegui import ui

from bot.config import EnvSettings
from bot.state import BotState

logger = logging.getLogger(__name__)

PAIRS = [
    "EURUSD", "GBPUSD", "XAUUSD",
    "USDJPY", "GBPJPY", "EURJPY",
    "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
]
EMOTIONS = ["Confiant", "Douteux", "FOMO", "Revenge"]


def _friday_cutoff_label() -> str:
    """Convert 15:00 UTC to the user's configured timezone (DST aware)."""
    env = EnvSettings()
    tz = ZoneInfo(env.timezone)
    cutoff_utc = datetime.combine(datetime.now().date(), time(15, 0), tzinfo=timezone.utc)
    local = cutoff_utc.astimezone(tz)
    offset = local.utcoffset()
    offset_hours = int(offset.total_seconds() // 3600) if offset else 0
    sign = "+" if offset_hours >= 0 else "-"
    return f"Pas vendredi apres {local.strftime('%Hh%M')} (UTC{sign}{abs(offset_hours)})"


def _build_raison_checklist() -> dict:
    """Build the raison-d-entree checklist with dynamic Friday cutoff."""
    return {
        "A. Contexte macro": [
            "Pas de news rouge",
        ],
        "B. Structure HTF (4H)": [
            "BOS/CHoCH clair",
            "Biais actif",
            "Pas d'inversion H1",
        ],
        "C. Zone OB (30M)": [
            "OB non mitige",
            "Force >= 50%",
            "OB < 3 jours",
            "Confluence liquidity/FVG",
        ],
        "D. Confirmation LTF": [
            "MSS dans OB",
            "FVG d'impulsion",
            "IFVG",
            "Breaker Block",
        ],
        "E. Timing + R:R": [
            "Kill zone active",
            "Pas fin de session",
            _friday_cutoff_label(),
            "R:R >= 1:2",
            "SL buffer ok",
        ],
    }


def build_journal_panel(state: BotState) -> None:
    """Build the Journal tab contents."""

    ui.label("Journal de Trading").classes("text-h5 q-mb-md")

    # === Form ===
    with ui.card().classes("w-full q-pa-md q-mb-lg"):
        ui.label("Nouveau trade").classes("text-h6 q-mb-sm")

        with ui.row().classes("gap-4 flex-wrap items-end"):
            pair_sel = ui.select(options=PAIRS, value="EURUSD", label="Paire").classes("w-36")
            dir_sel = ui.select(options=["BUY", "SELL"], value="BUY", label="Direction").classes("w-28")

            with ui.input("Date entree", value=str(date.today())).classes("w-40") as date_input:
                with ui.menu().props("no-parent-event") as date_menu:
                    with ui.date().bind_value(date_input):
                        pass
                with date_input.add_slot("append"):
                    ui.icon("edit_calendar").on("click", date_menu.open).classes("cursor-pointer")

        with ui.row().classes("gap-4 flex-wrap items-end q-mt-sm"):
            prix_input = ui.number(label="Prix entree", format="%.5f").classes("w-36")
            sl_input = ui.number(label="SL", format="%.5f").classes("w-36")
            tp_input = ui.number(label="TP", format="%.5f").classes("w-36")
            lot_input = ui.number(label="Lot size", value=0.01, format="%.2f", step=0.01).classes("w-28")
            rr_input = ui.number(label="R:R", format="%.1f", step=0.1).classes("w-28")

        ui.separator().classes("q-my-sm")

        # Raison d'entree = checklist simplifiee (cochable)
        ui.label("Raison d'entree (cocher les criteres valides)").classes(
            "text-caption text-grey"
        )
        raison_checkboxes: list[tuple[str, ui.checkbox]] = []
        with ui.row().classes("gap-4 flex-wrap w-full"):
            for section, items in _build_raison_checklist().items():
                with ui.column().classes("min-w-[180px]"):
                    ui.label(section).classes("text-caption text-weight-bold")
                    for label in items:
                        # Default: all checked, user unchecks missing criteria
                        cb = ui.checkbox(label, value=True)
                        raison_checkboxes.append((f"{section[:1]}: {label}", cb))

        with ui.row().classes("gap-4 items-end q-mt-sm"):
            emotions_sel = ui.select(
                options=EMOTIONS, value="Confiant", label="Emotions"
            ).classes("w-40")

        erreurs_input = ui.textarea(
            label="Erreurs commises",
            placeholder="Ex: Entre trop tot, pas attendu la confirmation...",
        ).classes("w-full q-mt-sm")

        notes_input = ui.textarea(
            label="Notes",
            placeholder="Commentaires libres...",
        ).classes("w-full q-mt-sm")

        save_btn = ui.button("Enregistrer", on_click=lambda: _save())
        save_btn.props("color=primary icon=save")

    # === History table ===
    ui.label("Historique du Journal").classes("text-h6 q-mt-md")
    history_area = ui.column().classes("w-full")

    # ------------------------------------------------------------------
    async def _save():
        if not prix_input.value:
            ui.notify("Le prix d'entree est requis", type="warning")
            return

        # Serialise checklist as "X/Y criteres : item1 ; item2 ; ..."
        coches = [label for label, cb in raison_checkboxes if cb.value]
        total = len(raison_checkboxes)
        raison_text = (
            f"{len(coches)}/{total} : " + " ; ".join(coches) if coches else ""
        )

        entry = {
            "pair": pair_sel.value,
            "direction": dir_sel.value,
            "date_entree": date_input.value,
            "prix_entree": float(prix_input.value),
            "sl": float(sl_input.value) if sl_input.value else None,
            "tp": float(tp_input.value) if tp_input.value else None,
            "lot_size": float(lot_input.value) if lot_input.value else None,
            "rr": float(rr_input.value) if rr_input.value else None,
            "raison_entree": raison_text,
            "emotions": emotions_sel.value,
            "erreurs": erreurs_input.value or "",
            "notes": notes_input.value or "",
        }

        entry_id = await state.save_journal_entry(entry)
        ui.notify(f"Trade #{entry_id} enregistre", type="positive")

        # Reset form
        prix_input.set_value(None)
        sl_input.set_value(None)
        tp_input.set_value(None)
        rr_input.set_value(None)
        for _, cb in raison_checkboxes:
            cb.set_value(True)  # default: all checked
        erreurs_input.set_value("")
        notes_input.set_value("")

        await _refresh_history()

    async def _refresh_history():
        entries = await state.get_journal_entries(limit=50)
        history_area.clear()
        with history_area:
            if not entries:
                ui.label("Aucun trade enregistre.").classes("text-grey")
                return

            columns = [
                {"name": "date", "label": "Date", "field": "date", "align": "left", "sortable": True},
                {"name": "pair", "label": "Paire", "field": "pair", "sortable": True},
                {"name": "dir", "label": "Dir", "field": "dir"},
                {"name": "entry", "label": "Entry", "field": "entry"},
                {"name": "sl", "label": "SL", "field": "sl"},
                {"name": "tp", "label": "TP", "field": "tp"},
                {"name": "rr", "label": "R:R", "field": "rr"},
                {"name": "emotions", "label": "Emotions", "field": "emotions"},
                {"name": "raison", "label": "Raison", "field": "raison",
                 "align": "left",
                 "style": "white-space: normal; word-break: break-word; max-width: 400px;",
                 "headerStyle": "max-width: 400px;"},
                {"name": "notes", "label": "Notes", "field": "notes",
                 "align": "left",
                 "style": "white-space: normal; word-break: break-word; max-width: 300px;",
                 "headerStyle": "max-width: 300px;"},
            ]

            rows = []
            for e in entries:
                rows.append({
                    "id": e["id"],
                    "date": e.get("date_entree", "")[:16],
                    "pair": e["pair"],
                    "dir": e["direction"],
                    "entry": e["prix_entree"],
                    "sl": e.get("sl") or "-",
                    "tp": e.get("tp") or "-",
                    "rr": f"1:{e['rr']:.1f}" if e.get("rr") else "-",
                    "emotions": e.get("emotions") or "",
                    "raison": e.get("raison_entree") or "",
                    "notes": e.get("notes") or "",
                })

            ui.table(
                columns=columns, rows=rows, row_key="id"
            ).classes("w-full").props("dense flat bordered wrap-cells")

    # Load history on panel build (after functions are defined)
    asyncio.ensure_future(_refresh_history())
