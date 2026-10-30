"""Shared fixtures. Every test runs against a throwaway data directory."""

from __future__ import annotations

from pathlib import Path

import pytest

from showitonce.config import Settings
from showitonce.service import Service


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    settings = Settings(
        root=tmp_path,
        mode="mock",
        execution="local",
        data_dir=data_dir,
        db_url=f"sqlite:///{data_dir / 'showitonce.db'}",
        storage_backend="local",
    )
    settings.validate()
    settings.ensure_dirs()
    return settings


@pytest.fixture()
def service(settings: Settings) -> Service:
    return Service.bootstrap(settings)
