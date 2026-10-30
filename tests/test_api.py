from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import pytest

from showitonce.service import Service
from showitonce.web.server import create_server


class Client:
    def __init__(self, base: str):
        self.base = base

    def request(self, path: str, *, method: str = "GET", body: Any = None) -> tuple[int, bytes, str]:
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, response.read(), response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), exc.headers.get("Content-Type", "")

    def json(self, path: str, *, method: str = "GET", body: Any = None) -> tuple[int, Any]:
        status, raw, _ = self.request(path, method=method, body=body)
        return status, json.loads(raw) if raw else None


@pytest.fixture()
def running_server(service: Service):
    server = create_server(service, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        yield Client(f"http://{host}:{port}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_health_and_stage_definitions(running_server: Client) -> None:
    status, payload = running_server.json("/api/health")
    assert status == 200
    assert payload["ok"] is True
    assert payload["mode"] == "mock"
    assert len(payload["stages"]) == 10
    assert [stage["letter"] for stage in payload["stage_defs"]][:3] == ["A", "B", "C"]


def test_static_dashboard_and_path_safety(running_server: Client) -> None:
    status, raw, content_type = running_server.request("/")
    assert status == 200
    assert b"SHOW IT ONCE" in raw
    assert content_type.startswith("text/html")
    status, _, _ = running_server.request("/static/app.js")
    assert status == 200
    status, _, _ = running_server.request("/static/../server.py")
    assert status in {403, 404}
    status, payload = running_server.json("/api/artifact?key=secrets.txt")
    assert status == 403


def test_demo_api_runs_pipeline_and_serves_artifacts(
    running_server: Client, service: Service
) -> None:
    status, payload = running_server.json(
        "/api/demo", method="POST", body={"robot": "so101", "pace": 0}
    )
    assert status == 201
    job_id = payload["job"]["id"]
    assert payload["job"]["status"] == "queued"

    deadline = time.time() + 10
    job = None
    while time.time() < deadline:
        status, job = running_server.json(f"/api/jobs/{job_id}")
        assert status == 200
        if job["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.05)
    assert job is not None
    assert job["status"] == "succeeded", job.get("error")
    assert job["progress"] == 10
    assert len(job["stage_defs"]) == 10

    status, events = running_server.json(f"/api/jobs/{job_id}/events?after=0")
    assert status == 200
    assert len(events["events"]) > 10
    seqs = [event["seq"] for event in events["events"]]
    assert seqs == sorted(seqs)
    status, tail = running_server.json(f"/api/jobs/{job_id}/events?after={seqs[-1]}")
    assert tail["events"] == []

    status, jobs = running_server.json("/api/jobs")
    assert status == 200
    assert jobs["jobs"][0]["id"] == job_id

    status, library = running_server.json("/api/library")
    assert status == 200
    assert library["skills"]["place-cup"]["latest"] == "0.1.0"

    status, manifest = running_server.json("/api/library/place-cup")
    assert status == 200
    assert manifest["name"] == "place-cup"

    artifact_key = job["stages"][0]["output"]["task_spec"]
    status, raw, content_type = running_server.request(
        "/api/artifact?key=" + urllib.parse.quote(artifact_key)
    )
    assert status == 200
    assert content_type.startswith("application/json")
    assert json.loads(raw)["task_name"] == "place_cup"


def test_job_api_validation(running_server: Client) -> None:
    status, payload = running_server.json("/api/jobs", method="POST", body={})
    assert status == 400
    assert "capture_id" in payload["error"]
    status, payload = running_server.json("/api/jobs/does-not-exist")
    assert status == 404
    status, payload = running_server.json("/api/jobs/does-not-exist/events")
    assert status == 404
    status, payload = running_server.json("/api/nope")
    assert status == 404


def test_post_job_for_existing_capture(running_server: Client, service: Service) -> None:
    from showitonce.demo import seed_demo_capture

    capture = seed_demo_capture(service.storage, capture_id="cap_http")
    status, payload = running_server.json(
        "/api/jobs",
        method="POST",
        body={"capture_id": capture["capture_id"], "skill": "http_place", "run": False},
    )
    assert status == 201
    job_id = payload["job"]["id"]
    assert payload["job"]["status"] == "queued"
    status, payload = running_server.json(
        "/api/jobs",
        method="POST",
        body={"capture_id": capture["capture_id"], "metadata": ["not", "an", "object"]},
    )
    assert status == 400
    assert "metadata" in payload["error"]
    status, payload = running_server.json(
        f"/api/jobs/{job_id}/run", method="POST", body={}
    )
    assert status == 202


def test_artifact_query_must_stay_in_public_prefixes(
    running_server: Client, service: Service
) -> None:
    service.storage.put_text("private/secret.txt", "no")
    status, payload = running_server.json("/api/artifact?key=private/secret.txt")
    assert status == 403
    assert "outside" in payload["error"]
