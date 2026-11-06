"""T-177: '(+66)', '(66)', '+66 (0)' phone forms not read (backlog15 EE-2)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "
G = "ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000"


def test_paren_66_forms_read():
    for ph in ("(+66)812345678", "+66 (0)81 234 5678", "(66)812345678"):
        r = P.parse("คุณสมชาย ใจดี " + ph + " 12 ม.4 " + G)
        assert r.phone == "0812345678" and r.address_detail == "12 หมู่ 4", ph
        assert r.status == "Ready", ph


def test_plain_plus_66_unchanged():
    for ph in ("+66812345678", "+66-81-234-5678"):
        r = P.parse("คุณสมชาย ใจดี " + ph + " 12 ม.4 " + G)
        assert r.phone == "0812345678" and r.address_detail == "12 หมู่ 4", ph


def test_plain_phone_stays():
    r = P.parse(N + "12 ม.4 " + G)
    assert r.phone == "0812345678" and r.address_detail == "12 หมู่ 4"
