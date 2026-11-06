"""T-178: teacher prefix 'อ.' on the receiver read as district (backlog15 EE-3)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "
G = "ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000"


def test_teacher_prefix_is_receiver():
    r = P.parse("อ.สมชาย ใจดี 0812345678 12 ม.4 " + G)
    assert r.receiver == "อ.สมชาย ใจดี"
    assert (r.province, r.district, r.sub_district) == ("ขอนแก่น", "เมืองขอนแก่น", "ในเมือง")


def test_district_prefix_still_district():
    r = P.parse(N + "12 ม.4 ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000")
    assert r.district == "เมืองขอนแก่น" and r.receiver == "คุณสมชาย ใจดี"


def test_district_first_message_unchanged():
    r = P.parse("อ.เมืองขอนแก่น " + N + "12 ม.4 ต.ในเมือง จ.ขอนแก่น 40000")
    assert r.district == "เมืองขอนแก่น"
