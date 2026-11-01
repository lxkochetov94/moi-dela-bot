"""YDB tables; owner is a namespaced string: tg:123, vk:123, max:123."""
TABLES = [
    """CREATE TABLE IF NOT EXISTS users (
        owner Utf8 NOT NULL,
        state Utf8,
        PRIMARY KEY (owner)
    );""",
    """CREATE TABLE IF NOT EXISTS tasks (
        owner Utf8 NOT NULL,
        task_id Utf8 NOT NULL,
        body Utf8,
        PRIMARY KEY (owner, task_id)
    );""",
    """CREATE TABLE IF NOT EXISTS reminders (
        due_ts Uint64 NOT NULL,
        reminder_id Utf8 NOT NULL,
        owner Utf8,
        task_id Utf8,
        PRIMARY KEY (due_ts, reminder_id)
    );""",
]
