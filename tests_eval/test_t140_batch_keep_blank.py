"""T-140: bug: blank batch items are dropped so results do not match inputs (quality Q-4)"""
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


def _post(texts):
    with TestClient(api.app) as c:
        return c.post("/api/parse/batch", json={"texts": texts})


def test_blank_middle_preserved():
    r = _post([BASE, "  ", BASE])
    assert r.status_code == 200
    j = r.json()
    assert j["count"] == 3 and j["results"][1]["status"] == "Error"


def test_all_blank_still_422():
    assert _post([" ", ""]).status_code == 422


def test_good_items_still_ready():
    j = _post([BASE, " "]).json()
    assert j["results"][0]["status"] == "Ready"
