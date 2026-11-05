"""T-154: missing CSV sets PARSER_DEGRADED and logs an error (quality Q-12)"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))
import app.services.address_engine as m


def test_missing_csv_sets_flag(monkeypatch, caplog):
    monkeypatch.setattr(m, "_PARSER_INSTANCE", None)
    monkeypatch.setattr(m, "_find_csv_path", lambda: None)
    monkeypatch.setattr(m, "PARSER_DEGRADED", False, raising=False)
    with caplog.at_level(logging.ERROR):
        p = m.get_parser()
    assert m.PARSER_DEGRADED is True
    assert isinstance(p, m._FallbackAddressParser)
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


def test_csv_present_not_degraded(monkeypatch):
    if m._find_csv_path() is None:
        return
    monkeypatch.setattr(m, "_PARSER_INSTANCE", None)
    monkeypatch.setattr(m, "PARSER_DEGRADED", False, raising=False)
    p = m.get_parser()
    assert not isinstance(p, m._FallbackAddressParser)
    assert getattr(m, "PARSER_DEGRADED", False) is False
