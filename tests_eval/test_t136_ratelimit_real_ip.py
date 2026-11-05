"""T-136: bug: rate limiter sees the proxy IP, not X-Forwarded-For (quality Q-5)"""
import os
import sys

os.environ.pop("API_KEY", None)
sys.path.insert(0, os.getcwd())
try:
    import orjson  # noqa: F401
except ImportError:  # the gate venv has no orjson; shim it for api.py
    import json
    import types

    _o = types.ModuleType("orjson")
    _o.OPT_NON_STR_KEYS = 1
    _o.OPT_SERIALIZE_NUMPY = 2
    _o.OPT_INDENT_2 = 4
    _o.dumps = lambda c, default=None, option=None: json.dumps(c, ensure_ascii=False, default=default).encode()
    _o.loads = json.loads
    sys.modules["orjson"] = _o
from fastapi.testclient import TestClient

import api

BASE = "คุณสมชาย ใจดี 99/9 ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 0812345678"


def _client():
    api._rate_limiter._max = 1
    api._rate_limiter._clients.clear()
    return TestClient(api.app, client=("172.17.0.2", 1))


def test_distinct_forwarded_clients_separate_buckets():
    old = api._rate_limiter._max
    try:
        c = _client()
        r1 = c.get("/", headers={"X-Forwarded-For": "1.1.1.1"})
        r2 = c.get("/", headers={"X-Forwarded-For": "2.2.2.2"})
        assert r1.status_code != 429 and r2.status_code != 429
    finally:
        api._rate_limiter._max = old
        api._rate_limiter._clients.clear()


def test_same_forwarded_client_still_limited():
    old = api._rate_limiter._max
    try:
        c = _client()
        c.get("/", headers={"X-Forwarded-For": "1.1.1.1"})
        r = c.get("/", headers={"X-Forwarded-For": "1.1.1.1"})
        assert r.status_code == 429
    finally:
        api._rate_limiter._max = old
        api._rate_limiter._clients.clear()
