"""T-111: glued honorific receiver equal to a sub-district must not become the sub (backlog5 U-2)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))


def test_glued_honorific_name_is_no_sub():
    for t in ("น.ส.ในเวียง ใจดี 0812345678 868/83 ม.14 อ.เมืองแพร่ จ.แพร่ 54000",
              "0812345678 868/83 ม.14 อ.เมืองแพร่ จ.แพร่ 54000 ผู้รับ น.ส.ในเวียง ใจดี"):
        r = P.parse(t)
        assert r.sub_district != "ในเวียง"
        assert r.status == "Needs confirmation"


def test_typed_sub_with_other_name_still_ready():
    r = P.parse("น.ส.สมใจ ใจดี 0812345678 868/83 ม.14 ต.ในเวียง อ.เมืองแพร่ จ.แพร่ 54000")
    assert (r.sub_district, r.status) == ("ในเวียง", "Ready")


def test_spaced_honorific_unchanged():
    r = P.parse("น.ส. ในเวียง ใจดี 0812345678 868/83 ม.14 อ.เมืองแพร่ จ.แพร่ 54000")
    assert r.sub_district != "ในเวียง"
