"""T-097: the phone-word strip must not cut "โทร" out of a sub-district name."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

MSG = "399 หมู่ 13 ต.บางโทรัด 74000 นางวิภาวดี รักไทย 0652883750"


def test_phone_word_inside_sub_name_survives():
    r = FULL.parse(MSG)
    assert r.sub_district == "บางโทรัด"
    assert "ัด" not in (r.address_detail or "").replace("บางโทรัด", "")


def test_phone_label_still_gives_phone():
    assert FULL.parse("คุณเอ โทร 0812345678 12 ต.ศรีราชา อ.ศรีราชา จ.ชลบุรี 20110").phone == "0812345678"


def test_phone_label_dot_still_gives_phone():
    assert FULL.parse("คุณเอ โทร.0812345678 12 ต.ศรีราชา อ.ศรีราชา จ.ชลบุรี 20110").phone == "0812345678"


def test_glued_phone_word_still_stripped():
    assert FULL.parse("คุณเอ โทร0812345678 12 ต.ศรีราชา อ.ศรีราชา จ.ชลบุรี 20110").phone == "0812345678"
