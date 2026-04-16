"""Backtest UI panel — run, results, journal (save/history/export CSV)."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import plotly.graph_objects as go
from nicegui import ui

from bot.backtest.engine import BacktestEngine
from bot.backtest.models import BacktestResult
from bot.config import EnvSettings, StrategyConfig
from bot.data_providers import create_provider
from bot.notifier.telegram import TelegramNotifier
from bot.state import BotState

logger = logging.getLogger(__name__)

_bt_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="backtest")


def build_backtest_panel(
    env: EnvSettings, strategy: StrategyConfig, state: BotState
) -> None:
    """Build the backtest tab contents inside the current NiceGUI container."""

    # --- Shared state ---
    ctx: dict = {"result": None, "run_id": None}

    # ================================================================
    # Sub-tabs: Run / Historique
    # ================================================================
    with ui.tabs().classes("w-full") as sub_tabs:
        run_tab = ui.tab("Lancer")
        history_tab = ui.tab("Historique")

    with ui.tab_panels(sub_tabs, value=run_tab).classes("w-full"):
        # ==============================================================
        # TAB: Lancer un backtest
        # ==============================================================
        with ui.tab_panel(run_tab):
            with ui.row().classes("items-end gap-4 q-mb-md"):
                with ui.input(
                    "Date debut",
                    value=str(date.today().replace(month=max(1, date.today().month - 1))),
                ).classes("w-40") as start_input:
                    with ui.menu().props("no-parent-event") as start_menu:
                        with ui.date().bind_value(start_input):
                            pass
                    with start_input.add_slot("append"):
                        ui.icon("edit_calendar").on("click", start_menu.open).classes("cursor-pointer")
                with ui.input(
                    "Date fin",
                    value=str(date.today()),
                ).classes("w-40") as end_input:
                    with ui.menu().props("no-parent-event") as end_menu:
                        with ui.date().bind_value(end_input):
                            pass
                    with end_input.add_slot("append"):
                        ui.icon("edit_calendar").on("click", end_menu.open).classes("cursor-pointer")
                run_btn = ui.button(
                    "Lancer le Backtest",
                    on_click=lambda: _run_backtest(),
                )
                run_btn.props("color=primary icon=play_arrow")

            progress_label = ui.label("").classes("text-caption text-grey")
            progress_bar = ui.linear_progress(value=0, show_value=False).classes("w-full")
            progress_bar.set_visibility(False)

            results_area = ui.column().classes("w-full")

        # ==============================================================
        # TAB: Historique des runs
        # ==============================================================
        with ui.tab_panel(history_tab):
            history_area = ui.column().classes("w-full")

    # ------------------------------------------------------------------
    # Run backtest
    # ------------------------------------------------------------------
    async def _run_backtest():
        start = start_input.value.strip()
        end = end_input.value.strip()
        if not start or not end:
            ui.notify("Veuillez remplir les deux dates", type="warning")
            return

        run_btn.set_enabled(False)
        progress_bar.set_visibility(True)
        progress_bar.set_value(0)
        progress_label.set_text("Connexion au provider...")

        def progress_cb(pair, current, total):
            if total > 0:
                progress_bar.set_value(current / total)
                progress_label.set_text(f"{pair}  {current}/{total} bougies")

        def do_backtest() -> BacktestResult:
            provider = create_provider(env)
            provider.connect()
            notifier = TelegramNotifier(
                token=env.telegram_bot_token,
                chat_id=env.telegram_chat_id,
                timezone=env.timezone,
            ) if env.telegram_bot_token else None
            try:
                engine = BacktestEngine(
                    provider=provider, strategy=strategy, notifier=notifier,
                )
                return engine.run(
                    start_date=start,
                    end_date=end,
                    progress_cb=progress_cb,
                )
            finally:
                provider.disconnect()

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(_bt_executor, do_backtest)
            ctx["result"] = result
            ctx["run_id"] = None
            progress_bar.set_value(1.0)
            progress_label.set_text(
                f"Termine — {result.total_signals} signaux trouves"
            )
            _render_results(results_area, result, strategy, state, ctx)
            ui.notify(
                f"Backtest termine : {result.total_signals} signaux, "
                f"{result.win_rate:.1f}% win rate",
                type="positive",
            )
        except Exception as exc:
            logger.exception("Backtest failed")
            progress_label.set_text(f"Erreur : {exc}")
            ui.notify(str(exc), type="negative")
        finally:
            run_btn.set_enabled(True)

    # ------------------------------------------------------------------
    # Refresh history on tab switch
    # ------------------------------------------------------------------
    async def _on_tab_change(e):
        tab_name = e.args if isinstance(e.args, str) else str(e.args)
        if "Historique" in tab_name:
            await _render_history(history_area, state)

    sub_tabs.on("update:model-value", _on_tab_change)


# ======================================================================
# Render backtest results
# ======================================================================

def _render_results(
    container: ui.column,
    result: BacktestResult,
    strategy: StrategyConfig,
    state: BotState,
    ctx: dict,
) -> None:
    container.clear()
    with container:
        # --- Diagnostic pipeline ---
        ui.label("Diagnostic Pipeline").classes("text-h6 q-mt-sm")
        with ui.row().classes("gap-4 flex-wrap q-mb-md"):
            _stat_card("OBs detectes", str(result.diag_total_obs_found), "grey")
            _stat_card("En confluence", str(result.diag_obs_in_confluence), "grey")
            _stat_card("Retour prix", str(result.diag_price_returns), "grey")
            _stat_card("Filtres R:R", str(result.diag_filtered_by_rr), "warning")
            _stat_card("Signaux", str(result.total_signals), "primary")

        if result.total_signals == 0:
            ui.label("Aucun signal genere sur cette periode.").classes(
                "text-h6 text-grey q-mt-md"
            )
            # Still show save button to record the diagnostic
            _render_save_section(result, strategy, state, ctx)
            return

        # --- Summary cards ---
        ui.label("Resultats").classes("text-h6")
        with ui.row().classes("gap-4 flex-wrap q-mb-md"):
            _stat_card("Wins", str(result.wins), "positive")
            _stat_card("Losses", str(result.losses), "negative")
            _stat_card("Expired", str(result.expired), "grey")
            _stat_card("Win Rate", f"{result.win_rate:.1f}%",
                        "positive" if result.win_rate >= 50 else "negative")
            _stat_card("RR Moyen (W)", f"{result.avg_rr_winners:.1f}",
                        "positive" if result.avg_rr_winners >= 2 else "grey")
            _stat_card("Profit Factor", f"{result.profit_factor:.2f}",
                        "positive" if result.profit_factor >= 1.5 else "negative")
            _stat_card("Total R", f"{result.total_rr:+.1f}R",
                        "positive" if result.total_rr > 0 else "negative")

        # --- Equity curve ---
        ui.label("Courbe d'Equity (R cumule)").classes("text-h6 q-mt-md")
        _render_equity_curve(result)

        # --- Signals detail table ---
        ui.label("Detail des Signaux").classes("text-h6 q-mt-md")
        _render_signals_table(result)

        # --- Per-pair stats ---
        if len(result.pair_stats) > 1:
            ui.label("Stats par Paire").classes("text-h6 q-mt-md")
            _render_pair_stats(result)

        # --- Save + Export ---
        _render_save_section(result, strategy, state, ctx)


# ======================================================================
# Save / Export section
# ======================================================================

def _render_save_section(
    result: BacktestResult,
    strategy: StrategyConfig,
    state: BotState,
    ctx: dict,
) -> None:
    ui.separator().classes("q-mt-lg")
    ui.label("Journal").classes("text-h6 q-mt-md")

    notes_input = ui.textarea(
        "Notes (optionnel)",
        placeholder="Ex: test swing_length=5, biais 4H, OB 30M...",
    ).classes("w-full")

    with ui.row().classes("gap-4 q-mt-sm"):
        save_btn = ui.button(
            "Sauvegarder en base",
            on_click=lambda: _save_run(result, strategy, state, ctx, notes_input, save_btn),
        )
        save_btn.props("color=primary icon=save")

        export_btn = ui.button(
            "Exporter CSV",
            on_click=lambda: _export_csv(result),
        )
        export_btn.props("color=secondary icon=download")

    save_status = ui.label("").classes("text-caption text-grey")
    ctx["save_status"] = save_status


async def _save_run(result, strategy, state, ctx, notes_input, save_btn):
    if ctx.get("run_id"):
        ui.notify("Ce run est deja sauvegarde", type="info")
        return
    notes = notes_input.value.strip() if notes_input.value else ""
    run_id = await state.save_backtest_run(result, strategy, notes)
    ctx["run_id"] = run_id
    save_btn.set_enabled(False)
    ctx["save_status"].set_text(f"Run #{run_id} sauvegarde")
    ui.notify(f"Backtest #{run_id} sauvegarde", type="positive")


def _export_csv(result: BacktestResult) -> None:
    if not result.signals:
        ui.notify("Aucun signal a exporter", type="warning")
        return

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow([
        "Date", "Paire", "Direction", "Biais", "Entry", "SL", "TP1", "TP2",
        "R:R", "Force OB %", "Taille OB pips", "Resultat", "RR Reel",
        "Date sortie", "Prix sortie",
    ])
    for s in sorted(result.signals, key=lambda x: x.signal_time):
        writer.writerow([
            str(s.signal_time) if s.signal_time else "",
            s.pair,
            "BUY" if s.direction == 1 else "SELL",
            s.bias_type,
            s.entry,
            s.sl,
            s.tp1 or "",
            s.tp2 or "",
            f"1:{s.rr1:.1f}" if s.rr1 else "",
            s.ob_strength,
            s.ob_size_pips,
            s.outcome,
            s.actual_rr if s.actual_rr is not None else "",
            str(s.exit_time) if s.exit_time else "",
            s.exit_price if s.exit_price else "",
        ])

    content = buf.getvalue()
    filename = f"backtest_{result.start_date}_{result.end_date}.csv"
    ui.download(content.encode("utf-8-sig"), filename)
    ui.notify(f"Export {filename}", type="positive")


# ======================================================================
# History tab
# ======================================================================

async def _render_history(container: ui.column, state: BotState) -> None:
    runs = await state.get_backtest_runs(limit=50)
    container.clear()
    with container:
        if not runs:
            ui.label("Aucun backtest sauvegarde.").classes("text-grey q-mt-md")
            return

        ui.label("Historique des Backtests").classes("text-h6")

        columns = [
            {"name": "id", "label": "#", "field": "id", "align": "left"},
            {"name": "created_at", "label": "Date run", "field": "created_at", "sortable": True},
            {"name": "period", "label": "Periode", "field": "period"},
            {"name": "pairs", "label": "Paires", "field": "pairs"},
            {"name": "bias_tf", "label": "TF Biais", "field": "bias_tf"},
            {"name": "ob_tf", "label": "TF OB", "field": "ob_tf"},
            {"name": "kz", "label": "Kill Zones", "field": "kz"},
            {"name": "signals", "label": "Signaux", "field": "signals"},
            {"name": "wr", "label": "Win Rate", "field": "wr"},
            {"name": "pf", "label": "Profit F.", "field": "pf"},
            {"name": "total_rr", "label": "Total R", "field": "total_rr"},
            {"name": "notes", "label": "Notes", "field": "notes"},
        ]

        rows = []
        for r in runs:
            pairs = json.loads(r["pairs"]) if isinstance(r["pairs"], str) else r["pairs"]
            kz_raw = r.get("killzones", "[]")
            kz_list = json.loads(kz_raw) if isinstance(kz_raw, str) and kz_raw else []
            kz_short = ", ".join(
                k.replace(" kill zone", "").replace(" open", " O").replace(" close", " C")
                for k in kz_list
            ) if kz_list else "-"
            rows.append({
                "id": r["id"],
                "created_at": r["created_at"][:16] if r["created_at"] else "",
                "period": f"{r['start_date']} → {r['end_date']}",
                "pairs": ", ".join(pairs) if isinstance(pairs, list) else str(pairs),
                "bias_tf": r.get("bias_timeframe", ""),
                "ob_tf": r.get("ob_timeframe", ""),
                "kz": kz_short,
                "signals": r["total_signals"],
                "wr": f"{r['win_rate']:.1f}%",
                "pf": f"{r['profit_factor']:.2f}",
                "total_rr": f"{r['total_rr']:+.1f}R",
                "notes": (r.get("notes") or "")[:60],
            })

        table = ui.table(columns=columns, rows=rows, row_key="id").classes(
            "w-full"
        ).props("dense flat bordered")

        # Detail area below the table
        detail_area = ui.column().classes("w-full q-mt-md")

        async def _show_run_detail(run_id: int):
            signals = await state.get_backtest_signals(run_id)
            detail_area.clear()
            with detail_area:
                ui.label(f"Signaux du run #{run_id}").classes("text-h6")
                if not signals:
                    ui.label("Aucun signal dans ce run.").classes("text-grey")
                    return

                sig_columns = [
                    {"name": "signal_time", "label": "Date", "field": "signal_time", "align": "left"},
                    {"name": "pair", "label": "Paire", "field": "pair"},
                    {"name": "dir", "label": "Dir", "field": "dir"},
                    {"name": "bias_type", "label": "Biais", "field": "bias_type"},
                    {"name": "entry", "label": "Entry", "field": "entry"},
                    {"name": "sl", "label": "SL", "field": "sl"},
                    {"name": "tp1", "label": "TP1", "field": "tp1"},
                    {"name": "rr1", "label": "R:R", "field": "rr1"},
                    {"name": "outcome", "label": "Resultat", "field": "outcome"},
                    {"name": "actual_rr", "label": "RR Reel", "field": "actual_rr"},
                ]
                sig_rows = [
                    {
                        "signal_time": s.get("signal_time", "")[:16],
                        "pair": s["pair"],
                        "dir": "BUY" if s["direction"] == 1 else "SELL",
                        "bias_type": s.get("bias_type", ""),
                        "entry": f"{s['entry']:.5f}",
                        "sl": f"{s['sl']:.5f}",
                        "tp1": f"{s['tp1']:.5f}" if s.get("tp1") else "-",
                        "rr1": f"1:{s['rr1']:.1f}" if s.get("rr1") else "-",
                        "outcome": s.get("outcome", ""),
                        "actual_rr": f"{s['actual_rr']:+.1f}R" if s.get("actual_rr") is not None else "-",
                    }
                    for s in signals
                ]
                ui.table(
                    columns=sig_columns, rows=sig_rows, row_key="signal_time"
                ).classes("w-full").props("dense flat bordered")

        # Wire row click to show detail
        table.on("row-click", lambda e: asyncio.ensure_future(
            _show_run_detail(e.args[1]["id"])
        ))

        # Delete button
        async def _delete_selected():
            # Use the last clicked run from detail_area
            ui.notify("Selectionnez un run dans le tableau", type="info")

        with ui.row().classes("q-mt-sm"):
            ui.label("Cliquez sur un run pour voir ses signaux").classes(
                "text-caption text-grey"
            )


# ======================================================================
# Reusable rendering helpers
# ======================================================================

def _stat_card(title: str, value: str, color: str) -> None:
    with ui.card().classes("items-center q-pa-sm min-w-[100px]"):
        ui.label(title).classes("text-caption text-grey")
        ui.label(value).classes(f"text-h6 text-{color} text-weight-bold")


def _render_equity_curve(result: BacktestResult) -> None:
    sorted_sigs = sorted(
        [s for s in result.signals if s.actual_rr is not None],
        key=lambda s: s.signal_time,
    )
    if not sorted_sigs:
        ui.label("Pas assez de donnees pour la courbe.").classes("text-grey")
        return

    cumulative = []
    running = 0.0
    times = []
    for s in sorted_sigs:
        running += s.actual_rr
        cumulative.append(running)
        times.append(str(s.signal_time))

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=times,
        y=cumulative,
        mode="lines+markers",
        marker=dict(
            color=["green" if c >= prev else "red"
                   for prev, c in zip([0] + cumulative[:-1], cumulative)],
            size=6,
        ),
        line=dict(color="dodgerblue", width=2),
        name="Equity (R)",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="grey")
    fig.update_layout(
        height=300,
        margin=dict(l=40, r=20, t=20, b=40),
        xaxis_title="",
        yaxis_title="R cumule",
        template="plotly_dark",
    )
    ui.plotly(fig).classes("w-full")


def _render_signals_table(result: BacktestResult) -> None:
    columns = [
        {"name": "time", "label": "Retour OB", "field": "time", "align": "left", "sortable": True},
        {"name": "ob_time", "label": "Cloture OB", "field": "ob_time", "sortable": True},
        {"name": "pair", "label": "Paire", "field": "pair", "sortable": True},
        {"name": "dir", "label": "Dir", "field": "dir", "sortable": True},
        {"name": "bias", "label": "Biais", "field": "bias"},
        {"name": "entry", "label": "Entry", "field": "entry"},
        {"name": "sl", "label": "SL", "field": "sl"},
        {"name": "tp1", "label": "TP1", "field": "tp1"},
        {"name": "rr", "label": "R:R", "field": "rr"},
        {"name": "outcome", "label": "Resultat", "field": "outcome", "sortable": True},
        {"name": "actual_rr", "label": "RR Reel", "field": "actual_rr", "sortable": True},
    ]
    rows = []
    for s in sorted(result.signals, key=lambda x: x.signal_time):
        outcome_label = {
            "WIN_TP1": "WIN", "LOSS": "LOSS", "EXPIRED": "EXPIRED",
            "NO_TP": "NO TP", "PENDING": "-",
        }.get(s.outcome, s.outcome)
        ob_time_str = s.ob_time.strftime("%Y-%m-%d %H:%M") if s.ob_time and hasattr(s.ob_time, "strftime") else "-"
        rows.append({
            "time": s.signal_time.strftime("%Y-%m-%d %H:%M") if s.signal_time else "",
            "ob_time": ob_time_str,
            "pair": s.pair,
            "dir": "BUY" if s.direction == 1 else "SELL",
            "bias": s.bias_type,
            "entry": f"{s.entry:.5f}",
            "sl": f"{s.sl:.5f}",
            "tp1": f"{s.tp1:.5f}" if s.tp1 else "-",
            "rr": f"1:{s.rr1:.1f}" if s.rr1 else "-",
            "outcome": outcome_label,
            "actual_rr": f"{s.actual_rr:+.1f}R" if s.actual_rr is not None else "-",
        })
    ui.table(columns=columns, rows=rows, row_key="time").classes("w-full").props(
        "dense flat bordered"
    )


def _render_pair_stats(result: BacktestResult) -> None:
    columns = [
        {"name": "pair", "label": "Paire", "field": "pair", "align": "left"},
        {"name": "signals", "label": "Signaux", "field": "signals"},
        {"name": "wins", "label": "Wins", "field": "wins"},
        {"name": "losses", "label": "Losses", "field": "losses"},
        {"name": "wr", "label": "Win Rate", "field": "wr"},
        {"name": "total_rr", "label": "Total R", "field": "total_rr"},
    ]
    rows = [
        {
            "pair": pair,
            "signals": st["signals"],
            "wins": st["wins"],
            "losses": st["losses"],
            "wr": f"{st['win_rate']:.1f}%",
            "total_rr": f"{st['total_rr']:+.1f}R",
        }
        for pair, st in result.pair_stats.items()
    ]
    ui.table(columns=columns, rows=rows, row_key="pair").classes("w-full").props(
        "dense flat bordered"
    )
