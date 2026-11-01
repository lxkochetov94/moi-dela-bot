"""Run once on Yandex with entry point init_db.handler to initialize YDB tables."""
from storage import YDBStore


def handler(event, context):
    db=YDBStore()
    db.initialize()
    return {"statusCode":200,"body":"YDB tables created"}
