"""T-110: address keyword "หมู่" must not be fuzzy-matched as the sub-district (backlog5 U-1)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))


def test_moo_word_is_no_sub():
    for t in ("คุณสมชาย ใจดี 0812345678 849 หมู่ 15 อ.เมืองอุดรธานี จ.อุดรธานี 41000",
              "นายณัฐวุฒิ ทองคำ 0663784573 891/31 ม.11 อ.โนนสูง จ.นครราชสีมา 30160"):
        r = P.parse(t)
        assert r.sub_district is None
        assert r.status == "Needs confirmation"


def test_typed_sub_still_ready():
    r = P.parse("นายณัฐวุฒิ ทองคำ 0663784573 891/31 ม.11 ต.ใหม่ อ.โนนสูง จ.นครราชสีมา 30160")
    assert (r.sub_district, r.status) == ("ใหม่", "Ready")


def test_typed_sub_moomon_still_ready():
    r = P.parse("คุณสมชาย ใจดี 0812345678 849 ต.หมูม่น อ.เมืองอุดรธานี จ.อุดรธานี 41000")
    assert (r.sub_district, r.status) == ("หมูม่น", "Ready")
