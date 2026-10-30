from __future__ import annotations

from pathlib import Path

import pytest

from showitonce.storage import (
    LocalStorage,
    StorageError,
    StorageNotFound,
    normalize_key,
    normalize_prefix,
)


def test_normalize_key_rejects_escapes() -> None:
    assert normalize_key("/captures/cap_1//capture.json") == "captures/cap_1/capture.json"
    assert normalize_prefix("captures/cap_1") == "captures/cap_1/"
    for bad in ("", "/", "../secret", "captures/../../secret", "a/../b"):
        with pytest.raises(StorageError):
            normalize_key(bad)


def test_local_storage_round_trip(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "objects")
    storage.put_json("captures/cap_1/capture.json", {"ok": True})
    storage.put_text("captures/cap_1/narration.txt", "hello")
    assert storage.exists("captures/cap_1/capture.json")
    assert storage.get_json("captures/cap_1/capture.json") == {"ok": True}
    assert storage.get_bytes("captures/cap_1/narration.txt") == b"hello"
    assert storage.list("captures/") == [
        "captures/cap_1/capture.json",
        "captures/cap_1/narration.txt",
    ]
    assert storage.uri("captures/cap_1/narration.txt").startswith("file://")


def test_local_storage_blocks_path_traversal(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "objects")
    with pytest.raises(StorageError):
        storage.get_bytes("../../etc/passwd")
    with pytest.raises(StorageError):
        storage.put_bytes("../escape.txt", b"no")
    assert not (tmp_path / "escape.txt").exists()


def test_missing_object_raises_storage_not_found(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "objects")
    with pytest.raises(StorageNotFound):
        storage.get_bytes("nope.json")
    with pytest.raises(StorageNotFound):
        storage.get_json("nope.json")


def test_invalid_json_raises_storage_error(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "objects")
    storage.put_text("bad.json", "{not json")
    with pytest.raises(StorageError):
        storage.get_json("bad.json")


def test_copy_prefix_copies_and_rewrites_keys(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "objects")
    storage.put_text("a/one.txt", "1")
    storage.put_text("a/nested/two.txt", "2")
    copied = storage.copy_prefix("a", "b")
    assert copied == ["b/nested/two.txt", "b/one.txt"]
    assert storage.get_bytes("b/one.txt") == b"1"
