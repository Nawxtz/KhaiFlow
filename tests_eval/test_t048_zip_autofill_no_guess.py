"""T-048: zip with several sub-districts: fuzzy inside the zip, else blank; never guess the first DB row."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))


def test_typo_sub_fuzzy_inside_zip():
    r = FULL.parse("นางพิมพ์ชนก สุขสวัสดิ์ 092-090-0490 650/4 หมู่ 15 ต.บานในดง อ.ท่ายาง จ.เพชรบุรี 76130")
    assert (r.sub_district, r.district, r.province) == ("บ้านในดง", "ท่ายาง", "เพชรบุรี")
    assert r.status == "Ready"


def test_missing_sub_left_blank():
    r = FULL.parse("นางอนันต์ มีสุข 0917002667 518 หมู่ 4 อ.พิบูลมังสาหาร จ.อุบลราชธานี 34110")
    assert r.sub_district is None
    assert r.district == "พิบูลมังสาหาร"
    assert r.status == "Needs confirmation"


def test_ambiguous_zip_district_blank():
    r = FULL.parse("นายอรุณี วงศ์ใหญ่ 090 152 8237 201/75 ซ.5 แขวงคลองถนน เขตสายไหม กรุงเทพมหานคร 27120")
    assert r.sub_district is None
    assert r.district is None
    assert r.province == "สระแก้ว"
    assert r.status == "Needs confirmation"


def test_unique_zip_still_autofills():
    r = FULL.parse("คุณเอ 0812345678 9 หมู่ 2 กระบี่ 81180")
    assert (r.sub_district, r.district, r.province) == ("หนองทะเล", "เมืองกระบี่", "กระบี่")


def test_exact_sub_still_kept():
    r = FULL.parse("นางสาวปวีณา หอมจันทร์ 0898765432 9 หมู่ 4 ต.ดอนจิก อ.พิบูลมังสาหาร จ.อุบลราชธานี 34110")
    assert (r.sub_district, r.district) == ("ดอนจิก", "พิบูลมังสาหาร")
