"""T-126: "40 000" must not stay in address_detail (probe [L272])."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

WITH_NOTE = 'คุณสมชาย ใจดี 0812345678 12 ม.4 ต.ในเมือง อ.เมือง จ.ขอนแก่น 40 000'
PLAIN = ''
LEAK = '40 000'
KEEP = '12'


def test_leak_dropped_from_detail():
    assert LEAK not in (P.parse(WITH_NOTE).address_detail or "")


def test_keep_still_in_detail():
    assert KEEP in (P.parse(WITH_NOTE).address_detail or "")


def test_house_number_with_space_not_stripped():
    d = P.parse("คุณสมชาย ใจดี 0812345678 12 หมู่ 4 ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000").address_detail or ""
    assert d == "12 หมู่ 4"
    d2 = P.parse("คุณสมชาย ใจดี 0812345678 4 0 ม.4 ต.ในเมือง อ.เมือง จ.ขอนแก่น 40 000").address_detail or ""
    assert "4 0" in d2
