"""T-164: bare province short forms dropped from address_detail (backlog13 CC-4)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "


def _d(tail):
    return P.parse(N + tail).address_detail


def test_short_forms_dropped():
    assert _d("12 ม.4 ต.ตลาด อ.เมือง สุราษฎร์ฯ 84000") == "12 หมู่ 4"
    assert _d("12 ม.4 ต.ตลาด อ.เมือง สุราษฎร์ 84000") == "12 หมู่ 4"
    assert _d("12 ม.4 ต.หมากแข้ง อ.เมือง อุดร. 41000") == "12 หมู่ 4"
    assert _d("12 ม.4 ต.ในเมือง อ.เมือง ขก. 40000") == "12 หมู่ 4"
    assert _d("12 ม.4 ต.ประตูชัย อ.พระนครศรีอยุธยา อยุธยา 13000") == "12 หมู่ 4"


def test_soi_name_like_province_kept():
    assert _d("12 ซ.นนท์ 3 ต.บางกระสอ อ.เมือง นนทบุรี 11000") == "12 ซอยนนท์ 3"
