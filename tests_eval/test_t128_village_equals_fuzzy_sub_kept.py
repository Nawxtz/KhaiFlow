"""T-128: a village name equal to the typed (fuzzy-corrected) sub-district keeps its name (probe [L274])."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
PRE = "คุณสมชาย ใจดี 0812345678 "


def test_village_name_present_in_detail():
    d = P.parse(PRE + "12 หมู่ 4 บ้านหนองกุ้ง ต.หนองกุ้ง อ.นาเชือก จ.มหาสารคาม 44170").address_detail or ""
    assert d == "12 หมู่ 4 บ้านหนองกุ้ง"


def test_exact_village_name_unchanged():
    d = P.parse(PRE + "12 หมู่ 4 บ้านหนองบัว ต.หนองบัว อ.นาเชือก จ.มหาสารคาม 44170").address_detail or ""
    assert "บ้านหนองบัว" in d


def test_typed_sub_prefix_still_stripped():
    r = P.parse(PRE + "12 หมู่ 4 บ้านหนองกุ้ง ต.หนองกุ้ง อ.นาเชือก จ.มหาสารคาม 44170")
    if r.sub_district == "หนองกุง":  # fuzzy correction ran (needs rapidfuzz)
        assert "ตำบล" not in (r.address_detail or "")
