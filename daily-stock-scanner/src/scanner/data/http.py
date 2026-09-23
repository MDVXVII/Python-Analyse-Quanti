"""Client HTTP commun aux providers : cache disque, limitation de débit, relances, logs.

* **Cache** : la réponse est stockée sur disque (clé = empreinte de la requête sans les
  secrets) avec son horodatage de collecte. Une durée de vie par appel évite de
  re-télécharger ce qui ne change pas (faits SEC, historiques).
* **Limitation de débit** : seau à jetons par source (ex. SEC : 8 req/s < limite de 10).
* **Relances** : backoff exponentiel sur 429, 5xx et erreurs réseau ; respect de
  l'en-tête ``Retry-After``.
* **Logs** : URL (clés masquées), statut, durée, hit/miss du cache.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from scanner.core.logging import get_logger

log = get_logger(__name__)

SECRET_PARAM_NAMES = frozenset({"api_token", "apikey", "api_key", "token", "key"})


class RateLimiter:
    """Seau à jetons thread-safe : au plus ``rate`` requêtes par seconde en régime établi."""

    def __init__(self, rate_per_sec: float, burst: int = 1,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        if rate_per_sec <= 0:
            raise ValueError("rate_per_sec doit être > 0")
        self.rate = rate_per_sec
        self.capacity = max(1, burst)
        self._tokens = float(self.capacity)
        self._clock = clock
        self._sleep = sleep
        self._last = clock()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            while True:
                now = self._clock()
                self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.rate)
                self._last = now
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                self._sleep((1 - self._tokens) / self.rate)


class HttpError(RuntimeError):
    def __init__(self, status: int, url: str, body: str = "") -> None:
        super().__init__(f"HTTP {status} sur {url} : {body[:200]}")
        self.status = status
        self.url = url


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, HttpError):
        return exc.status == 429 or exc.status >= 500
    return isinstance(exc, httpx.TransportError)


def _redact_params(params: Mapping[str, Any] | None) -> dict[str, Any]:
    return {k: ("***" if k.lower() in SECRET_PARAM_NAMES else v) for k, v in (params or {}).items()}


@dataclass
class CachedResponse:
    status: int
    text: str
    fetched_at: float
    from_cache: bool

    def json(self) -> Any:
        return json.loads(self.text)


class HttpClient:
    """Client GET avec cache disque, rate limiting et relances."""

    def __init__(self, source: str, cache_dir: Path | None, rate_per_sec: float,
                 headers: Mapping[str, str] | None = None, timeout: float = 30.0,
                 max_attempts: int = 5, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.source = source
        self.cache_dir = cache_dir / source if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.limiter = RateLimiter(rate_per_sec, sleep=sleep)
        self._client = httpx.Client(headers=dict(headers or {}), timeout=timeout,
                                    transport=transport, follow_redirects=True)
        self._max_attempts = max_attempts
        self._sleep = sleep

    # -- cache ---------------------------------------------------------------------------
    def _cache_key(self, url: str, params: Mapping[str, Any] | None) -> str:
        public = {k: v for k, v in sorted((params or {}).items())
                  if k.lower() not in SECRET_PARAM_NAMES}
        raw = json.dumps({"url": url, "params": public}, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _cache_path(self, key: str) -> Path | None:
        return self.cache_dir / key[:2] / f"{key}.json" if self.cache_dir else None

    def _read_cache(self, key: str, ttl_hours: float | None) -> CachedResponse | None:
        path = self._cache_path(key)
        if path is None or ttl_hours is None or not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - payload["fetched_at"] > ttl_hours * 3600:
            return None
        return CachedResponse(payload["status"], payload["text"], payload["fetched_at"], True)

    def _write_cache(self, key: str, resp: CachedResponse) -> None:
        path = self._cache_path(key)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"status": resp.status, "text": resp.text,
                                   "fetched_at": resp.fetched_at}), encoding="utf-8")
        tmp.replace(path)

    # -- requêtes ------------------------------------------------------------------------
    def get(self, url: str, params: Mapping[str, Any] | None = None,
            ttl_hours: float | None = None) -> CachedResponse:
        """GET avec cache (si ``ttl_hours``), rate limiting et relances."""
        key = self._cache_key(url, params)
        cached = self._read_cache(key, ttl_hours)
        if cached is not None:
            log.debug("cache hit", extra={"ctx": {"source": self.source, "url": url}})
            return cached

        def _before_sleep(state: RetryCallState) -> None:
            exc = state.outcome.exception() if state.outcome else None
            log.warning("relance HTTP", extra={"ctx": {
                "source": self.source, "url": url, "attempt": state.attempt_number,
                "error": str(exc)[:200]}})

        @retry(retry=retry_if_exception(_is_retryable),
               wait=wait_exponential(multiplier=1, min=1, max=30),
               stop=stop_after_attempt(self._max_attempts), reraise=True,
               before_sleep=_before_sleep, sleep=self._sleep)
        def _do() -> CachedResponse:
            self.limiter.acquire()
            t0 = time.perf_counter()
            r = self._client.get(url, params=dict(params or {}))
            ms = round((time.perf_counter() - t0) * 1000)
            log.info("HTTP GET", extra={"ctx": {"source": self.source, "url": url,
                                                "params": _redact_params(params),
                                                "status": r.status_code, "ms": ms}})
            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    self._sleep(min(float(retry_after), 60.0))
            if r.status_code >= 400:
                raise HttpError(r.status_code, url, r.text)
            return CachedResponse(r.status_code, r.text, time.time(), False)

        resp = _do()
        if ttl_hours is not None:
            self._write_cache(key, resp)
        return resp

    def close(self) -> None:
        self._client.close()
