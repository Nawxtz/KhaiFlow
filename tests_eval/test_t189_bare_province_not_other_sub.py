"""T-189: a bare province name (no จ., no district, no zip) is never read as a sub of another province (backlog18 HH-1)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "


def _check(text, prov):
    r = P.parse(N + text)
    assert r.province == prov and r.sub_district is None and r.status == "Needs confirmation", (r.province, r.sub_district, r.status)


def test_khonkaen_bare():
    _check("12/3 ขอนแก่น", "ขอนแก่น")


def test_lamphun_bare():
    _check("12/3 ลำพูน", "ลำพูน")


def test_chiangmai_bare():
    _check("12/3 เชียงใหม่", "เชียงใหม่")


def test_typed_sub_named_like_province_still_ready():
    r = P.parse(N + "12 ม.4 ต.เชียงใหม่ อ.โพธิ์ชัย จ.ร้อยเอ็ด")
    assert (r.province, r.district, r.sub_district, r.status) == ("ร้อยเอ็ด", "โพธิ์ชัย", "เชียงใหม่", "Ready")


def test_bare_province_with_zip_unchanged():
    r = P.parse(N + "12/3 เชียงใหม่ 50290")
    assert (r.province, r.district, r.zipcode) == ("เชียงใหม่", "สันทราย", "50290")
