"""T-133: bug: parse(None) / parse(123) raises TypeError (quality Q-1)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
BASE = "คุณสมชาย ใจดี 99/9 ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 0812345678"


def test_none_returns_error():
    assert P.parse(None).status == "Error"


def test_int_returns_error():
    assert P.parse(12345).status == "Error"


def test_base_address_still_ready():
    r = P.parse(BASE)
    assert r.status == "Ready" and r.phone == "0812345678"
    assert r.receiver == "คุณสมชาย ใจดี"
