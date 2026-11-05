"""T-118: จ.ชม. does not leak into address_detail (backlog9 Y-3)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
NAME = "คุณสมชาย ใจดี 0812345678 "


def test_chm_province_abbrev_no_leak():
    r = P.parse(NAME + "5 ถ.ราชดำเนิน ต.ศรีภูมิ อ.เมืองเชียงใหม่ จ.ชม. 50200")
    assert r.address_detail == "5 ถนนราชดำเนิน"
    assert r.province == "เชียงใหม่"


def test_full_province_name_unchanged():
    r = P.parse(NAME + "5 ถ.ราชดำเนิน ต.ศรีภูมิ อ.เมืองเชียงใหม่ จ.เชียงใหม่ 50200")
    assert r.address_detail == "5 ถนนราชดำเนิน"


def test_glued_moo_still_split():
    r = P.parse(NAME + "12 บ้านสวนม.3 ต.สุเทพ อ.เมือง จ.เชียงใหม่ 50200")
    assert "หมู่ 3" in r.address_detail
