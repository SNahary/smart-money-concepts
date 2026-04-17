"""Persistent state — SQLite via aiosqlite for async compatibility with NiceGUI."""

import json
import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent / "data" / "bot_state.db"


class BotState:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        await self._create_tables()
        logger.info("State DB ready at %s", self.db_path)

    async def _create_tables(self) -> None:
        await self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS notified_obs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                pair        TEXT    NOT NULL,
                ob_index    INTEGER NOT NULL,
                top         REAL    NOT NULL,
                bottom      REAL    NOT NULL,
                direction   INTEGER NOT NULL,
                notified_at TEXT    NOT NULL DEFAULT (datetime('now')),
                UNIQUE(pair, ob_index, top, bottom)
            );

            CREATE TABLE IF NOT EXISTS backtest_runs (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                start_date      TEXT    NOT NULL,
                end_date        TEXT    NOT NULL,
                pairs           TEXT    NOT NULL,
                bias_timeframe  TEXT    NOT NULL DEFAULT '',
                ob_timeframe    TEXT    NOT NULL DEFAULT '',
                killzones       TEXT    NOT NULL DEFAULT '',
                config_json     TEXT    NOT NULL,
                total_signals   INTEGER DEFAULT 0,
                wins            INTEGER DEFAULT 0,
                losses          INTEGER DEFAULT 0,
                expired         INTEGER DEFAULT 0,
                win_rate        REAL    DEFAULT 0,
                profit_factor   REAL    DEFAULT 0,
                total_rr        REAL    DEFAULT 0,
                notes           TEXT    DEFAULT '',
                created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS backtest_signals (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id        INTEGER NOT NULL REFERENCES backtest_runs(id),
                pair          TEXT    NOT NULL,
                direction     INTEGER NOT NULL,
                bias_type     TEXT,
                signal_time   TEXT    NOT NULL,
                ob_time       TEXT,
                entry         REAL    NOT NULL,
                sl            REAL    NOT NULL,
                tp1           REAL,
                tp2           REAL,
                rr1           REAL,
                rr2           REAL,
                ob_strength   REAL,
                ob_size_pips  REAL,
                sl_pips       REAL,
                tp1_pips      REAL,
                tp2_pips      REAL,
                outcome       TEXT    NOT NULL,
                actual_rr     REAL,
                exit_time     TEXT,
                exit_price    REAL
            );

            CREATE TABLE IF NOT EXISTS signal_history (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                pair          TEXT    NOT NULL,
                direction     INTEGER NOT NULL,
                bias_type     TEXT,
                ob_time       TEXT,
                entry         REAL    NOT NULL,
                sl            REAL    NOT NULL,
                tp1           REAL,
                tp2           REAL,
                rr1           REAL,
                rr2           REAL,
                ob_strength   REAL,
                ob_size_pips  REAL,
                sl_pips       REAL,
                tp1_pips      REAL,
                tp2_pips      REAL,
                created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS checklist_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                pair            TEXT,
                verdict         TEXT,
                setup_level     TEXT,
                score           INTEGER,
                items_cochees   TEXT,
                created_at      TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS trading_journal (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                pair            TEXT    NOT NULL,
                direction       TEXT    NOT NULL,
                date_entree     TEXT    NOT NULL,
                prix_entree     REAL    NOT NULL,
                sl              REAL,
                tp              REAL,
                lot_size        REAL,
                rr              REAL,
                raison_entree   TEXT,
                emotions        TEXT,
                erreurs         TEXT,
                notes           TEXT,
                created_at      TEXT    DEFAULT (datetime('now'))
            );
            """
        )

    # ------------------------------------------------------------------
    # Dedup: have we already notified for this OB?
    # ------------------------------------------------------------------
    async def is_notified(
        self, pair: str, ob_index: int, top: float, bottom: float
    ) -> bool:
        async with self._db.execute(
            "SELECT 1 FROM notified_obs WHERE pair=? AND ob_index=? AND top=? AND bottom=?",
            (pair, ob_index, top, bottom),
        ) as cur:
            return (await cur.fetchone()) is not None

    async def mark_notified(
        self,
        pair: str,
        ob_index: int,
        top: float,
        bottom: float,
        direction: int,
    ) -> None:
        await self._db.execute(
            "INSERT OR IGNORE INTO notified_obs "
            "(pair, ob_index, top, bottom, direction) VALUES (?, ?, ?, ?, ?)",
            (pair, ob_index, top, bottom, direction),
        )
        await self._db.commit()

    # ------------------------------------------------------------------
    # Signal history
    # ------------------------------------------------------------------
    async def save_signal(self, trade: dict, bias_type: str) -> None:
        ob_time = trade.get("ob_time")
        ob_time_str = str(ob_time) if ob_time else None
        await self._db.execute(
            """INSERT INTO signal_history
               (pair, direction, bias_type, ob_time, entry, sl, tp1, tp2,
                rr1, rr2, ob_strength, ob_size_pips, sl_pips, tp1_pips, tp2_pips)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trade["symbol"],
                trade["direction"],
                bias_type,
                ob_time_str,
                trade["entry"],
                trade["sl"],
                trade.get("tp1"),
                trade.get("tp2"),
                trade.get("rr1"),
                trade.get("rr2"),
                trade.get("ob_strength"),
                trade.get("ob_size_pips"),
                trade.get("sl_pips"),
                trade.get("tp1_pips"),
                trade.get("tp2_pips"),
            ),
        )
        await self._db.commit()

    async def get_signal_history(self, limit: int = 50) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM signal_history ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in rows]

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------
    async def clear_old_notifications(self, days: int = 7) -> None:
        await self._db.execute(
            "DELETE FROM notified_obs WHERE notified_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        await self._db.commit()

    # ------------------------------------------------------------------
    # Backtest journal
    # ------------------------------------------------------------------
    async def save_backtest_run(self, result, config, notes: str = "") -> int:
        """Persist a backtest run + all its signals. Returns the run_id."""
        from bot.backtest.models import BacktestResult

        cur = await self._db.execute(
            """INSERT INTO backtest_runs
               (start_date, end_date, pairs,
                bias_timeframe, ob_timeframe, killzones,
                config_json,
                total_signals, wins, losses, expired,
                win_rate, profit_factor, total_rr, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.start_date,
                result.end_date,
                json.dumps(result.pairs),
                config.bias_timeframe,
                config.ob_timeframe,
                json.dumps(config.killzones),
                config.model_dump_json(),
                result.total_signals,
                result.wins,
                result.losses,
                result.expired,
                result.win_rate,
                result.profit_factor,
                result.total_rr,
                notes,
            ),
        )
        run_id = cur.lastrowid

        for s in result.signals:
            await self._db.execute(
                """INSERT INTO backtest_signals
                   (run_id, pair, direction, bias_type, signal_time, ob_time,
                    entry, sl, tp1, tp2, rr1, rr2,
                    ob_strength, ob_size_pips, sl_pips, tp1_pips, tp2_pips,
                    outcome, actual_rr, exit_time, exit_price)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    s.pair,
                    s.direction,
                    s.bias_type,
                    str(s.signal_time) if s.signal_time else "",
                    str(s.ob_time) if s.ob_time else None,
                    s.entry,
                    s.sl,
                    s.tp1,
                    s.tp2,
                    s.rr1,
                    s.rr2,
                    s.ob_strength,
                    s.ob_size_pips,
                    s.sl_pips,
                    s.tp1_pips,
                    s.tp2_pips,
                    s.outcome,
                    s.actual_rr,
                    str(s.exit_time) if s.exit_time else None,
                    s.exit_price,
                ),
            )

        await self._db.commit()
        logger.info("Backtest run #%d saved — %d signals", run_id, len(result.signals))
        return run_id

    async def get_backtest_runs(self, limit: int = 50) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM backtest_runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in rows]

    async def get_backtest_signals(self, run_id: int) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM backtest_signals WHERE run_id=? ORDER BY signal_time",
            (run_id,),
        ) as cur:
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in rows]

    async def update_backtest_notes(self, run_id: int, notes: str) -> None:
        await self._db.execute(
            "UPDATE backtest_runs SET notes=? WHERE id=?", (notes, run_id)
        )
        await self._db.commit()

    async def delete_backtest_run(self, run_id: int) -> None:
        await self._db.execute(
            "DELETE FROM backtest_signals WHERE run_id=?", (run_id,)
        )
        await self._db.execute(
            "DELETE FROM backtest_runs WHERE id=?", (run_id,)
        )
        await self._db.commit()
        logger.info("Backtest run #%d deleted", run_id)

    # ------------------------------------------------------------------
    # Trading journal (manual entries)
    # ------------------------------------------------------------------
    async def save_journal_entry(self, entry: dict) -> int:
        cur = await self._db.execute(
            """INSERT INTO trading_journal
               (pair, direction, date_entree, prix_entree, sl, tp,
                lot_size, rr, raison_entree, emotions, erreurs, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry["pair"],
                entry["direction"],
                entry["date_entree"],
                entry["prix_entree"],
                entry.get("sl"),
                entry.get("tp"),
                entry.get("lot_size"),
                entry.get("rr"),
                entry.get("raison_entree"),
                entry.get("emotions"),
                entry.get("erreurs"),
                entry.get("notes"),
            ),
        )
        await self._db.commit()
        return cur.lastrowid

    async def get_journal_entries(self, limit: int = 100) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM trading_journal ORDER BY date_entree DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in rows]

    async def delete_journal_entry(self, entry_id: int) -> None:
        await self._db.execute(
            "DELETE FROM trading_journal WHERE id=?", (entry_id,)
        )
        await self._db.commit()

    # ------------------------------------------------------------------
    # Checklist log
    # ------------------------------------------------------------------
    async def save_checklist(self, data: dict) -> int:
        cur = await self._db.execute(
            """INSERT INTO checklist_log
               (pair, verdict, setup_level, score, items_cochees)
               VALUES (?, ?, ?, ?, ?)""",
            (
                data.get("pair"),
                data.get("verdict"),
                data.get("setup_level"),
                data.get("score"),
                json.dumps(data.get("items_cochees", [])),
            ),
        )
        await self._db.commit()
        return cur.lastrowid

    async def get_checklists(self, limit: int = 50) -> list[dict]:
        async with self._db.execute(
            "SELECT * FROM checklist_log ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in rows]

    # ------------------------------------------------------------------
    async def close(self) -> None:
        if self._db:
            await self._db.close()
