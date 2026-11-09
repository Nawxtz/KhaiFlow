"""T-197: a name typed twice after a road (sub + district) keeps the sub; T-192 bare-district rule stays"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

N = "สมชาย แก้วมณี 0682105655 "


def _sub(text):
    r = P.parse(N + text)
    assert r.sub_district == r.district and r.sub_district, (r.sub_district, r.district)


def test_prachuap_doubled():
    _sub("125 หมู่ 11 ซอยวัดใหม่ ปราณบุรี ปราณบุรี ประจวบคีรีขันธ์ 77120")


def test_taling_chan_doubled():
    _sub("777 ม.1 ซ.สุขุมวิท 21 ตลิ่งชัน ตลิ่งชัน กรุงเทพมหานคร 10170")


def test_thawi_watthana_doubled():
    _sub("152 ซ.สุขุมวิท 21 ทวีวัฒนา ทวีวัฒนา กรุงเทพมหานคร 10170")


def test_single_bare_district_after_road_still_blank():
    r = P.parse(N + "12/3 ถ.นครไชยศรี ดุสิต กรุงเทพ 10300")
    assert r.district == "ดุสิต" and r.sub_district is None and r.status == "Needs confirmation"


def test_typed_khwaeng_still_ready():
    r = P.parse(N + "12/3 แขวงดุสิต เขตดุสิต กทม 10300")
    assert (r.sub_district, r.status) == ("ดุสิต", "Ready")
