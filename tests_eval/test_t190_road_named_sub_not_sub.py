"""T-190: a road typed with ถ./ถนน whose name equals a DB sub named ถนน… is not the sub (backlog18 HH-2, V-1q (a))"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "


def _check(text):
    r = P.parse(N + text)
    assert r.district == "ราชเทวี" and r.sub_district is None and r.status == "Needs confirmation", (r.district, r.sub_district, r.status)


def test_tho_phetchaburi():
    _check("12 ถ.เพชรบุรี เขตราชเทวี กทม 10400")


def test_tho_phayathai():
    _check("12 ถ.พญาไท เขตราชเทวี กทม 10400")


def test_thanon_phetchaburi_with_note():
    _check("12 ถนนเพชรบุรี ตัดใหม่ เขตราชเทวี 10400")


def test_typed_sub_with_prefix_still_ready():
    r = P.parse(N + "12 แขวงถนนเพชรบุรี เขตราชเทวี กทม 10400")
    assert (r.sub_district, r.status) == ("ถนนเพชรบุรี", "Ready")


def test_soi_phetchaburi_unchanged():
    r = P.parse(N + "12 ซ.เพชรบุรี 5 เขตราชเทวี กทม 10400")
    assert (r.sub_district, r.status) == (None, "Needs confirmation")
