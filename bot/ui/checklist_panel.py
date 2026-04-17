"""Entry Checklist panel — interactive pre-trade validation."""

from __future__ import annotations

import asyncio
import logging

from nicegui import ui

from bot.state import BotState

logger = logging.getLogger(__name__)

PAIRS = [
    "EURUSD", "GBPUSD", "XAUUSD",
    "USDJPY", "GBPJPY", "EURJPY",
    "AUDUSD", "USDCAD", "USDCHF", "NZDUSD",
]

# Correlation rule shown per pair (A3 item of the checklist)
CORRELATIONS = {
    "EURUSD": "EURUSD et GBPUSD dans le meme sens (coherence EUR/GBP)",
    "GBPUSD": "GBPUSD et EURUSD dans le meme sens (coherence EUR/GBP)",
    "XAUUSD": "DXY baissier (or = inverse du dollar) + risk sentiment coherent",
    "USDJPY": "DXY haussier + sentiment risk-on (JPY = refuge)",
    "EURJPY": "EURUSD haussier + risk-on (JPY = refuge)",
    "GBPJPY": "GBPUSD haussier + risk-on (JPY = refuge)",
    "AUDUSD": "Risk-on confirme (AUD = pro-risk, sensible a la Chine)",
    "NZDUSD": "Risk-on confirme (NZD = pro-risk, correle a AUD)",
    "USDCAD": "Petrole baissier (CAD = petro-devise, correlation inverse)",
    "USDCHF": "Risk-off OU DXY haussier (CHF = refuge)",
}

# Structure: { section_key: { "title": str, "items": [ {"key": str, "label": str, "critical": bool } ] } }
SECTIONS = {
    "A": {
        "title": "A. Contexte macro",
        "items": [
            {"key": "A1", "label": "Pas de news rouge dans les 2h", "critical": True},
            {"key": "A2", "label": "DXY compatible avec le trade", "critical": True},
            {"key": "A3", "label": "Correlations coherentes (voir paire)", "critical": True, "dynamic_correlation": True},
        ],
    },
    "B": {
        "title": "B. Structure HTF (TF Biais 4H)",
        "items": [
            {"key": "B1", "label": "BOS/CHoCH clair sur 4H", "critical": True},
            {"key": "B2", "label": "Biais actif et non contredit", "critical": True},
            {"key": "B3", "label": "Pas d'inversion CHoCH imminente sur H1", "critical": True},
        ],
    },
    "C": {
        "title": "C. Zone (TF OB 30M)",
        "items": [
            {"key": "C1", "label": "OB non mitige (premier retour)", "critical": True},
            {"key": "C2", "label": "Force OB >= 50%", "critical": True},
            {"key": "C3", "label": "OB age < 3 jours", "critical": True},
            {"key": "C4", "label": "Confluence liquidity pool / FVG HTF", "critical": True},
        ],
    },
    "D": {
        "title": "D. Confirmation LTF (5M ou 15M)",
        "items": [
            {"key": "D1", "label": "MSS dans la zone OB (OBLIGATOIRE)", "critical": True},
            {"key": "D2", "label": "FVG dans l'impulsion du MSS (point d'entree principal)", "critical": False, "entry_point": True},
            {"key": "D3", "label": "IFVG = ancien FVG oppose invalide (confluence bonus)", "critical": False, "entry_point": True},
        ],
    },
    "E": {
        "title": "E. Timing + R:R",
        "items": [
            {"key": "E1", "label": "Kill zone active", "critical": True},
            {"key": "E2", "label": "Pas en fin de session", "critical": True},
            {"key": "E3", "label": "Pas vendredi apres 15h UTC", "critical": True},
            {"key": "E4", "label": "R:R >= 1:2 sur TP1", "critical": True},
            {"key": "E5", "label": "SL au-dela de l'OB + buffer", "critical": True},
        ],
    },
}

TOTAL_ITEMS = sum(len(s["items"]) for s in SECTIONS.values())


def build_checklist_panel(state: BotState) -> None:
    """Build the Checklist tab contents."""

    ui.label("Checklist d'Entree SMC").classes("text-h5 q-mb-md")

    # === Header: pair + reset + save ===
    with ui.row().classes("items-end gap-4 q-mb-md"):
        pair_sel = ui.select(
            options=PAIRS, value="EURUSD", label="Paire",
            on_change=lambda: _update_correlation_label(),
        ).classes("w-40")
        reset_btn = ui.button("Reset", on_click=lambda: _reset())
        reset_btn.props("color=warning icon=refresh")
        save_btn = ui.button("Sauvegarder", on_click=lambda: _save())
        save_btn.props("color=primary icon=save")

    # === Store checkbox references ===
    checkboxes: dict[str, ui.checkbox] = {}
    section_counters: dict[str, ui.label] = {}

    # === Build sections ===
    for key, section in SECTIONS.items():
        total = len(section["items"])
        with ui.expansion(f"{section['title']}  (0/{total})", icon="check_box_outline_blank").classes("w-full q-mb-sm") as exp:
            section_counters[key] = exp

            for item in section["items"]:
                label = item["label"]
                if not item["critical"]:
                    label = f"{label}  (bonus)"
                # Dynamic correlation label — depends on selected pair
                if item.get("dynamic_correlation"):
                    label = f"Correlations : {CORRELATIONS.get(pair_sel.value, '—')}"
                cb = ui.checkbox(label, on_change=lambda: _update_verdict()).classes("q-ml-md")
                checkboxes[item["key"]] = cb

    ui.separator().classes("q-my-md")

    # === Verdict zone ===
    with ui.card().classes("w-full q-pa-md items-center"):
        verdict_label = ui.label("INCOMPLET").classes("text-h4 text-weight-bold")
        score_label = ui.label(f"0 / {TOTAL_ITEMS}").classes("text-h6 text-grey")
        setup_label = ui.label("Cochez les criteres...").classes("text-subtitle1")

    # ------------------------------------------------------------------
    def _update_correlation_label():
        """Update the A3 checkbox label when the pair changes."""
        rule = CORRELATIONS.get(pair_sel.value, "—")
        checkboxes["A3"].text = f"Correlations : {rule}"

    # ------------------------------------------------------------------
    def _update_verdict():
        # Count checked items per section
        score = 0
        section_counts: dict[str, int] = {}
        critical_missing = False
        mss_ok = False

        for sec_key, section in SECTIONS.items():
            c = 0
            for item in section["items"]:
                if checkboxes[item["key"]].value:
                    c += 1
                    score += 1
                else:
                    if item["critical"]:
                        critical_missing = True
            section_counts[sec_key] = c
            # Update expansion header
            total = len(section["items"])
            section_counters[sec_key].text = f"{section['title']}  ({c}/{total})"

        # Check MSS + entry point (FVG d'impulsion ou IFVG)
        mss_ok = checkboxes["D1"].value
        fvg_ok = checkboxes["D2"].value   # FVG dans l'impulsion du MSS
        ifvg_ok = checkboxes["D3"].value  # IFVG (ancien FVG oppose invalide)
        entry_point_ok = fvg_ok or ifvg_ok

        # Determine verdict
        if score == TOTAL_ITEMS:
            verdict = "GO"
            color = "positive"
            setup = "Setup A+ — MSS + FVG impulsion + IFVG"
        elif not mss_ok:
            verdict = "NO-GO"
            color = "negative"
            setup = "MSS obligatoire manquant"
        elif not entry_point_ok:
            verdict = "NO-GO"
            color = "negative"
            setup = "Entree impossible — FVG d'impulsion ou IFVG obligatoire"
        elif critical_missing:
            verdict = "NO-GO"
            color = "negative"
            setup = "Critere critique manquant"
        elif score >= 14:
            verdict = "GO"
            color = "positive"
            if fvg_ok and ifvg_ok:
                setup = "Setup A+ — FVG impulsion + IFVG confluence"
            elif fvg_ok:
                setup = "Setup Standard — entree sur FVG d'impulsion"
            else:
                setup = "Setup Standard — entree sur IFVG"
        else:
            verdict = "INCOMPLET"
            color = "warning"
            setup = "Continuez la checklist..."

        verdict_label.text = verdict
        verdict_label.classes(replace=f"text-h4 text-weight-bold text-{color}")
        score_label.text = f"{score} / {TOTAL_ITEMS}"
        setup_label.text = setup

    def _reset():
        for cb in checkboxes.values():
            cb.set_value(False)
        _update_verdict()
        ui.notify("Checklist reinitialisee", type="info")

    async def _save():
        # Gather items cochees
        items_cochees = [k for k, cb in checkboxes.items() if cb.value]
        score = len(items_cochees)
        mss_ok = checkboxes["D1"].value
        fvg_ok = checkboxes["D2"].value
        ifvg_ok = checkboxes["D3"].value
        entry_point_ok = fvg_ok or ifvg_ok

        if score == TOTAL_ITEMS:
            verdict, setup = "GO", "A+"
        elif not mss_ok:
            verdict, setup = "NO-GO", "Skip (MSS manquant)"
        elif not entry_point_ok:
            verdict, setup = "NO-GO", "Skip (FVG/IFVG manquant)"
        elif score >= 14:
            verdict = "GO"
            if fvg_ok and ifvg_ok:
                setup = "A+"
            elif fvg_ok:
                setup = "Standard (FVG impulsion)"
            else:
                setup = "Standard (IFVG)"
        else:
            verdict, setup = "INCOMPLET", "Skip"

        entry_id = await state.save_checklist({
            "pair": pair_sel.value,
            "verdict": verdict,
            "setup_level": setup,
            "score": score,
            "items_cochees": items_cochees,
        })
        ui.notify(f"Checklist #{entry_id} sauvegardee — {verdict} ({setup})", type="positive")

    # Initial verdict calculation
    _update_verdict()
