"""Persistent YDB storage, with a memory adapter for isolated local tests."""
import json
import os
from schema import TABLES


class YDBStore:
    def __init__(self):
        import ydb
        import ydb.iam
        endpoint = os.environ["YDB_ENDPOINT"]
        database = os.environ["YDB_DATABASE"]
        # A function-bound service account receives short-lived credentials from metadata.
        credentials = ydb.iam.MetadataUrlCredentials()
        self.ydb = ydb
        self.driver = ydb.Driver(endpoint=endpoint, database=database, credentials=credentials)
        self.driver.wait(timeout=10, fail_fast=True)
        self.pool = ydb.QuerySessionPool(self.driver)

    def query(self, sql, params=None):
        if params:
            typed = {"$"+key: (value, getattr(self.ydb.PrimitiveType, kind))
                     for key, (value, kind) in params.items()}
        else:
            typed = None
        if typed is None:
            result = self.pool.execute_with_retries(sql)
        else:
            result = self.pool.execute_with_retries(sql, parameters=typed)
        return [row for group in (result or []) for row in group.rows]

    def initialize(self):
        for statement in TABLES:
            self.query(statement)

    def get_state(self, owner):
        rows = self.query("DECLARE $owner AS Utf8; SELECT state FROM users WHERE owner=$owner;",
                          {"owner": (str(owner), "Utf8")})
        return json.loads(rows[0]["state"]) if rows and rows[0]["state"] else {}

    def put_state(self, owner, state):
        self.query("DECLARE $owner AS Utf8; DECLARE $value AS Utf8; "
                   "UPSERT INTO users (owner,state) VALUES ($owner,$value);",
                   {"owner": (str(owner), "Utf8"), "value": (json.dumps(state, ensure_ascii=False), "Utf8")})

    def get_task(self, owner, task_id):
        rows = self.query("DECLARE $owner AS Utf8; DECLARE $id AS Utf8; "
                          "SELECT body FROM tasks WHERE owner=$owner AND task_id=$id;",
                          {"owner": (str(owner), "Utf8"), "id": (task_id, "Utf8")})
        return json.loads(rows[0]["body"]) if rows else None

    def put_task(self, owner, task):
        self.query("DECLARE $owner AS Utf8; DECLARE $id AS Utf8; DECLARE $body AS Utf8; "
                   "UPSERT INTO tasks (owner, task_id, body) VALUES ($owner, $id, $body);",
                   {"owner": (str(owner), "Utf8"), "id": (task["id"], "Utf8"),
                    "body": (json.dumps(task, ensure_ascii=False), "Utf8")})

    def list_tasks(self, owner):
        rows = self.query("DECLARE $owner AS Utf8; SELECT body FROM tasks WHERE owner=$owner;",
                          {"owner": (str(owner), "Utf8")})
        return [json.loads(r["body"]) for r in rows]

    def put_reminder(self, entry):
        self.query("DECLARE $due AS Uint64; DECLARE $id AS Utf8; "
                   "DECLARE $owner AS Utf8; DECLARE $task AS Utf8; "
                   "UPSERT INTO reminders (due_ts, reminder_id, owner, task_id) "
                   "VALUES ($due,$id,$owner,$task);",
                   {"due": (entry["at"], "Uint64"), "id": (entry["id"], "Utf8"),
                    "owner": (str(entry["owner"]), "Utf8"), "task": (entry["task_id"], "Utf8")})

    def delete_reminder(self, entry):
        self.query("DECLARE $due AS Uint64; DECLARE $id AS Utf8; "
                   "DELETE FROM reminders WHERE due_ts=$due AND reminder_id=$id;",
                   {"due": (entry["at"], "Uint64"), "id": (entry["id"], "Utf8")})

    def due_reminders(self, now, limit=100):
        # A range over first PK field avoids full-scanning a user's task history.
        rows = self.query("DECLARE $now AS Uint64; "
                          f"SELECT due_ts, reminder_id, owner, task_id FROM reminders "
                          f"WHERE due_ts <= $now ORDER BY due_ts LIMIT {int(limit)};",
                          {"now": (now, "Uint64")})
        return [{"at": int(r["due_ts"]), "id": r["reminder_id"],
                 "owner": str(r["owner"]), "task_id": r["task_id"]} for r in rows]


class MemoryStore:
    """Simple deterministic adapter for offline, no-account smoke tests."""
    def __init__(self):
        self.states = {}
        self.tasks = {}
        self.reminders = {}

    def initialize(self):
        return None

    def get_state(self, owner):
        return dict(self.states.get(owner, {}))

    def put_state(self, owner, state):
        self.states[owner] = dict(state)

    def get_task(self, owner, task_id):
        import copy
        return copy.deepcopy(self.tasks.get((owner, task_id)))

    def put_task(self, owner, task):
        import copy
        self.tasks[(owner, task["id"])] = copy.deepcopy(task)

    def list_tasks(self, owner):
        import copy
        return copy.deepcopy([v for (u, _), v in self.tasks.items() if u == owner])

    def put_reminder(self, entry):
        self.reminders[(entry["at"], entry["id"])] = dict(entry)

    def delete_reminder(self, entry):
        self.reminders.pop((entry["at"], entry["id"]), None)

    def due_reminders(self, now, limit=100):
        return [dict(r) for r in sorted(self.reminders.values(),key=lambda x:(x["at"],x["id"]))
                if r["at"] <= now][:limit]
