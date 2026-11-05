"""T-173: Latin building text between phone and house number kept (backlog14 DD-3, narrow)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "
G = "ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000"


def test_latin_building_text_moves_to_detail():
    r = P.parse(N + "Condo The Base ห้อง 1203 " + G)
    assert "Condo The Base" in r.address_detail and r.receiver == "คุณสมชาย ใจดี"
    r = P.parse(N + "The Base Condo 99 " + G)
    assert "The Base Condo" in r.address_detail and r.receiver == "คุณสมชาย ใจดี"


def test_surname_after_phone_still_receiver():
    r = P.parse("คุณสมชาย 0812345678 ใจดี 12 ม.4 " + G)
    assert r.receiver == "คุณสมชาย ใจดี" and r.address_detail == "12 หมู่ 4"


def test_phone_first_unchanged():
    r = P.parse("0812345678 คุณสมชาย ใจดี 12 ม.4 " + G)
    assert r.receiver == "คุณสมชาย ใจดี" and r.address_detail == "12 หมู่ 4"


def test_plain_detail_stays():
    r = P.parse(N + "12 ม.4 " + G)
    assert r.receiver == "คุณสมชาย ใจดี" and r.address_detail == "12 หมู่ 4"
