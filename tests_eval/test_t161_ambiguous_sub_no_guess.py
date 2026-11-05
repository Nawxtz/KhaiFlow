"""T-161: sub+province with a non-unique sub leaves district and zip blank (backlog13 CC-2, Q1)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
NAME = "คุณสมชาย ใจดี 0812345678 "


def test_ambiguous_sub_blank_district_zip():
    r = P.parse(NAME + "12 ม.4 ต.ในเมือง จ.ขอนแก่น")
    assert r.district in (None, "") and r.zipcode in (None, "")
    assert r.status == "Needs confirmation"


def test_unique_sub_still_filled():
    r = P.parse(NAME + "12 ม.4 ต.บ้านเป็ด จ.ขอนแก่น")
    assert r.district and "เมือง" in r.district and r.zipcode == "40000"


def test_full_address_unchanged():
    r = P.parse(NAME + "12 ม.4 ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000")
    assert r.zipcode == "40000" and r.status == "Ready"
