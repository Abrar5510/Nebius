from __future__ import annotations

from pathlib import Path

import pytest

from showitonce.config import ConfigError, Settings, load_dotenv


def test_auto_mode_picks_hybrid_only_with_a_token_factory_key(tmp_path: Path) -> None:
    base = Settings(root=tmp_path, mode="auto")
    assert base.resolved_mode == "mock"
    assert base.with_overrides(nebius_api_key="key").resolved_mode == "hybrid"
    assert base.with_overrides(nebius_api_key="key").live_reasoning
    assert base.with_overrides(cosmos_reason_url="https://cosmos").resolved_mode == "mock"
    assert base.with_overrides(mode="mock", nebius_api_key="key").resolved_mode == "mock"


def test_sqlite_path_resolution(tmp_path: Path) -> None:
    settings = Settings(root=tmp_path, db_url="sqlite:///relative.db")
    assert settings.sqlite_path == tmp_path / "relative.db"
    absolute = tmp_path / "absolute.db"
    settings = Settings(root=tmp_path, db_url=f"sqlite:///{absolute}")
    assert settings.sqlite_path == absolute
    settings = Settings(root=tmp_path, db_url="sqlite:////tmp/other.db")
    assert settings.sqlite_path == Path("/tmp/other.db")


def test_validate_rejects_unknown_values(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        Settings(root=tmp_path, mode="turbo").validate()
    with pytest.raises(ConfigError):
        Settings(root=tmp_path, execution="magic").validate()
    with pytest.raises(ConfigError):
        Settings(root=tmp_path, storage_backend="ftp").validate()


def test_dotenv_does_not_override_the_process(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SHOWITONCE_MODE=live\nNEW_KEY=new\n")
    monkeypatch.setenv("SHOWITONCE_MODE", "mock")
    monkeypatch.delenv("NEW_KEY", raising=False)
    load_dotenv(env_file)
    import os

    assert os.environ["SHOWITONCE_MODE"] == "mock"
    assert os.environ["NEW_KEY"] == "new"
