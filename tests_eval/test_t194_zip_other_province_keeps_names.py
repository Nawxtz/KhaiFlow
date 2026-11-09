"""T-194: a zip of another province does not erase a typed district+province that exist together in the DB (backlog19 II-3, Q2)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

N = "สมชาย 0812345678 "


def test_maerim_with_bangkok_zip():
    r = P.parse(N + "12/3 ต.แม่ริม อ.แม่ริม จ.เชียงใหม่ 10110")
    assert (r.province, r.district, r.status) == ("เชียงใหม่", "แม่ริม", "Needs confirmation"), (r.province, r.district, r.status)
    assert r.zipcode == "10110", r.zipcode


def test_maerim_own_zip_unchanged():
    r = P.parse(N + "12/3 ต.แม่ริม อ.แม่ริม จ.เชียงใหม่ 50180")
    assert (r.province, r.district, r.zipcode) == ("เชียงใหม่", "แม่ริม", "50180"), (r.province, r.district, r.zipcode)


def test_real_sub_still_ready():
    r = P.parse(N + "12/3 ต.ช้างคลาน อ.เมือง จ.เชียงใหม่ 50100")
    assert (r.province, r.sub_district, r.status) == ("เชียงใหม่", "ช้างคลาน", "Ready"), (r.province, r.sub_district, r.status)
