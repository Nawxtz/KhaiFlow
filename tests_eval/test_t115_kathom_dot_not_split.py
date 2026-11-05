"""T-115: "กทม." (with dot) is not split by the glued-prefix rule (backlog8 X-1)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
NAME = "คุณสมชาย ใจดี 0812345678 "


def test_kathom_dot_no_stray_moo():
    r = P.parse(NAME + "45 ถ.ศรีนครินทร์ แขวงหนองบอน เขตประเวศ กทม. 10250 อยู่หน้าบ้าน")
    assert "หมู่" not in r.address_detail
    assert "อยู่หน้าบ้าน" in r.address_detail
    r = P.parse(NAME + "45 ถ.ศรีนครินทร์ แขวงหนองบอน เขตประเวศ กทม.10250 ห่อของขวัญด้วยค่ะ")
    assert "หมู่" not in r.address_detail


def test_glued_moo_still_split():
    r = P.parse(NAME + "12 บ้านสวนม.3 ต.สุเทพ อ.เมือง จ.เชียงใหม่ 50200")
    assert "หมู่ 3" in r.address_detail


def test_glued_district_prefix_still_split():
    r = P.parse(NAME + "12 บางโฉลงอ.บางพลีจ.สมุทรปราการ 10540")
    assert r.sub_district == "บางโฉลง" and r.district == "บางพลี"
