"""T-169: dotted ranks expand cleanly (backlog14 DD-2)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "
G = "ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000"


def _recv(rank):
    return P.parse(rank + "สมชาย ใจดี 0812345678 12 ม.4 " + G).receiver


def test_ranks_expanded():
    assert _recv("ร.ต.อ.") == "ร้อยตำรวจเอกสมชาย ใจดี"
    assert _recv("พ.อ.") == "พันเอกสมชาย ใจดี"
    assert _recv("ด.ต.") == "ดาบตำรวจสมชาย ใจดี"
    assert _recv("จ.ส.อ.") == "จ่าสิบเอกสมชาย ใจดี"


def test_geo_abbrevs_still_expand():
    r = P.parse(N + "12 ม.4 " + G)
    assert r.district == "เมืองขอนแก่น" and r.province == "ขอนแก่น"


def test_other_title_unchanged():
    assert _recv("ผศ.ดร.") == P.parse("ผศ.ดร.สมชาย ใจดี 0812345678 12 ม.4 " + G).receiver
