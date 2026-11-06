"""T-180: Thai building/landmark text between phone and house number kept in address_detail (backlog15 EE-6, narrow)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "
G = " ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000"


def _ok(r):
    assert r.receiver == "คุณสมชาย ใจดี"
    assert (r.province, r.district, r.sub_district) == ("ขอนแก่น", "เมืองขอนแก่น", "ในเมือง")


def test_house_name_in_detail():
    r = P.parse(N + "บ้านสีฟ้า 12 ม.4" + G)
    _ok(r)
    assert r.address_detail == "บ้านสีฟ้า 12 หมู่ 4"


def test_temple_in_detail():
    r = P.parse(N + "วัดป่า 12 ม.4" + G)
    _ok(r)
    assert r.address_detail == "วัดป่า 12 หมู่ 4"


def test_hospital_in_detail():
    r = P.parse(N + "โรงพยาบาลขอนแก่น ตึก 2" + G)
    _ok(r)
    assert "โรงพยาบาล" in r.address_detail and "ตึก 2" in r.address_detail


def test_company_in_detail():
    r = P.parse(N + "บริษัท เอบีซี จำกัด 99" + G)
    _ok(r)
    assert r.address_detail == "บริษัท เอบีซี จำกัด 99"


def test_plain_detail_unchanged():
    r = P.parse(N + "12 ม.4" + G)
    _ok(r)
    assert r.address_detail == "12 หมู่ 4"


def test_surname_after_phone_still_receiver():
    r = P.parse("คุณสมชาย 0812345678 ใจดี 12 ม.4" + G)
    assert r.receiver == "คุณสมชาย ใจดี" and r.address_detail == "12 หมู่ 4"


def test_name_first_phone_last_unchanged():
    r = P.parse("0812345678 คุณสมชาย ใจดี 12 ม.4" + G)
    assert r.receiver == "คุณสมชาย ใจดี" and r.address_detail == "12 หมู่ 4"
