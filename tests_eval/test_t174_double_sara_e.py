"""T-174: doubled sara e 'เเ' not normalised (backlog15 EE-1)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "
G = "ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000"


def test_double_e_province_without_zip():
    r = P.parse(N + "12 ม.4 ต.ในเมือง อ.เมือง จ.ขอนเเก่น")
    assert (r.province, r.district, r.sub_district) == ("ขอนแก่น", "เมืองขอนแก่น", "ในเมือง")


def test_double_e_detail_clean_with_zip():
    r = P.parse(N + "12 ม.4 ต.ในเมือง อ.เมือง จ.ขอนเเก่น 40000")
    assert r.address_detail == "12 หมู่ 4" and r.province == "ขอนแก่น"


def test_normal_address_unchanged():
    r = P.parse(N + "12 ม.4 " + G)
    assert r.address_detail == "12 หมู่ 4" and r.province == "ขอนแก่น" and r.receiver == "คุณสมชาย ใจดี"


def test_double_e_in_receiver_fixed():
    r = P.parse("คุณเเดง ใจดี 0812345678 12 ม.4 " + G)
    assert r.receiver == "คุณแดง ใจดี"
