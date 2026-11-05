"""T-160: a second phone after/before the address is not a second address (backlog13 CC-1)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
NAME = "คุณสมชาย ใจดี 0812345678 "
ADDR = "12 ม.4 ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000"


def _ok(r):
    assert r.status == "Ready"
    assert r.sub_district == "ในเมือง" and r.zipcode == "40000"
    assert "หมู่ 4" in r.address_detail
    assert not any("MultiAddress" in str(w) for w in (r.warnings or []))


def test_second_phone_after():
    _ok(P.parse(NAME + ADDR + " 0899999999"))


def test_two_phones_before():
    _ok(P.parse("คุณสมชาย ใจดี 0812345678 0899999999 " + ADDR))


def test_two_real_addresses_still_multi():
    r = P.parse("คุณมณี 0812345678 1/1 ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 0899999999 / คุณโอ๋ 0898765432 2/2 ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000")
    assert r.zipcode == "20130"
    assert any("MultiAddress" in str(w) for w in (r.warnings or []))


def test_single_address_unchanged():
    _ok(P.parse(NAME + ADDR))
