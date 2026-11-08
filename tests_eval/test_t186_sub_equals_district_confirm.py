"""T-186: sub typed equal to the district name, fuzzy-guessed from another district: Needs confirmation (backlog17 GG-1 part 1)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 12 ม.4 "


def test_sub_equals_district_needs_confirmation():
    r = P.parse(N + "ต.กระนวน อ.กระนวน จ.ขอนแก่น 40170")
    assert r.district == "กระนวน" and r.status == "Needs confirmation"


def test_valid_triple_still_ready():
    r = P.parse(N + "ต.กระนวน อ.ซำสูง จ.ขอนแก่น 40170")
    assert r.sub_district == "กระนวน" and r.district == "ซำสูง"


def test_real_sub_and_typo_unchanged():
    r = P.parse(N + "ต.หางดง อ.หางดง จ.เชียงใหม่ 50230")
    assert r.status == "Ready" and r.sub_district == "หางดง"
    r = P.parse(N + "ต.ในเมิอง อ.เมือง จ.ขอนแก่น 40000")
    assert r.status == "Ready" and r.sub_district == "ในเมือง"
