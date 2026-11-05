"""T-135: bug: /api/parse/batch items have no length cap (quality Q-3)"""
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


def test_oversize_item_422():
    assert _post([BASE, "ก" * 2001]).status_code == 422


def test_2000_char_item_ok():
    assert _post(["ก" * 1990 + " 0812345678"]).status_code == 200


def test_base_still_ok():
    assert _post([BASE]).status_code == 200
