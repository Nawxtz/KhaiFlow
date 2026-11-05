"""T-116: อบต./รพ.สต. landmark is not split by the glued-prefix rule (backlog9 Y-1)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
NAME = "คุณสมชาย ใจดี 0812345678 "


def test_aobotor_landmark_typed_sub_wins():
    r = P.parse(NAME + "99 ม.4 หน้า อบต.หนองระเวียง ต.บ้านใหม่ อ.เมืองนครราชสีมา จ.นครราชสีมา 30000")
    assert r.sub_district == "บ้านใหม่"
    assert "อบต.หนองระเวียง" in r.address_detail


def test_rpsor_landmark_in_detail():
    r = P.parse(NAME + "99 ม.4 ใกล้ รพ.สต.บ้านใหม่ ต.หนองระเวียง อ.เมืองนครราชสีมา จ.นครราชสีมา 30000")
    assert "รพ.สต.บ้านใหม่" in r.address_detail


def test_glued_district_prefix_still_split():
    r = P.parse(NAME + "12 บางโฉลงอ.บางพลีจ.สมุทรปราการ 10540")
    assert r.sub_district == "บางโฉลง" and r.district == "บางพลี"


def test_glued_moo_still_split():
    r = P.parse(NAME + "12 บ้านสวนม.3 ต.สุเทพ อ.เมือง จ.เชียงใหม่ 50200")
    assert "หมู่ 3" in r.address_detail
