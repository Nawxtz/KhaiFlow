"""T-117: prefix of two subs is not fuzzy-guessed (backlog9 Y-2)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
NAME = "คุณสมชาย ใจดี 0812345678 "


def test_ambiguous_prefix_sub_blank():
    r = P.parse(NAME + "8 ม.5 ต.สันทราย อ.สันทราย จ.เชียงใหม่ 50210")
    assert r.sub_district in (None, "")
    assert r.status == "Needs confirmation"


def test_ambiguous_prefix_bangna_blank():
    r = P.parse(NAME + "10 ถ.สุขุมวิท แขวงบางนา เขตบางนา กรุงเทพมหานคร 10260")
    assert r.sub_district in (None, "")
    assert r.status == "Needs confirmation"


def test_unique_prefix_still_resolved():
    r = P.parse(NAME + "10 ม.2 ต.บางพลี อ.บางพลี จ.สมุทรปราการ 10540")
    assert r.sub_district == "บางพลีใหญ่"
    assert r.status == "Ready"


def test_exact_full_sub_stays():
    r = P.parse(NAME + "10 ถ.สุขุมวิท แขวงบางนาเหนือ เขตบางนา กทม. 10260")
    assert r.sub_district == "บางนาเหนือ"
    assert r.status == "Ready"
