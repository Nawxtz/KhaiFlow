"""T-181: international prefix 0066 read as +66 (backlog16 FF-2)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "
G = " ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000"


def _ok(r):
    assert r.phone == "0812345678" and r.status == "Ready"
    assert r.address_detail == "12 หมู่ 4" and r.receiver == "คุณสมชาย ใจดี"


def test_0066_glued():
    _ok(P.parse("คุณสมชาย ใจดี 0066812345678 12 ม.4" + G))


def test_0066_spaced():
    _ok(P.parse("คุณสมชาย ใจดี 0066 81 234 5678 12 ม.4" + G))


def test_plain_and_plus66_unchanged():
    _ok(P.parse(N + "12 ม.4" + G))
    _ok(P.parse("คุณสมชาย ใจดี +66812345678 12 ม.4" + G))
    _ok(P.parse("คุณสมชาย ใจดี 66812345678 12 ม.4" + G))


def test_house_number_0066_kept():
    r = P.parse(N + "0066 ม.4" + G)
    assert r.phone == "0812345678" and "0066" in r.address_detail
