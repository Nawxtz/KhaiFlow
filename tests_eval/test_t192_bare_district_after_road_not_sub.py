"""T-192: a district typed bare after a road name is not read as the sub (backlog19 II-2, delegated II-2q (a))"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

N = "สมชาย 0812345678 "


def _check(text):
    r = P.parse(N + text)
    assert r.district == "ดุสิต" and r.sub_district is None and r.status == "Needs confirmation", (r.district, r.sub_district, r.status)


def test_tho_nakhonchaisri():
    _check("12/3 ถ.นครไชยศรี ดุสิต กรุงเทพ 10300")


def test_thanon_with_soi():
    _check("12/3 ซ.5 ถนนนครไชยศรี ดุสิต กรุงเทพมหานคร 10300")


def test_khet_form_stays():
    _check("12/3 ถ.นครไชยศรี เขตดุสิต กทม 10300")


def test_typed_khwaeng_still_ready():
    r = P.parse(N + "12/3 แขวงดุสิต เขตดุสิต กทม 10300")
    assert (r.sub_district, r.status) == ("ดุสิต", "Ready"), (r.sub_district, r.status)
