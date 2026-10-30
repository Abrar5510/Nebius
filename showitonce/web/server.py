"""Zero-dependency dashboard API and static file server."""

from __future__ import annotations

import json
import mimetypes
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from ..contracts import STAGE_BY_NAME
from ..demo import seed_demo_capture
from ..jobs import JobNotFound
from ..service import Service
from ..storage import StorageNotFound


def _stage_defs() -> list[dict]:
    return [
        {
            "name": stage.name,
            "letter": stage.letter,
            "title": stage.title,
            "description": stage.description,
        }
        for stage in STAGE_BY_NAME.values()
    ]


def make_handler(service: Service, static_dir: Path):
    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "ShowItOnce/0.1"

        def log_message(self, fmt: str, *args) -> None:
            if os.environ.get("SHOWITONCE_HTTP_LOG"):
                super().log_message(fmt, *args)

        # -- helpers ---------------------------------------------------
        def _send_json(self, payload, status=HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_bytes(self, body: bytes, content_type: str, status=HTTPStatus.OK) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _error(self, message: str, status=HTTPStatus.BAD_REQUEST) -> None:
            self._send_json({"error": message}, status=status)

        def _body(self) -> dict:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0:
                return {}
            if length > 1_000_000:
                raise ValueError("request body too large")
            raw = self.rfile.read(length)
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("body must be valid JSON") from exc
            if not isinstance(value, dict):
                raise ValueError("body must be a JSON object")
            return value

        def _static(self, raw_path: str) -> None:
            relative = unquote(raw_path.lstrip("/"))
            path = (static_dir / relative).resolve()
            if path != static_dir.resolve() and static_dir.resolve() not in path.parents:
                self._error("forbidden", HTTPStatus.FORBIDDEN)
                return
            if not path.is_file():
                self._error("not found", HTTPStatus.NOT_FOUND)
                return
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self._send_bytes(path.read_bytes(), content_type)

        # -- routes ----------------------------------------------------
        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            try:
                if path in {"/", "/index.html"}:
                    self._static("index.html")
                elif path.startswith("/static/"):
                    self._static(path[len("/static/") :])
                elif path == "/api/health":
                    health = service.health()
                    health["stage_defs"] = _stage_defs()
                    self._send_json(health)
                elif path == "/api/captures":
                    self._send_json({"captures": service.list_captures()})
                elif path == "/api/jobs":
                    limit = int(query.get("limit", ["30"])[0])
                    jobs = [job.to_dict() for job in service.list_jobs(limit=limit)]
                    self._send_json({"jobs": jobs})
                elif path.startswith("/api/jobs/"):
                    self._get_job(path, query)
                elif path == "/api/library":
                    self._send_json(service.library())
                elif path.startswith("/api/library/"):
                    name = unquote(path[len("/api/library/") :])
                    version = query.get("version", [None])[0]
                    self._send_json(service.skill_manifest(name, version))
                elif path == "/api/artifact":
                    key = query.get("key", [""])[0]
                    self._get_artifact(key)
                else:
                    self._error("not found", HTTPStatus.NOT_FOUND)
            except (ValueError, StorageNotFound, JobNotFound) as exc:
                self._error(str(exc), HTTPStatus.NOT_FOUND)
            except Exception as exc:  # pragma: no cover - boundary
                self._error(f"internal error: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)

        def _get_job(self, path: str, query: dict) -> None:
            rest = path[len("/api/jobs/") :]
            if rest.endswith("/events"):
                job_id = rest[: -len("/events")]
                if not job_id:
                    self._error("job id required", HTTPStatus.NOT_FOUND)
                    return
                after = int(query.get("after", ["0"])[0])
                events = service.events(job_id, after=after)
                self._send_json({"events": events})
                return
            if not rest:
                self._error("job id required", HTTPStatus.NOT_FOUND)
                return
            job = service.get_job(rest)
            payload = job.to_dict()
            payload["stage_defs"] = _stage_defs()
            self._send_json(payload)

        def _get_artifact(self, key: str) -> None:
            if not key:
                self._error("key required", HTTPStatus.BAD_REQUEST)
                return
            if not key.startswith(("jobs/", "captures/", "library/")):
                self._error("artifact key is outside the public prefixes", HTTPStatus.FORBIDDEN)
                return
            data = service.storage.get_bytes(key)
            content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
            if key.endswith(".json"):
                content_type = "application/json; charset=utf-8"
            self._send_bytes(data, content_type)

        def do_POST(self) -> None:
            parsed = urlsplit(self.path)
            path = parsed.path
            try:
                body = self._body()
                if path == "/api/demo":
                    self._post_demo(body)
                elif path == "/api/jobs":
                    self._post_job(body)
                elif path.startswith("/api/jobs/") and path.endswith("/run"):
                    job_id = path[len("/api/jobs/") : -len("/run")]
                    self._post_run(job_id)
                else:
                    self._error("not found", HTTPStatus.NOT_FOUND)
            except (ValueError, StorageNotFound, JobNotFound) as exc:
                self._error(str(exc), HTTPStatus.BAD_REQUEST)
            except Exception as exc:  # pragma: no cover - boundary
                self._error(f"internal error: {exc}", HTTPStatus.INTERNAL_SERVER_ERROR)

        def _post_demo(self, body: dict) -> None:
            capture = seed_demo_capture(service.storage)
            try:
                pace = float(body.get("pace", 0.45))
            except (TypeError, ValueError):
                pace = 0.45
            pace = max(0.0, min(pace, 2.0))
            job = service.create_job(
                capture["capture_id"],
                skill=capture.get("skill"),
                robot=str(body.get("robot") or "so101"),
                metadata={"stage_delay_s": pace} if pace else None,
            )
            if body.get("run", True):
                service.run_job_async(job.id)
            self._send_json({"job": job.to_dict(), "capture": capture}, HTTPStatus.CREATED)

        def _post_job(self, body: dict) -> None:
            capture_id = body.get("capture_id")
            if not capture_id:
                raise ValueError("capture_id is required")
            job = service.create_job(
                str(capture_id),
                skill=body.get("skill"),
                robot=str(body.get("robot") or "so101"),
                metadata=body.get("metadata"),
            )
            if body.get("run", True):
                service.run_job_async(job.id)
            self._send_json({"job": job.to_dict()}, HTTPStatus.CREATED)

        def _post_run(self, job_id: str) -> None:
            job = service.get_job(job_id)
            if job.status == "succeeded":
                self._send_json({"job": job.to_dict()})
                return
            if job.status == "running":
                self._send_json({"job": job.to_dict()}, HTTPStatus.CONFLICT)
                return
            service.run_job_async(job_id)
            self._send_json({"job": job.to_dict()}, HTTPStatus.ACCEPTED)

    return DashboardHandler


def create_server(service: Service, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    static_dir = Path(__file__).resolve().parent / "static"
    handler = make_handler(service, static_dir)
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    server.service = service  # type: ignore[attr-defined]
    return server


def serve(service: Service, host: str = "127.0.0.1", port: int = 8765) -> None:
    server = create_server(service, host=host, port=port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
