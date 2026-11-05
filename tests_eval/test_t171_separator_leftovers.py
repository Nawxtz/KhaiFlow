"""T-171: separator leftovers (backlog14 DD-4)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "
G = "ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000"


def test_separators_dropped():
    assert P.parse(N + "12 ม.4; ต.ในเมือง; อ.เมือง; จ.ขอนแก่น; 40000").address_detail == "12 หมู่ 4"
    assert P.parse(N + '"12 ม.4 ' + G + '"').address_detail == "12 หมู่ 4"


def test_slash_and_note_kept():
    assert P.parse(N + "12/3 ม.4 " + G).address_detail == "12/3 หมู่ 4"
    assert "(ใกล้เซเว่น)" in P.parse(N + "12 ม.4 (ใกล้เซเว่น) " + G).address_detail
