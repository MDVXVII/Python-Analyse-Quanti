from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from scanner.core.config import DEFAULT_CONFIG_DIR, Secrets, SignalStatus, load_config


def test_default_config_loads(config):
    assert set(config.settings.books) == {"S", "M", "L"}
    assert config.signals.by_id["Q-MOM-12-1"].sign == 1
    assert config.signals.by_id["F-AGR"].sign == -1
    assert len(config.fingerprint) == 16


def test_every_weighted_family_has_signals(config):
    for book, fams in config.weights.books.items():
        for fam in fams:
            assert config.signals.for_book(book) and any(
                s.books[book] == fam for s in config.signals.for_book(book)
            )


def test_penalty_signals_have_no_book(config):
    for s in config.signals.signals:
        if s.status == SignalStatus.PENALTY:
            assert s.books == {}


def test_unknown_key_is_rejected(tmp_path: Path):
    cdir = tmp_path / "config"
    shutil.copytree(DEFAULT_CONFIG_DIR, cdir)
    data = yaml.safe_load((cdir / "settings.yaml").read_text(encoding="utf-8"))
    data["scoring"]["typo_key"] = 1
    (cdir / "settings.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(cdir)


def test_weight_family_without_signal_is_rejected(tmp_path: Path):
    cdir = tmp_path / "config"
    shutil.copytree(DEFAULT_CONFIG_DIR, cdir)
    data = yaml.safe_load((cdir / "weights.yaml").read_text(encoding="utf-8"))
    data["books"]["M"]["famille_inexistante"] = 1.0
    (cdir / "weights.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(cdir)


def test_secrets_redaction():
    s = Secrets(eodhd_api_key="SECRET123", _env_file=None)
    assert s.redact("url?api_token=SECRET123") == "url?api_token=***"


def test_provider_auto_enable(config):
    assert not config.provider_enabled("eodhd", Secrets(_env_file=None))
    assert config.provider_enabled("eodhd", Secrets(eodhd_api_key="x", _env_file=None))
    assert config.provider_enabled("sec_edgar", Secrets(_env_file=None))
