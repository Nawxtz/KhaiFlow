"""T-067: typed sub + district + bare "กรุงเทพมหานคร" win over a zip of another province (Q2, W1)."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))


def test_bare_bangkok_names_win_over_foreign_zip():
    r = FULL.parse("นายอรุณี วงศ์ใหญ่ 090 152 8237 201/75 ซ.5 แขวงคลองถนน เขตสายไหม กรุงเทพมหานคร 27120")
    assert (r.sub_district, r.district, r.province) == ("คลองถนน", "สายไหม", "กรุงเทพมหานคร")
    assert r.status == "Needs confirmation"


def test_matching_zip_still_ready():
    r = FULL.parse("นางสาวปวีณา หอมจันทร์ 0898765432 9 หมู่ 4 ต.ดอนจิก อ.พิบูลมังสาหาร จ.อุบลราชธานี 34110")
    assert (r.sub_district, r.district, r.province) == ("ดอนจิก", "พิบูลมังสาหาร", "อุบลราชธานี")
    assert r.status == "Ready"
