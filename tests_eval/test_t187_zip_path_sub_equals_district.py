"""T-187: sub typed equal to the district name must not be fuzzy-guessed through the zipcode path (backlog17 GG-1 part 2)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 12 ม.4 "


def test_sub_equals_district_blank_confirm():
    r = P.parse(N + "ต.แม่ริม อ.แม่ริม จ.เชียงใหม่ 50180")
    assert r.district == "แม่ริม" and r.sub_district is None and r.status == "Needs confirmation"


def test_valid_triple_still_ready():
    r = P.parse(N + "ต.หางดง อ.หางดง จ.เชียงใหม่ 50230")
    assert r.status == "Ready" and r.sub_district == "หางดง"
    r = P.parse(N + "ต.ริมใต้ อ.แม่ริม จ.เชียงใหม่ 50180")
    assert r.district == "แม่ริม" and r.sub_district == "ริมใต้"


def test_typo_sub_still_corrected():
    r = P.parse(N + "ต.ในเมิอง อ.เมือง จ.ขอนแก่น 40000")
    assert r.status == "Ready" and r.sub_district == "ในเมือง"
