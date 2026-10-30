"""Command line interface: demo, submit, run, worker, serve, inspect."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import __version__
from .clients import ClientError
from .config import ConfigError, Settings
from .contracts import STAGE_BY_NAME, STAGE_NAMES
from .demo import seed_demo_capture
from .jobs import Job, JobConflict, JobNotFound
from .orchestrator import Worker
from .service import Service
from .storage import StorageError, StorageNotFound

SYMBOLS = {
    "pending": "○",
    "running": "◐",
    "succeeded": "●",
    "failed": "×",
    "skipped": "–",
}


def _settings(args: argparse.Namespace) -> Settings:
    settings = Settings.from_env()
    if getattr(args, "mode", None):
        settings = settings.with_overrides(mode=args.mode)
    if getattr(args, "data_dir", None):
        data_dir = Path(args.data_dir).expanduser().resolve()
        settings = settings.with_overrides(
            data_dir=data_dir,
            db_url=f"sqlite:///{data_dir / 'showitonce.db'}",
        )
    settings.validate()
    settings.ensure_dirs()
    return settings


def _service(args: argparse.Namespace) -> Service:
    return Service.bootstrap(_settings(args))


def _print_job(job: Job, *, json_output: bool = False) -> None:
    if json_output:
        print(json.dumps(job.to_dict(), indent=2))
        return
    print(f"\n{job.skill}  ·  {job.robot}  ·  {job.status.upper()}")
    print(f"job {job.id}   capture {job.capture_id}   {job.progress}/{len(job.stages)} stages")
    print("-" * 78)
    for stage in job.stages:
        definition = STAGE_BY_NAME.get(stage.name)
        letter = definition.letter if definition else "?"
        title = definition.title if definition else stage.name
        summary = stage.output.get("summary", "")
        if stage.status == "failed":
            summary = stage.error or summary
        duration = ""
        if stage.started_at and stage.finished_at:
            try:
                from datetime import datetime

                start = datetime.fromisoformat(stage.started_at.replace("Z", "+00:00"))
                end = datetime.fromisoformat(stage.finished_at.replace("Z", "+00:00"))
                duration = f"{max(0.0, (end - start).total_seconds()):.2f}s"
            except ValueError:
                duration = ""
        print(
            f"{SYMBOLS.get(stage.status, '?')} [{letter}] {title:<12} "
            f"{stage.status:<10} {duration:>7}  {summary[:80]}"
        )
    if job.error:
        print(f"\nError: {job.error}")


def _stream_job(service: Service, job_id: str, *, json_output: bool = False) -> int:
    if json_output:
        job = service.run_job(job_id)
        print(json.dumps(job.to_dict(), indent=2))
        return 0 if job.status == "succeeded" else 1

    service.run_job_async(job_id)
    after = 0
    final: Job | None = None
    printed = False
    while True:
        for event in service.events(job_id, after=after):
            after = event["seq"]
            if event["kind"] in {"stage.completed", "stage.failed", "stage.retrying"}:
                stage = event.get("stage") or ""
                letter = STAGE_BY_NAME[stage].letter if stage in STAGE_BY_NAME else " "
                print(f"  [{letter}] {event['message']}")
                printed = True
        job = service.get_job(job_id)
        if job.status in {"succeeded", "failed", "cancelled"}:
            final = job
            # Drain the last events (job.succeeded / job.failed).
            for event in service.events(job_id, after=after):
                after = event["seq"]
                if event["kind"] in {"job.succeeded", "job.failed"}:
                    print(f"  {event['message']}")
            break
        time.sleep(0.15)
    if final is None:
        final = service.get_job(job_id)
    if not printed:
        print("  no stage events")
    _print_job(final)
    return 0 if final.status == "succeeded" else 1


def cmd_demo(args: argparse.Namespace) -> int:
    service = _service(args)
    capture = seed_demo_capture(service.storage)
    job = service.create_job(
        capture["capture_id"],
        skill=capture["skill"],
        robot=args.robot,
        metadata={"stage_delay_s": args.pace} if args.pace else None,
    )
    if args.json:
        if args.no_run:
            print(json.dumps(job.to_dict(), indent=2))
            return 0
        return _stream_job(service, job.id, json_output=True)
    print(f"Seeded synthetic capture {capture['capture_id']}.")
    print(f"Queued {job.id} with {len(job.stages)} stages in {service.settings.resolved_mode} mode.")
    if args.no_run:
        print("Run it with: showitonce run " + job.id)
        return 0
    return _stream_job(service, job.id)


def cmd_submit(args: argparse.Namespace) -> int:
    service = _service(args)
    if not service.capture_exists(args.capture_id):
        raise StorageNotFound(f"capture not found: {args.capture_id}")
    job = service.create_job(
        args.capture_id, skill=args.skill, robot=args.robot
    )
    if args.json:
        print(json.dumps(job.to_dict(), indent=2))
        return 0
    print(f"Queued {job.id} for capture {args.capture_id}.")
    if args.run:
        return _stream_job(service, job.id)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    service = _service(args)
    if args.stage:
        job = service.orchestrator.run_stage(args.job_id, args.stage)
        _print_job(job, json_output=args.json)
        return 0 if job.status != "failed" else 1
    return _stream_job(service, args.job_id, json_output=args.json)


def cmd_status(args: argparse.Namespace) -> int:
    service = _service(args)
    job = service.get_job(args.job_id)
    _print_job(job, json_output=args.json)
    return 0 if job.status != "failed" else 1


def cmd_events(args: argparse.Namespace) -> int:
    service = _service(args)
    events = service.events(args.job_id, after=args.after)
    if args.json:
        print(json.dumps(events, indent=2))
        return 0
    for event in events:
        stage = f"[{event['stage']}] " if event.get("stage") else ""
        print(f"{event['seq']:>3}  {event['kind']:<16} {stage}{event['message']}")
    return 0


def cmd_jobs(args: argparse.Namespace) -> int:
    service = _service(args)
    jobs = service.list_jobs(limit=args.limit)
    if args.json:
        print(json.dumps([job.to_dict() for job in jobs], indent=2))
        return 0
    if not jobs:
        print("No jobs yet. Run `showitonce demo`.")
        return 0
    for job in jobs:
        print(
            f"{job.id}  {job.status:<10} {job.progress:>2}/{len(job.stages)}  "
            f"{job.skill:<18} {job.robot:<8} {job.created_at}"
        )
    return 0


def cmd_captures(args: argparse.Namespace) -> int:
    service = _service(args)
    captures = service.list_captures()
    if args.json:
        print(json.dumps(captures, indent=2))
        return 0
    if not captures:
        print("No captures. Run `showitonce demo`.")
        return 0
    for capture in captures:
        print(
            f"{capture['capture_id']}  {capture.get('task_name', ''):<45} "
            f"{capture.get('duration_s', 0):>5}s  {capture.get('created_at', '')}"
        )
    return 0


def cmd_library(args: argparse.Namespace) -> int:
    service = _service(args)
    data = service.library()
    if args.json:
        print(json.dumps(data, indent=2))
        return 0
    skills = data.get("skills", {})
    if not skills:
        print("Library is empty. Run `showitonce demo` end to end first.")
        return 0
    for name, entry in sorted(skills.items()):
        print(
            f"{name:<20} latest {entry.get('latest', '?')}  "
            f"{', '.join(entry.get('versions', []))}  {entry.get('instruction', '')}"
        )
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    settings = _settings(args)
    service = Service.bootstrap(settings)
    health = service.health()
    print(f"Show It Once {__version__}")
    print(f"mode       {health['mode']}")
    print(f"execution  {health['execution']}")
    print(f"storage    {health['storage']}")
    print(f"database   {health['database']}")
    print(f"data dir   {settings.data_dir}")
    print(f"stages     {len(health['stages'])}: {', '.join(health['stages'])}")
    print(f"captures   {health['captures']}")
    print(f"jobs       {health['jobs']}")
    if settings.mode == "live":
        print(f"token factory  {'configured' if settings.nebius_api_key else 'missing NEBIUS_API_KEY'}")
        print(f"cosmos reason  {'configured' if settings.cosmos_reason_url else 'missing COSMOS_REASON_URL'}")
        print(f"parakeet       {'configured' if settings.parakeet_url else 'missing PARAKEET_URL'}")
        print(f"object storage {'configured' if settings.s3_bucket else 'missing NEBIUS_S3_BUCKET'}")
    return 0


def cmd_worker(args: argparse.Namespace) -> int:
    service = _service(args)
    worker = Worker(service.orchestrator, poll_interval_s=args.poll)
    if args.once:
        job = worker.run_once()
        if job is None:
            print("No queued jobs.")
            return 0
        _print_job(job)
        return 0 if job.status != "failed" else 1
    print(f"Worker polling every {args.poll:.1f}s. Ctrl-C to stop.")
    try:
        count = worker.run_forever(max_jobs=args.max_jobs)
    except KeyboardInterrupt:
        worker.stop()
        print("Stopped.")
        return 0
    print(f"Worker finished {count} job(s).")
    return 0


def cmd_stage(args: argparse.Namespace) -> int:
    service = _service(args)
    job = service.orchestrator.run_stage(args.job_id, args.stage)
    stage = job.stage(args.stage)
    print(json.dumps(stage.to_dict(), indent=2))
    return 0 if stage.status == "succeeded" else 1


def cmd_serve(args: argparse.Namespace) -> int:
    from .web.server import serve

    service = _service(args)
    print(f"Show It Once dashboard: http://{args.host}:{args.port}")
    print(f"mode={service.settings.resolved_mode}  data={service.settings.data_dir}")
    serve(service, host=args.host, port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="showitonce",
        description="Film yourself doing a task once on your phone. Any robot learns it.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--data-dir", help="override SHOWITONCE_DATA_DIR")
    parser.add_argument("--mode", choices=["mock", "live", "auto"], help="override SHOWITONCE_MODE")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="seed a synthetic capture and run the full pipeline")
    demo.add_argument("--robot", default="so101")
    demo.add_argument("--pace", type=float, default=0.0, help="seconds to pause between mock stages")
    demo.add_argument("--no-run", action="store_true")
    demo.add_argument("--json", action="store_true")
    demo.set_defaults(func=cmd_demo)

    submit = sub.add_parser("submit", help="queue a capture")
    submit.add_argument("capture_id")
    submit.add_argument("--skill")
    submit.add_argument("--robot", default="so101")
    submit.add_argument("--run", action="store_true")
    submit.add_argument("--json", action="store_true")
    submit.set_defaults(func=cmd_submit)

    run = sub.add_parser("run", help="run a queued job (or one stage)")
    run.add_argument("job_id")
    run.add_argument("--stage", choices=STAGE_NAMES)
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=cmd_run)

    status = sub.add_parser("status", help="show a job and its stage table")
    status.add_argument("job_id")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    events = sub.add_parser("events", help="print the append-only job event stream")
    events.add_argument("job_id")
    events.add_argument("--after", type=int, default=0)
    events.add_argument("--json", action="store_true")
    events.set_defaults(func=cmd_events)

    jobs = sub.add_parser("jobs", help="list recent jobs")
    jobs.add_argument("--limit", type=int, default=20)
    jobs.add_argument("--json", action="store_true")
    jobs.set_defaults(func=cmd_jobs)

    captures = sub.add_parser("captures", help="list captures")
    captures.add_argument("--json", action="store_true")
    captures.set_defaults(func=cmd_captures)

    library = sub.add_parser("library", help="show the shared skill library")
    library.add_argument("--json", action="store_true")
    library.set_defaults(func=cmd_library)

    check = sub.add_parser("check", help="print configuration and storage health")
    check.set_defaults(func=cmd_check)

    worker = sub.add_parser("worker", help="poll the queue and run jobs")
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--poll", type=float, default=2.0)
    worker.add_argument("--max-jobs", type=int)
    worker.set_defaults(func=cmd_worker)

    stage = sub.add_parser("stage", help="run a single stage (Serverless Jobs entrypoint)")
    stage.add_argument("stage", choices=STAGE_NAMES)
    stage.add_argument("--job", dest="job_id", required=True)
    stage.set_defaults(func=cmd_stage)

    serve_parser = sub.add_parser("serve", help="start the dashboard")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.set_defaults(func=cmd_serve)

    return parser


def cli(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (ConfigError, StorageError, StorageNotFound, ClientError, JobNotFound, JobConflict) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nstopped", file=sys.stderr)
        return 130


def main() -> None:
    raise SystemExit(cli())


if __name__ == "__main__":
    main()
