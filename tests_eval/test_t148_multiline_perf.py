"""T-148: perf: multi-line _split_multi_address is superlinear (quality P-4)"""
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

LINES = "คุณเอ 0812345678\n" * 100


def test_100_lines_under_budget():
    assert best(lambda: P.parse(LINES), n=5) <= 200


def test_two_line_message_still_splits_or_flags():
    r = P.parse(BASE + "\n" + BASE)
    assert r.phone == "0812345678"


def test_base_still_ready():
    assert P.parse(BASE).status == "Ready"
