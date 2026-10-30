"""Artifact storage: local filesystem by default, Nebius Object Storage in the cloud.

Every stage reads and writes through this interface, so moving a capture from a
laptop to a Serverless Job is a configuration change, not a code change.
"""

from __future__ import annotations

import json
import mimetypes
import shutil
from pathlib import Path
from typing import Any, Protocol

from .config import Settings
from .util import atomic_write_bytes, json_dumps


class StorageError(RuntimeError):
    pass


class StorageNotFound(StorageError):
    pass


def normalize_key(key: str) -> str:
    if not key:
        raise StorageError("object key cannot be empty")
    key = key.replace("\\", "/").lstrip("/")
    parts: list[str] = []
    for part in key.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise StorageError(f"object key escapes the bucket: {key!r}")
        parts.append(part)
    if not parts:
        raise StorageError("object key cannot be empty")
    return "/".join(parts)


def normalize_prefix(prefix: str) -> str:
    prefix = prefix.replace("\\", "/").lstrip("/")
    if not prefix:
        return ""
    return normalize_key(prefix).rstrip("/") + "/"


class Storage(Protocol):
    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> str: ...
    def get_bytes(self, key: str) -> bytes: ...
    def put_json(self, key: str, value: Any) -> str: ...
    def put_text(self, key: str, value: str) -> str: ...
    def get_json(self, key: str) -> Any: ...
    def exists(self, key: str) -> bool: ...
    def list(self, prefix: str = "") -> list[str]: ...
    def delete(self, key: str) -> None: ...
    def copy_prefix(self, source: str, destination: str) -> list[str]: ...
    def uri(self, key: str) -> str: ...


class LocalStorage:
    """Filesystem-backed store used for local development and tests."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / normalize_key(key)).resolve()
        if path != self.root and self.root not in path.parents:
            raise StorageError(f"object key escapes the data directory: {key!r}")
        return path

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> str:
        path = self._path(key)
        atomic_write_bytes(path, data)
        return normalize_key(key)

    def get_bytes(self, key: str) -> bytes:
        path = self._path(key)
        try:
            return path.read_bytes()
        except FileNotFoundError as exc:
            raise StorageNotFound(f"object not found: {key}") from exc

    def put_json(self, key: str, value: Any) -> str:
        return self.put_bytes(key, json_dumps(value).encode("utf-8"), "application/json")

    def put_text(self, key: str, value: str) -> str:
        return self.put_bytes(key, value.encode("utf-8"), "text/plain; charset=utf-8")

    def get_json(self, key: str) -> Any:
        try:
            return json.loads(self.get_bytes(key))
        except json.JSONDecodeError as exc:
            raise StorageError(f"object is not valid JSON: {key}") from exc

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list(self, prefix: str = "") -> list[str]:
        if not prefix:
            base = self.root
            normalized = ""
        else:
            normalized = normalize_prefix(prefix)
            base = self._path(normalized)
        if not base.exists():
            return []
        if base.is_file():
            return [normalized.rstrip("/")]
        keys = [
            path.relative_to(self.root).as_posix()
            for path in base.rglob("*")
            if path.is_file()
        ]
        return sorted(keys)

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.is_file():
            path.unlink()

    def copy_prefix(self, source: str, destination: str) -> list[str]:
        source_prefix = normalize_prefix(source)
        destination_prefix = normalize_prefix(destination)
        copied: list[str] = []
        for key in self.list(source_prefix):
            target = destination_prefix + key[len(source_prefix) :]
            self.put_bytes(target, self.get_bytes(key))
            copied.append(target)
        return copied

    def local_path(self, key: str) -> Path:
        return self._path(key)

    def uri(self, key: str) -> str:
        return f"file://{self._path(key)}"


class S3Storage:
    """Nebius Object Storage via its S3-compatible API.

    Requires the ``cloud`` extra (boto3). Credentials can come from the environment
    or from the instance role of the machine running the job.
    """

    def __init__(self, settings: Settings):
        if not settings.s3_bucket:
            raise StorageError("NEBIUS_S3_BUCKET is required for S3 storage")
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - exercised only without extra
            raise StorageError("install the cloud extra: pip install -e '.[cloud]'") from exc

        self.bucket = settings.s3_bucket
        self.endpoint = settings.s3_endpoint
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint or None,
            region_name=settings.s3_region or None,
            aws_access_key_id=settings.s3_access_key_id or None,
            aws_secret_access_key=settings.s3_secret_access_key or None,
        )

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> str:
        key = normalize_key(key)
        extra = {"ContentType": content_type} if content_type else None
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, **(extra or {}))
        return key

    def get_bytes(self, key: str) -> bytes:
        key = normalize_key(key)
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
        except self.client.exceptions.ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"NoSuchKey", "404", "NotFound"}:
                raise StorageNotFound(f"object not found: {key}") from exc
            raise StorageError(f"could not read {key}: {exc}") from exc
        return response["Body"].read()

    def put_json(self, key: str, value: Any) -> str:
        return self.put_bytes(key, json_dumps(value).encode("utf-8"), "application/json")

    def put_text(self, key: str, value: str) -> str:
        return self.put_bytes(key, value.encode("utf-8"), "text/plain; charset=utf-8")

    def get_json(self, key: str) -> Any:
        try:
            return json.loads(self.get_bytes(key))
        except json.JSONDecodeError as exc:
            raise StorageError(f"object is not valid JSON: {key}") from exc

    def exists(self, key: str) -> bool:
        key = normalize_key(key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except self.client.exceptions.ClientError:
            return False

    def list(self, prefix: str = "") -> list[str]:
        normalized = normalize_prefix(prefix) if prefix else ""
        paginator = self.client.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=normalized):
            keys.extend(item["Key"] for item in page.get("Contents", []))
        return sorted(keys)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=normalize_key(key))

    def copy_prefix(self, source: str, destination: str) -> list[str]:
        source_prefix = normalize_prefix(source)
        destination_prefix = normalize_prefix(destination)
        copied: list[str] = []
        for key in self.list(source_prefix):
            target = destination_prefix + key[len(source_prefix) :]
            self.client.copy_object(
                Bucket=self.bucket,
                CopySource={"Bucket": self.bucket, "Key": key},
                Key=target,
            )
            copied.append(target)
        return copied

    def uri(self, key: str) -> str:
        return f"s3://{self.bucket}/{normalize_key(key)}"


def make_storage(settings: Settings) -> Storage:
    settings.ensure_dirs()
    if settings.storage_backend == "s3":
        return S3Storage(settings)
    return LocalStorage(settings.objects_dir)


def guess_content_type(path: str) -> str:
    return mimetypes.guess_type(path)[0] or "application/octet-stream"


def local_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
