"""T-099: a typo'd sub-district typed with its prefix is fuzzy-matched inside the matched district (W2)."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

ADDR = "ต.เขวาสวนรินทร์ อ.เขวาสินรินทร์ จ.สุรินทร์"
MSG = "นางสาววิภาวดี ศรีสุข 0893276108 293 ม.4 " + ADDR


def test_typo_sub_matched_inside_district():
    r = FULL.parse(MSG)
    assert r.sub_district == "เขวาสินรินทร์"
    assert r.district == "เขวาสินรินทร์"
    assert r.status == "Needs confirmation"


def test_typo_sub_without_surname_still_matched():
    assert FULL.parse("คุณเอ 0893276108 293 " + ADDR).sub_district == "เขวาสินรินทร์"


def test_exact_sub_still_ready_and_unchanged():
    r = FULL.parse("คุณเอ 0893276108 63 ม.8 ต.ศรีราชา อ.ศรีราชา จ.ชลบุรี 20110")
    assert (r.sub_district, r.district, r.status) == ("ศรีราชา", "ศรีราชา", "Ready")


def test_no_sub_typed_still_not_guessed():
    r = FULL.parse("คุณเอ 0893276108 293 อ.เขวาสินรินทร์ จ.สุรินทร์")
    assert r.status != "Ready"
