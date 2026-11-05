"""T-175: navy/air dotted ranks mangled in the receiver (backlog15 EE-4)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "
G = "ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000"


def _recv(rank):
    return P.parse(rank + "สมชาย ใจดี 0812345678 12 ม.4 " + G).receiver


def test_navy_air_ranks_expanded():
    assert _recv("น.อ.") == "นาวาเอกสมชาย ใจดี"
    assert _recv("จ.อ.") == "จ่าเอกสมชาย ใจดี"
    assert _recv("น.ต.") == "นาวาตรีสมชาย ใจดี"
    assert _recv("พ.จ.อ.") == "พันจ่าเอกสมชาย ใจดี"


def test_other_ranks_still_expanded():
    assert _recv("ร.ต.อ.") == "ร้อยตำรวจเอกสมชาย ใจดี"
    assert _recv("พ.อ.") == "พันเอกสมชาย ใจดี"


def test_geo_abbrevs_not_taken_as_rank():
    r = P.parse(N + "12 ม.4 " + G)
    assert r.district == "เมืองขอนแก่น" and r.province == "ขอนแก่น" and r.receiver == "คุณสมชาย ใจดี"
