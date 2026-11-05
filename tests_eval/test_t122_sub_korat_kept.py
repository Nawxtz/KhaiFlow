"""T-122: sub-district named โคราช is not rewritten to the province (backlog10 Z-4)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
NAME = "John Smith 0820676506 "


def test_sub_korat_is_sub():
    r = P.parse(NAME + "513/87 ม.8 ถ.พหลโยธิน ต.โคราช อ.สูงเนิน จ.นครราชสีมา")
    assert r.sub_district == "โคราช"


def test_province_alias_still_works():
    r = P.parse(NAME + "5 ต.ในเมือง อ.เมือง จ.โคราช 30000")
    assert r.province == "นครราชสีมา"
