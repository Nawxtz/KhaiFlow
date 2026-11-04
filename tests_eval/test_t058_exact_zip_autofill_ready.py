"""T-058: zip auto-filled from an exact, unique sub+dist+prov match does not block Ready (Q4 a)."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
BASE = "นางสาวปวีณา หอมจันทร์ 0898765432 9 หมู่ 4 "


def test_exact_names_without_zip_is_ready():
    r = FULL.parse(BASE + "ต.ดอนจิก อ.พิบูลมังสาหาร จ.อุบลราชธานี")
    assert r.zipcode == "34110"
    assert r.status == "Ready"


def test_typed_zip_still_ready():
    r = FULL.parse(BASE + "ต.ดอนจิก อ.พิบูลมังสาหาร จ.อุบลราชธานี 34110")
    assert r.status == "Ready"


def test_missing_sub_district_still_not_ready():
    r = FULL.parse(BASE + "อ.พิบูลมังสาหาร จ.อุบลราชธานี")
    assert r.status != "Ready"


def test_typo_sub_district_without_zip_still_not_ready():
    r = FULL.parse(BASE + "ต.ดอนจิ อ.พิบูลมังสาหาร จ.อุบลราชธานี")
    assert r.status != "Ready"


def test_partial_names_zip_autofill_still_not_ready():
    r = FULL.parse(BASE + "ต.ดอนจิก อ.พิบูลมังสาหาร")
    assert r.zipcode == "34110"
    assert r.status != "Ready"
