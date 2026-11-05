"""T-113: a road/soi name equal to a sub-district of the typed district is never the sub (backlog6 V-1, Q1)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
NAME = "คุณสมชาย ใจดี 0812345678 "


def test_road_name_is_no_sub():
    for t in ("134 ถนนมิตรภาพ อ.สีคิ้ว จ.นครราชสีมา 30140",
              "134 ซ.ในเวียง อ.เมืองแพร่ จ.แพร่ 54000",
              "99 ถนน สุเทพ อ.เมืองเชียงใหม่ จ.เชียงใหม่ 50200"):
        r = P.parse(NAME + t)
        assert r.sub_district is None, t
        assert r.status == "Needs confirmation", t


def test_typed_sub_with_road_still_ready():
    r = P.parse(NAME + "134 ถนนมิตรภาพ ต.ลาดบัวขาว อ.สีคิ้ว จ.นครราชสีมา 30340")
    assert (r.sub_district, r.status) == ("ลาดบัวขาว", "Ready")
    r = P.parse(NAME + "99 ถนนสุเทพ ต.สุเทพ อ.เมืองเชียงใหม่ จ.เชียงใหม่ 50200")
    assert (r.sub_district, r.status) == ("สุเทพ", "Ready")


def test_typed_sub_same_name_as_road_stays_ready():
    r = P.parse(NAME + "134 ต.มิตรภาพ อ.สีคิ้ว จ.นครราชสีมา 30140")
    assert (r.sub_district, r.status) == ("มิตรภาพ", "Ready")
