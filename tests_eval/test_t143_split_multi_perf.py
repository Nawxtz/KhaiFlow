"""T-143: perf: _split_multi_address runs full geo lookups on empty/no-name segments (quality P-1)"""
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

L43 = "คุณเอฟ 3 ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 0812345678 / 0898765432"


def test_l43_under_budget():
    assert best(lambda: P.parse(L43)) <= 16


def test_two_phone_output_still_same_shape():
    r = P.parse(L43)
    assert r.phone == "0812345678" and r.status in ("Ready", "Needs confirmation")


def test_base_still_ready():
    assert P.parse(BASE).status == "Ready"
