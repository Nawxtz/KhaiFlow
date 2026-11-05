"""T-163: separator leftovers dropped from address_detail (backlog13 CC-7)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "


def test_commas_and_district_word_dropped():
    r = P.parse(N + "12/3, ม.4, ต.ในเมือง, อ.เมือง, จ.ขอนแก่น, 40000")
    assert r.address_detail == "12/3, หมู่ 4" or r.address_detail == "12/3 หมู่ 4"
    assert r.zipcode == "40000" and r.status == "Ready"


def test_slashes_dropped():
    r = P.parse(N + "12/3 ม.4 ต.ในเมือง / อ.เมือง / จ.ขอนแก่น / 40000")
    assert r.address_detail == "12/3 หมู่ 4"


def test_house_number_slash_kept():
    r = P.parse(N + "12/3 ม.4 ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000")
    assert r.address_detail == "12/3 หมู่ 4"
