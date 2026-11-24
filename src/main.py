import os
import json
from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

APP_VERSION = os.getenv("APP_VERSION", "dev")

app = FastAPI(title="to-do-list-api")


class TaskIn(BaseModel):
    title: str
    done: bool = False


# ---------- Almacenamiento ----------
class MemoryStore:
    """Solo para desarrollo local y pruebas."""
    def __init__(self):
        self.tasks = []

    def list_tasks(self):
        return self.tasks

    def add_task(self, title, done):
        task = {"id": len(self.tasks) + 1, "title": title, "done": done}
        self.tasks.append(task)
        return task

    def ping(self):
        return True


class PostgresStore:
    def __init__(self):
        import boto3
        client = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION", "us-east-1"))
        secret = json.loads(
            client.get_secret_value(SecretId=os.environ["SECRET_NAME"])["SecretString"]
        )
        self.conn_args = dict(
            host=secret["host"],
            port=secret.get("port", 5432),
            dbname=secret["dbname"],
            user=secret["username"],
            password=secret["password"],
            connect_timeout=5,
        )
        self._init_table()

    def _connect(self):
        import psycopg2
        return psycopg2.connect(**self.conn_args)

    def _init_table(self):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS tasks (
                       id SERIAL PRIMARY KEY,
                       title TEXT NOT NULL,
                       done BOOLEAN NOT NULL DEFAULT FALSE
                   )"""
            )

    def list_tasks(self):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT id, title, done FROM tasks ORDER BY id")
            return [{"id": r[0], "title": r[1], "done": r[2]} for r in cur.fetchall()]

    def add_task(self, title, done):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tasks (title, done) VALUES (%s, %s) RETURNING id",
                (title, done),
            )
            return {"id": cur.fetchone()[0], "title": title, "done": done}

    def ping(self):
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            return True


_store = None


def get_store():
    global _store
    if _store is None:
        if os.getenv("DB_BACKEND", "postgres") == "memory":
            _store = MemoryStore()
        else:
            _store = PostgresStore()
    return _store


# ---------- Endpoints ----------
@app.get("/tasks")
def list_tasks(store=Depends(get_store)):
    return store.list_tasks()


@app.post("/tasks", status_code=201)
def create_task(task: TaskIn, store=Depends(get_store)):
    return store.add_task(task.title, task.done)


@app.get("/version")
def version():
    return {"version": APP_VERSION}


@app.get("/health")
def health(store=Depends(get_store)):
    now = datetime.now(timezone.utc).isoformat()
    try:
        store.ping()
        return {"status": "OK", "version": APP_VERSION, "timestamp": now}
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "FAIL", "version": APP_VERSION, "timestamp": now},
        )