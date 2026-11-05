"""T-144: perf: GeoDatabase._build_candidate_pool scans ~8.6k keys per call (quality P-2)"""
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

NOZIP = "คุณเอ 12 ต.ในเมือง อ.เมือง จ.ขอนแก่น"


def test_nozip_under_budget():
    # base ~15 ms per pool build; the budget is set halfway to the target
    assert best(lambda: P.parse(NOZIP)) <= 11


def test_nozip_result_still_resolves_province():
    assert "ขอนแก่น" in (P.parse(NOZIP).province or "")


def test_base_still_ready():
    assert P.parse(BASE).status == "Ready"
