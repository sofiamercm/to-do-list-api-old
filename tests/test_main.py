from fastapi.testclient import TestClient

from main import app, get_store, MemoryStore


class BrokenStore(MemoryStore):
    def ping(self):
        raise RuntimeError("db down")


def make_client(store):
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app)


def test_create_and_list_tasks():
    client = make_client(MemoryStore())
    r = client.post("/tasks", json={"title": "estudiar", "done": False})
    assert r.status_code == 201
    assert r.json()["title"] == "estudiar"

    r = client.get("/tasks")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_create_task_without_title_fails():
    client = make_client(MemoryStore())
    r = client.post("/tasks", json={"done": False})
    assert r.status_code == 422


def test_version_returns_env_value():
    client = make_client(MemoryStore())
    r = client.get("/version")
    assert r.status_code == 200
    assert "version" in r.json()


def test_health_ok():
    client = make_client(MemoryStore())
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "OK"
    assert "timestamp" in body


def test_health_fail_when_db_down():
    client = make_client(BrokenStore())
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json()["status"] == "FAIL"