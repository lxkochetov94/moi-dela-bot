"""Local persistent storage for the Telegram-first pilot. No cloud account required."""
import json
import sqlite3
from pathlib import Path


class SQLiteStore:
    def __init__(self, path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute("PRAGMA busy_timeout=30000")
        self.initialize()

    def initialize(self):
        self.con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            owner TEXT PRIMARY KEY,
            state TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tasks (
            owner TEXT NOT NULL,
            task_id TEXT NOT NULL,
            body TEXT NOT NULL,
            PRIMARY KEY(owner,task_id)
        );
        CREATE TABLE IF NOT EXISTS reminders (
            due_ts INTEGER NOT NULL,
            reminder_id TEXT NOT NULL,
            owner TEXT NOT NULL,
            task_id TEXT NOT NULL,
            PRIMARY KEY(due_ts,reminder_id)
        );
        CREATE TABLE IF NOT EXISTS runtime (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(due_ts);
        """)

    def close(self):
        self.con.close()

    def get_state(self, owner):
        row = self.con.execute("SELECT state FROM users WHERE owner=?", (str(owner),)).fetchone()
        return json.loads(row["state"]) if row else {}

    def put_state(self, owner, state):
        self.con.execute(
            "INSERT INTO users(owner,state) VALUES(?,?) "
            "ON CONFLICT(owner) DO UPDATE SET state=excluded.state",
            (str(owner), json.dumps(state, ensure_ascii=False))
        )

    def get_task(self, owner, task_id):
        row = self.con.execute("SELECT body FROM tasks WHERE owner=? AND task_id=?",
                               (str(owner), str(task_id))).fetchone()
        return json.loads(row["body"]) if row else None

    def put_task(self, owner, task):
        self.con.execute(
            "INSERT INTO tasks(owner,task_id,body) VALUES(?,?,?) "
            "ON CONFLICT(owner,task_id) DO UPDATE SET body=excluded.body",
            (str(owner), task["id"], json.dumps(task, ensure_ascii=False))
        )

    def list_tasks(self, owner):
        rows = self.con.execute("SELECT body FROM tasks WHERE owner=? ORDER BY task_id",
                                (str(owner),)).fetchall()
        return [json.loads(row["body"]) for row in rows]

    def put_reminder(self, entry):
        self.con.execute(
            "INSERT INTO reminders(due_ts,reminder_id,owner,task_id) VALUES(?,?,?,?) "
            "ON CONFLICT(due_ts,reminder_id) DO UPDATE SET owner=excluded.owner, task_id=excluded.task_id",
            (entry["at"], entry["id"], str(entry["owner"]), entry["task_id"])
        )

    def delete_reminder(self, entry):
        self.con.execute("DELETE FROM reminders WHERE due_ts=? AND reminder_id=?",
                         (entry["at"], entry["id"]))

    def due_reminders(self, now, limit=100):
        rows = self.con.execute(
            "SELECT due_ts,reminder_id,owner,task_id FROM reminders "
            "WHERE due_ts<=? ORDER BY due_ts,reminder_id LIMIT ?",
            (int(now), int(limit))
        ).fetchall()
        return [{"at":r["due_ts"], "id":r["reminder_id"], "owner":r["owner"],
                 "task_id":r["task_id"]} for r in rows]

    def get_runtime(self, key, default=None):
        row = self.con.execute("SELECT value FROM runtime WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_runtime(self, key, value):
        self.con.execute("INSERT INTO runtime(key,value) VALUES(?,?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                         (str(key), str(value)))

    def get_owner_id(self):
        value = self.get_runtime("owner_telegram_id")
        return int(value) if value is not None else None

    def bind_owner_id(self, telegram_id):
        """First valid private /start message claims this local single-owner pilot."""
        self.con.execute(
            "INSERT OR IGNORE INTO runtime(key,value) VALUES('owner_telegram_id',?)",
            (str(int(telegram_id)),)
        )
        return self.get_owner_id()

    def get_offset(self):
        return int(self.get_runtime("next_update_offset", "0"))

    def set_offset(self, offset):
        self.set_runtime("next_update_offset", str(int(offset)))
