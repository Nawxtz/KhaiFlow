"""T-166: stray ฯ after the province dropped (backlog13 CC-6)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "


def test_stray_dropped():
    r = P.parse(N + "12 ม.4 ต.ตลาด อ.เมือง สุราษฎร์ธานี ฯ 84000")
    assert r.address_detail == "12 หมู่ 4"


def test_soi_name_kept():
    r = P.parse(N + "12 ซ.บางกอก 3 ต.ตลาด อ.เมือง จ.สุราษฎร์ธานี 84000")
    assert r.address_detail == "12 ซอยบางกอก 3"


def test_normal_unchanged():
    r = P.parse(N + "12 ม.4 ต.ตลาด อ.เมือง จ.สุราษฎร์ธานี 84000")
    assert r.address_detail == "12 หมู่ 4"
