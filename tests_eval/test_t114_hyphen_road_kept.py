"""T-114: a hyphenated road name keeps both halves in address_detail (backlog7 W-1)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
NAME = "คุณสมชาย ใจดี 0812345678 "


def test_hyphen_road_has_both_halves():
    r = P.parse(NAME + "12 ถ.บางนา-ตราด แขวงบางนาเหนือ เขตบางนา กทม 10260")
    assert "บางนา-ตราด" in r.address_detail
    r = P.parse(NAME + "12 ถ.เชียงใหม่-ลำปาง ต.ช้างเผือก อ.เมืองเชียงใหม่ จ.เชียงใหม่ 50300")
    assert "เชียงใหม่-ลำปาง" in r.address_detail
    assert r.province == "เชียงใหม่"
    assert r.status == "Ready"
    r = P.parse(NAME + "12 ถ.บางนา - ตราด แขวงบางนาเหนือ เขตบางนา กทม 10260")
    assert "บางนา" in r.address_detail and "ตราด" in r.address_detail


def test_colon_label_still_stripped():
    r = P.parse("ชื่อ: สมชาย ใจดี 0812345678 12 ต.สุเทพ อ.เมืองเชียงใหม่ จ.เชียงใหม่ 50200")
    assert "ชื่อ" not in (r.address_detail or "")


def test_house_range_stays():
    r = P.parse(NAME + "12/3-4 ม.5 ต.สุเทพ อ.เมืองเชียงใหม่ จ.เชียงใหม่ 50200")
    assert "12/3-4" in r.address_detail
