"""T-112: fuzzy-accepted ตำบล/อำเภอ token must leave address_detail (backlog5 U-3)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))


def test_fuzzy_sub_dropped_from_detail():
    r = P.parse("นางสาวสุดารัตน์ ศรีสุข 0962895625 826/53 หมู่ 2 ซ.สุขุมวิท 21 ต.ขามใหง่ อ.เมืองอุบลราชธานี จ.อุบลราชธานี")
    d = r.address_detail or ""
    assert "ขามใหง่" not in d and "อำเภอ" not in d
    assert "826/53" in d and "สุขุมวิท 21" in d


def test_exact_sub_detail_unchanged():
    r = P.parse("นางสาวสุดารัตน์ ศรีสุข 0962895625 826/53 หมู่ 2 ซ.สุขุมวิท 21 ต.ขามใหญ่ อ.เมืองอุบลราชธานี จ.อุบลราชธานี")
    d = r.address_detail or ""
    assert "826/53" in d and "สุขุมวิท 21" in d and "ขามใหญ่" not in d
