"""Trading journal panel — manual trade logging form + history table."""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from nicegui import ui

from bot.state import BotState

logger = logging.getLogger(__name__)

PAIRS = [
    "EURUSD", "GBPUSD", "XAUUSD",
    "USDJPY", "GBPJPY", "EURJPY",
    "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
]
EMOTIONS = ["Confiant", "Douteux", "FOMO", "Revenge"]


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

        raison_input = ui.textarea(
            label="Raison d'entree",
            placeholder="Ex: Retour sur OB bullish en confluence avec biais haussier 4H, London KZ...",
        ).classes("w-full")

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

        save_btn = ui.button("Enregistrer", on_click=lambda: asyncio.ensure_future(_save()))
        save_btn.props("color=primary icon=save")

    # === History table ===
    ui.label("Historique du Journal").classes("text-h6 q-mt-md")
    history_area = ui.column().classes("w-full")

    # ------------------------------------------------------------------
    async def _save():
        if not prix_input.value:
            ui.notify("Le prix d'entree est requis", type="warning")
            return

        entry = {
            "pair": pair_sel.value,
            "direction": dir_sel.value,
            "date_entree": date_input.value,
            "prix_entree": float(prix_input.value),
            "sl": float(sl_input.value) if sl_input.value else None,
            "tp": float(tp_input.value) if tp_input.value else None,
            "lot_size": float(lot_input.value) if lot_input.value else None,
            "rr": float(rr_input.value) if rr_input.value else None,
            "raison_entree": raison_input.value or "",
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
        raison_input.set_value("")
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
                {"name": "raison", "label": "Raison", "field": "raison"},
                {"name": "notes", "label": "Notes", "field": "notes"},
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
                    "raison": (e.get("raison_entree") or "")[:50],
                    "notes": (e.get("notes") or "")[:50],
                })

            ui.table(
                columns=columns, rows=rows, row_key="id"
            ).classes("w-full").props("dense flat bordered")

    # Load history on panel build (after functions are defined)
    asyncio.ensure_future(_refresh_history())
