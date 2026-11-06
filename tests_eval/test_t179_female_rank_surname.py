"""T-179: female rank '<rank>หญิง' drops the surname (backlog15 EE-5)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "
G = "ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000"


def _r(rank):
    return P.parse(rank + " สมหญิง ใจดี 0812345678 12 ม.4 " + G).receiver


def test_female_rank_has_surname():
    assert _r("พ.ต.อ.หญิง") == "พันตำรวจเอกหญิง สมหญิง ใจดี"
    assert _r("พันตำรวจเอกหญิง") == "พันตำรวจเอกหญิง สมหญิง ใจดี"


def test_police_captain_female_unchanged():
    assert _r("ร.ต.อ.หญิง") == "ร้อยตำรวจเอกหญิง สมหญิง ใจดี"


def test_plain_receiver_unchanged():
    assert P.parse(N + "12 ม.4 " + G).receiver == "คุณสมชาย ใจดี"
