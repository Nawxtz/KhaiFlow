"""T-168: parenthesised phone prefix (backlog14 DD-1)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "
G = "ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000"


def test_paren_phone_read():
    r = P.parse("คุณสมชาย ใจดี (081)2345678 12 ม.4 " + G)
    assert r.phone == "0812345678" and r.address_detail == "12 หมู่ 4"
    r = P.parse("คุณสมชาย ใจดี (081) 234-5678 12 ม.4 " + G)
    assert r.phone == "0812345678"
    r = P.parse("คุณสมชาย ใจดี (02)1234567 55 แขวงคลองเตย เขตคลองเตย กทม 10110")
    assert r.phone == "021234567"


def test_note_parens_kept():
    r = P.parse(N + "12 ม.4 (ใกล้เซเว่น) " + G)
    assert "(ใกล้เซเว่น)" in r.address_detail


def test_normal_phone_unchanged():
    r = P.parse(N + "12 ม.4 " + G)
    assert r.phone == "0812345678" and r.address_detail == "12 หมู่ 4"
