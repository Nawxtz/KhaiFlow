"""T-172: typo district word dropped (backlog14 DD-5)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "
G = "ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000"


def test_typo_word_dropped():
    r = P.parse(N + "12 ม.4 ต.ในเมือง อ.เมีองขอนแก่น จ.ขอนแก่น 40000")
    assert r.address_detail == "12 หมู่ 4"


def test_road_name_kept():
    r = P.parse(N + "12 ม.4 ถนนเมืองใหม่ " + G)
    assert "ถนนเมืองใหม่" in r.address_detail
