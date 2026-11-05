"""T-121: 2-letter province codes after จ. do not leak into detail (backlog10 Z-2)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
NAME = "คุณสมชาย ใจดี 0812345678 "


def test_khon_kaen_code():
    r = P.parse(NAME + "7 ม.1 ต.ในเมือง อ.เมือง จ.ขก. 40000")
    assert r.address_detail == "7 หมู่ 1"


def test_nakhon_ratchasima_code():
    r = P.parse(NAME + "5 ต.ในเมือง อ.เมืองนครราชสีมา จ.นม. 30000")
    assert r.address_detail == "5"


def test_chiang_mai_code_unchanged():
    r = P.parse(NAME + "5 ถ.ราชดำเนิน ต.ศรีภูมิ อ.เมืองเชียงใหม่ จ.ชม. 50200")
    assert r.address_detail == "5 ถนนราชดำเนิน"


def test_glued_moo_still_split():
    r = P.parse(NAME + "12 บ้านสวนม.3 ต.สุเทพ อ.เมือง จ.เชียงใหม่ 50200")
    assert "หมู่ 3" in r.address_detail
