"""T-138: bug: admin dashboard FileResponse uses a cwd-relative path (quality Q-10)"""
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


def test_dashboard_from_other_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with TestClient(api.app) as c:
        assert c.get("/").status_code == 200


def test_health_still_ok():
    with TestClient(api.app) as c:
        assert c.get("/api/health").status_code == 200
