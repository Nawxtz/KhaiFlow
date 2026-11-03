"""T-049: zip-pool fuzzy match guards its regex match with `if m:` (no logic change)."""
import os
import re

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
SRC = open("parser.py", encoding="utf-8").read()


def test_fuzzy_group_is_guarded_by_if_m():
    i = SRC.index("[FuzzyCorrection] ตำบล")
    block = SRC[SRC.rindex("m = re.search(r'(?:ตำบล|แขวง|ต\\.)", 0, i):i + 200]
    assert re.search(r"^\s*if m:\s*$", block, re.M)


def test_unique_zip_autofill_still_kept():
    r = FULL.parse("คุณเอ 0812345678 9 หมู่ 2 กระบี่ 81180")
    assert (r.sub_district, r.district, r.province) == ("หนองทะเล", "เมืองกระบี่", "กระบี่")


def test_exact_sub_still_kept():
    r = FULL.parse("นางสาวปวีณา หอมจันทร์ 0898765432 9 หมู่ 4 ต.ดอนจิก อ.พิบูลมังสาหาร จ.อุบลราชธานี 34110")
    assert (r.sub_district, r.district) == ("ดอนจิก", "พิบูลมังสาหาร")
