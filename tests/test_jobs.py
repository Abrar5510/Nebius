from __future__ import annotations

from pathlib import Path

import pytest

from showitonce.contracts import STAGE_NAMES
from showitonce.jobs import JobNotFound, SqlJobStore


def test_create_job_initialises_every_stage(tmp_path: Path) -> None:
    store = SqlJobStore(f"sqlite:///{tmp_path / 'jobs.db'}")
    job = store.create_job("cap_1", "place_cup", robot="so101", metadata={"source": "test"})
    assert job.status == "queued"
    assert job.progress == 0
    assert len(job.stages) == len(STAGE_NAMES)
    assert [stage.name for stage in job.stages] == list(STAGE_NAMES)
    assert job.metadata == {"source": "test"}
    assert job.stage("understand").status == "pending"
    assert store.get_job(job.id).id == job.id


def test_claim_and_stage_transitions(tmp_path: Path) -> None:
    store = SqlJobStore(f"sqlite:///{tmp_path / 'jobs.db'}")
    job = store.create_job("cap_1", "place_cup")
    assert store.claim_job(job.id) is True
    assert store.claim_job(job.id) is False
    assert store.get_job(job.id).status == "running"

    store.start_stage(job.id, "understand")
    running = store.get_job(job.id).stage("understand")
    assert running.status == "running"
    assert running.attempts == 1

    store.finish_stage(job.id, "understand", {"summary": "done"})
    finished = store.get_job(job.id)
    assert finished.stage("understand").status == "succeeded"
    assert finished.stage("understand").output["summary"] == "done"
    assert finished.progress == 1

    store.fail_stage(job.id, "reconstruct", "boom")
    store.update_job(job.id, status="failed", error="boom")
    failed = store.get_job(job.id)
    assert failed.stage("reconstruct").status == "failed"
    assert failed.stage("reconstruct").error == "boom"
    assert failed.status == "failed"


def test_claim_next_queued_and_list_jobs(tmp_path: Path) -> None:
    store = SqlJobStore(f"sqlite:///{tmp_path / 'jobs.db'}")
    first = store.create_job("cap_1", "first")
    assert [job.id for job in store.list_jobs()] == [first.id]
    assert store.claim_next_queued() == first.id
    assert store.get_job(first.id).status == "running"
    assert store.claim_next_queued() is None

    second = store.create_job("cap_2", "second")
    assert [job.id for job in store.list_jobs(status="queued")] == [second.id]
    assert store.claim_next_queued() == second.id
    assert store.get_job(second.id).status == "running"
    assert store.claim_next_queued() is None


def test_job_conflict_and_missing_job(tmp_path: Path) -> None:
    store = SqlJobStore(f"sqlite:///{tmp_path / 'jobs.db'}")
    with pytest.raises(JobNotFound):
        store.get_job("job_missing")
    job = store.create_job("cap_1", "place_cup")
    assert store.claim_job(job.id)
    assert store.claim_job(job.id) is False
    # A second claim is a conflict, not a silent rerun.
    assert not store.claim_job(job.id)


def test_events_are_append_only_and_ordered(tmp_path: Path) -> None:
    store = SqlJobStore(f"sqlite:///{tmp_path / 'jobs.db'}")
    job = store.create_job("cap_1", "place_cup")
    first = store.add_event(job.id, "one", kind="job.queued")
    second = store.add_event(job.id, "two", stage="understand", kind="stage.started", data={"x": 1})
    third = store.add_event(job.id, "three", kind="job.succeeded")
    assert (first.seq, second.seq, third.seq) == (1, 2, 3)
    events = store.get_events(job.id)
    assert [event.message for event in events] == ["one", "two", "three"]
    assert events[1].stage == "understand"
    assert events[1].data == {"x": 1}
    assert [event.seq for event in store.get_events(job.id, after=1)] == [2, 3]
    assert len(store.get_events(job.id, limit=2)) == 2


def test_metadata_update_round_trips(tmp_path: Path) -> None:
    store = SqlJobStore(f"sqlite:///{tmp_path / 'jobs.db'}")
    job = store.create_job("cap_1", "place_cup")
    store.update_job(job.id, metadata={"phase": 2}, status="cancelled")
    updated = store.get_job(job.id)
    assert updated.metadata == {"phase": 2}
    assert updated.status == "cancelled"
    with pytest.raises(ValueError):
        store.update_job(job.id, nonsense=True)
