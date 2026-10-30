from __future__ import annotations

import json
from pathlib import Path

from showitonce.cli import cli


def test_cli_demo_check_and_status(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("SHOWITONCE_MODE", "mock")
    monkeypatch.delenv("SHOWITONCE_DATA_DIR", raising=False)
    monkeypatch.delenv("SHOWITONCE_DB_URL", raising=False)
    data_dir = str(tmp_path / "data")

    assert cli(["--data-dir", data_dir, "check"]) == 0
    check_output = capsys.readouterr().out
    assert "mode       mock" in check_output
    assert "stages     10" in check_output

    assert cli(["--data-dir", data_dir, "demo", "--json"]) == 0
    job = json.loads(capsys.readouterr().out)
    assert job["status"] == "succeeded"
    assert job["progress"] == 10

    assert cli(["--data-dir", data_dir, "status", job["id"], "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["id"] == job["id"]

    assert cli(["--data-dir", data_dir, "events", job["id"]]) == 0
    events_output = capsys.readouterr().out
    assert "job.succeeded" in events_output
