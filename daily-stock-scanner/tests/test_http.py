from __future__ import annotations

import httpx
import pytest

from scanner.data.http import HttpClient, HttpError, RateLimiter


def _client(tmp_path, handler, **kw):
    return HttpClient(
        "test",
        tmp_path,
        rate_per_sec=1000,
        transport=httpx.MockTransport(handler),
        sleep=lambda s: None,
        **kw,
    )


def test_cache_hit_avoids_second_call(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, json={"ok": True})

    c = _client(tmp_path, handler)
    assert c.get("https://x.test/a", params={"q": 1}, ttl_hours=1).json() == {"ok": True}
    r2 = c.get("https://x.test/a", params={"q": 1}, ttl_hours=1)
    assert r2.from_cache and len(calls) == 1


def test_cache_key_ignores_secret_params(tmp_path):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, text="{}")

    c = _client(tmp_path, handler)
    c.get("https://x.test/a", params={"api_token": "k1"}, ttl_hours=1)
    c.get("https://x.test/a", params={"api_token": "k2"}, ttl_hours=1)
    assert len(calls) == 1
    # la clé n'apparaît pas dans le cache sur disque
    for f in tmp_path.rglob("*.json"):
        assert "k1" not in f.read_text()


def test_retry_on_429_then_success(tmp_path):
    state = {"n": 0}

    def handler(request):
        state["n"] += 1
        if state["n"] < 3:
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, text="{}")

    c = _client(tmp_path, handler)
    assert c.get("https://x.test/b").status == 200
    assert state["n"] == 3


def test_no_retry_on_404(tmp_path):
    state = {"n": 0}

    def handler(request):
        state["n"] += 1
        return httpx.Response(404, text="absent")

    c = _client(tmp_path, handler)
    with pytest.raises(HttpError) as exc:
        c.get("https://x.test/c")
    assert exc.value.status == 404 and state["n"] == 1


def test_gives_up_after_max_attempts(tmp_path):
    def handler(request):
        return httpx.Response(503)

    c = _client(tmp_path, handler, max_attempts=3)
    with pytest.raises(HttpError):
        c.get("https://x.test/d")


def test_rate_limiter_spacing():
    now = [0.0]
    slept = []

    def clock():
        return now[0]

    def sleep(s):
        slept.append(s)
        now[0] += s

    rl = RateLimiter(rate_per_sec=4, clock=clock, sleep=sleep)
    for _ in range(5):
        rl.acquire()
    # 1 jeton initial puis 4 attentes de 0,25 s
    assert now[0] == pytest.approx(1.0)
