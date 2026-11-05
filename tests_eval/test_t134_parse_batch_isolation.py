"""T-134: bug: parse_batch aborts on a None item and leaks exception text (quality Q-2)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
BASE = "คุณสมชาย ใจดี 99/9 ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 0812345678"


class _Boom:
    def __len__(self):
        raise RuntimeError("secret detail")

    def __str__(self):
        raise RuntimeError("secret detail")


def test_bad_item_isolated(monkeypatch):
    real = P.parse

    def fake(t):
        if t is None:
            raise TypeError("secret detail")
        return real(t)

    monkeypatch.setattr(P, "parse", fake)
    out = P.parse_batch(["x", None, BASE])
    assert len(out) == 3
    assert out[1].status == "Error"


def test_no_exception_text_leak(monkeypatch):
    def fake(t):
        raise TypeError("secret detail")

    monkeypatch.setattr(P, "parse", fake)
    out = P.parse_batch([None])
    assert "TypeError" not in " ".join(out[0].warnings) and "secret" not in " ".join(out[0].warnings)


def test_good_item_still_ready():
    assert P.parse_batch([BASE])[0].status == "Ready"
