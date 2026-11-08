"""T-188: typed sub = typed district name, but that name is a real sub of ANOTHER district: keep typed district, sub blank, Needs confirmation (backlog17 GG-1 part 2b)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 12 ม.4 "


def _check(text, dist):
    r = P.parse(N + text)
    assert r.district == dist and r.sub_district is None and r.status == "Needs confirmation", (r.district, r.sub_district, r.status)


def test_yannawa_typed_as_district():
    _check("ต.ยานนาวา อ.ยานนาวา จ.กรุงเทพมหานคร 10120", "ยานนาวา")


def test_yannawa_khet_form():
    _check("แขวงยานนาวา เขตยานนาวา กรุงเทพมหานคร 10120", "ยานนาวา")


def test_bangkhunthian_typed_as_district():
    _check("ต.บางขุนเทียน อ.บางขุนเทียน จ.กรุงเทพมหานคร 10150", "บางขุนเทียน")


def test_sub_with_its_real_district_still_ready():
    r = P.parse(N + "ต.ยานนาวา เขตสาทร กรุงเทพมหานคร 10120")
    assert r.status == "Ready" and r.sub_district == "ยานนาวา" and r.district == "สาทร"
    r = P.parse(N + "ต.กระนวน อ.ซำสูง จ.ขอนแก่น 40170")
    assert r.status == "Ready" and r.sub_district == "กระนวน" and r.district == "ซำสูง"


def test_valid_same_name_triples_unchanged():
    r = P.parse(N + "ต.หางดง อ.หางดง จ.เชียงใหม่ 50230")
    assert r.status == "Ready" and r.sub_district == "หางดง" and r.district == "หางดง"
    r = P.parse(N + "ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000")
    assert r.status == "Ready" and r.sub_district == "ในเมือง"


def test_t186_shape_unchanged():
    r = P.parse(N + "ต.กระนวน อ.กระนวน จ.ขอนแก่น 40170")
    assert r.district == "กระนวน" and r.sub_district is None and r.status == "Needs confirmation"
