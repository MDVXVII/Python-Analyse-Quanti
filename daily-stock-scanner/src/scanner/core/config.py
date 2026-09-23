"""Chargement et validation de la configuration centralisée (fichiers YAML de ``config/``).

Toute la configuration est typée avec pydantic : une faute de frappe dans un YAML
provoque une erreur explicite au démarrage plutôt qu'un comportement silencieux.
Les secrets (clés API) ne sont jamais dans les YAML : ils sont lus dans l'environnement
(voir :class:`Secrets`).
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from functools import cached_property
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BookId = Literal["S", "M", "L"]
BOOK_IDS: tuple[BookId, ...] = ("S", "M", "L")

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- settings.yaml


class ProjectCfg(_Strict):
    name: str
    base_currency: str = "EUR"
    report_timezone: str = "Europe/Paris"


class PathsCfg(_Strict):
    data_dir: Path
    cache_dir: Path
    reports_dir: Path
    journal_dir: Path
    commitments_dir: Path


class LiquidityCfg(_Strict):
    min_price_usd: float = Field(gt=0)
    min_adv_usd: float = Field(ge=0)
    min_market_cap_usd: float = Field(ge=0)
    adv_window_days: int = Field(gt=5)


class UniverseCfg(_Strict):
    tier1_indices: list[str]
    liquidity: LiquidityCfg
    pea_countries: list[str]
    ttf_min_market_cap_eur: float


class MarketCfg(_Strict):
    fx_fallback_to_usd: dict[str, float]


class BacktestUniverseRegionCfg(_Strict):
    top_n: int = Field(gt=0)
    min_price_usd: float = Field(gt=0)
    min_adv_usd: float = Field(ge=0)


class BookCfg(_Strict):
    label: str
    horizon_days: int = Field(gt=0)
    rebalance: Literal["daily", "weekly", "monthly", "quarterly"]
    top_n_long: int = Field(ge=0)
    top_n_short: int = Field(ge=0)


class ScoringCfg(_Strict):
    winsor_lower: float = Field(ge=0, lt=0.5)
    winsor_upper: float = Field(gt=0.5, le=1)
    min_group_size: int = Field(ge=2)
    z_clip: float = Field(gt=0)
    min_module_coverage: float = Field(ge=0, le=1)
    statuses_in_score: list[str]


class PenaltiesCfg(_Strict):
    liquidity_soft_multiple: float = Field(ge=1)
    liquidity_soft: float = Field(ge=0)
    beneish_threshold: float
    beneish: float = Field(ge=0)
    altman_distress: dict[BookId, float]
    binary_event_days: int = Field(ge=0)
    binary_event: dict[BookId, float]


class FundamentalsCfg(_Strict):
    max_statement_age_days: int = Field(gt=0)
    financial_sectors: list[str]
    altman_original_sectors: list[str]


class JournalCfg(_Strict):
    reference_price: Literal["next_open", "next_close"]
    eval_horizons_days: list[int]


class SnapshotItemCfg(_Strict):
    enabled: bool
    max_symbols: int = Field(ge=0)
    pause_seconds: float = Field(ge=0)


class SnapshotsCfg(_Strict):
    consensus: SnapshotItemCfg
    options: SnapshotItemCfg


class Settings(_Strict):
    project: ProjectCfg
    paths: PathsCfg
    universe: UniverseCfg
    market: MarketCfg
    backtest_universe: dict[str, BacktestUniverseRegionCfg]
    books: dict[BookId, BookCfg]
    scoring: ScoringCfg
    penalties: PenaltiesCfg
    fundamentals: FundamentalsCfg
    journal: JournalCfg
    snapshots: SnapshotsCfg


# ---------------------------------------------------------------------------- signals.yaml


class SignalStatus(StrEnum):
    CORE_VALIDATED = "core_validated"
    CORE_CANDIDATE = "core_candidate"
    OBSERVATION = "observation"
    PENALTY = "penalty"
    FILTER = "filter"
    CONTEXT = "context"
    RETIRED = "retired"


class SignalDef(_Strict):
    id: str
    name: str
    module: Literal["quant", "fundamentals", "flows", "text", "macro"]
    books: dict[BookId, str]
    sign: Literal[-1, 1]
    status: SignalStatus
    phase: int = Field(ge=1, le=5)
    refs: list[str] = Field(default_factory=list)
    description: str = ""


class SignalCatalog(_Strict):
    signals: list[SignalDef]

    @field_validator("signals")
    @classmethod
    def _unique_ids(cls, v: list[SignalDef]) -> list[SignalDef]:
        ids = [s.id for s in v]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f"identifiants de signaux dupliqués : {sorted(dup)}")
        return v

    @cached_property
    def by_id(self) -> dict[str, SignalDef]:
        return {s.id: s for s in self.signals}

    def for_book(self, book: BookId, statuses: list[str] | None = None) -> list[SignalDef]:
        """Signaux rattachés à un livre, éventuellement filtrés par statut."""
        out = [s for s in self.signals if book in s.books]
        if statuses is not None:
            out = [s for s in out if s.status.value in statuses]
        return out


# ---------------------------------------------------------------------------- weights.yaml


class WeightsChange(_Strict):
    date: str
    change: str
    evidence: str


class Weights(_Strict):
    version: int
    changelog: list[WeightsChange]
    books: dict[BookId, dict[str, float]]

    @field_validator("books")
    @classmethod
    def _positive(cls, v: dict[BookId, dict[str, float]]) -> dict[BookId, dict[str, float]]:
        for book, fams in v.items():
            if not fams:
                raise ValueError(f"livre {book} sans famille")
            if any(w < 0 for w in fams.values()):
                raise ValueError(f"poids négatif dans le livre {book}")
        return v


# ------------------------------------------------------------------------------ costs.yaml


class SpreadBucket(_Strict):
    min_adv_usd: float = Field(ge=0)
    bps: float = Field(ge=0)


class Costs(_Strict):
    commission_bps: dict[str, float]
    half_spread_bps: list[SpreadBucket]
    buy_taxes_bps: dict[str, float]
    short_borrow_bps_per_year: float = Field(ge=0)
    delisting_return: float = Field(ge=-1, le=1)

    @field_validator("half_spread_bps")
    @classmethod
    def _sorted(cls, v: list[SpreadBucket]) -> list[SpreadBucket]:
        if not v or min(b.min_adv_usd for b in v) != 0:
            raise ValueError("half_spread_bps doit contenir une tranche min_adv_usd: 0")
        return sorted(v, key=lambda b: b.min_adv_usd, reverse=True)


# ---------------------------------------------------------------------------- sources.yaml


class ProviderCfg(_Strict):
    enabled: bool | Literal["auto"]
    rate_per_sec: float | None = None
    pause_seconds: float | None = None
    cache_ttl_hours: float | None = None


class Sources(_Strict):
    providers: dict[str, ProviderCfg]
    priority: dict[str, list[str]]
    publication_lags_days: dict[Literal["annual", "semiannual", "quarterly"], int]


# ----------------------------------------------------------------------------- secrets


class Secrets(BaseSettings):
    """Clés et identifiants lus dans l'environnement ou un fichier ``.env`` (jamais versionné)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    sec_user_agent: str | None = None  # « Nom Prénom email@exemple.com » exigé par la SEC
    eodhd_api_key: str | None = None
    finnhub_api_key: str | None = None
    fred_api_key: str | None = None
    anthropic_api_key: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    report_to: str | None = None

    def redact(self, text: str) -> str:
        """Masque toute valeur secrète présente dans ``text`` (utile pour les logs)."""
        for name in (
            "eodhd_api_key",
            "finnhub_api_key",
            "fred_api_key",
            "anthropic_api_key",
            "smtp_password",
        ):
            value = getattr(self, name)
            if value:
                text = text.replace(value, "***")
        return text


# ---------------------------------------------------------------------------- agrégat


class AppConfig(_Strict):
    settings: Settings
    signals: SignalCatalog
    weights: Weights
    costs: Costs
    sources: Sources
    config_dir: Path

    @model_validator(mode="after")
    def _cross_checks(self) -> AppConfig:
        # Chaque famille pondérée doit exister dans au moins un signal du livre.
        for book, fams in self.weights.books.items():
            declared = {s.books[book] for s in self.signals.signals if book in s.books}
            missing = set(fams) - declared
            if missing:
                raise ValueError(f"familles pondérées sans signal dans le livre {book} : {missing}")
        return self

    @cached_property
    def fingerprint(self) -> str:
        """Empreinte de la configuration, enregistrée dans chaque run et dans le journal."""
        payload = {
            "settings": self.settings.model_dump(mode="json"),
            "signals": self.signals.model_dump(mode="json"),
            "weights": self.weights.model_dump(mode="json"),
            "costs": self.costs.model_dump(mode="json"),
            "sources": self.sources.model_dump(mode="json"),
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    def resolve(self, path: Path) -> Path:
        """Résout un chemin relatif de la config par rapport à la racine du projet."""
        return path if path.is_absolute() else (self.config_dir.parent / path)

    def provider_enabled(self, name: str, secrets: Secrets) -> bool:
        cfg = self.sources.providers.get(name)
        if cfg is None:
            return False
        if cfg.enabled == "auto":
            key = getattr(secrets, f"{name}_api_key", None)
            return bool(key)
        return bool(cfg.enabled)


def _load_yaml(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} : le fichier doit contenir un dictionnaire YAML")
    return data


def load_config(config_dir: Path | None = None) -> AppConfig:
    """Charge et valide toute la configuration."""
    cdir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
    return AppConfig(
        settings=Settings.model_validate(_load_yaml(cdir / "settings.yaml")),
        signals=SignalCatalog.model_validate(_load_yaml(cdir / "signals.yaml")),
        weights=Weights.model_validate(_load_yaml(cdir / "weights.yaml")),
        costs=Costs.model_validate(_load_yaml(cdir / "costs.yaml")),
        sources=Sources.model_validate(_load_yaml(cdir / "sources.yaml")),
        config_dir=cdir,
    )
