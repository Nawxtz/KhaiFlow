"""T-147: perf: GeoDatabase.lookup scores all ~7.4k records when the text has no geo name (quality P-3)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
BASE = "คุณสมชาย ใจดี 99/9 ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 0812345678"
import time


def best(fn, n=5):
    t = []
    for _ in range(n):
        s = time.perf_counter(); fn(); t.append((time.perf_counter() - s) * 1000)
    return min(t)


def test_digits_only_under_budget():
    assert best(lambda: P.parse("0812345678")) <= 20


def test_bare_sub_still_found():
    r = P.parse("คุณเอ 12 แสนสุข เมืองชลบุรี ชลบุรี")
    assert "ชลบุรี" in (r.province or "")


def test_base_still_ready():
    assert P.parse(BASE).status == "Ready"
