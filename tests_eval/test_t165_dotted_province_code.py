"""T-165: dotted/abbreviated province codes dropped (backlog13 CC-5)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "


def _d(tail):
    return P.parse(N + tail).address_detail


def test_dotted_code_dropped():
    assert _d("12 ม.4 ต.ในเมือง อ.เมือง จ.ข.ก. 40000") == "12 หมู่ 4"
    assert _d("12 ม.4 ต.ศรีภูมิ อ.เมือง ชม. 50200") == "12 หมู่ 4"


def test_jor_chm_still_works():
    assert _d("12 ม.4 ต.ศรีภูมิ อ.เมือง จ.ชม. 50200") == "12 หมู่ 4"


def test_normal_address_unchanged():
    r = P.parse(N + "12 ม.4 ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000")
    assert r.address_detail == "12 หมู่ 4" and r.province == "ขอนแก่น"
