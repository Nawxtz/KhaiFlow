"""T-182: ส.ต.ต./ส.ต.ท. expand and ranks keep the surname (backlog16 FF-3)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "
G = " ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000"


def test_sub_lt_trainee():
    r = P.parse("ส.ต.ต.สมชาย ใจดี 0812345678 12 ม.4" + G)
    assert r.receiver == "สิบตำรวจตรีสมชาย ใจดี" and r.address_detail == "12 หมู่ 4"


def test_sub_lt_female_surname_present():
    r = P.parse("ส.ต.ต.หญิง สมหญิง ใจดี 0812345678 12 ม.4" + G)
    assert r.receiver == "สิบตำรวจตรีหญิง สมหญิง ใจดี" and r.address_detail == "12 หมู่ 4"


def test_chief_sub_lt_female_surname_present():
    r = P.parse("จ.ส.ต.หญิง สมหญิง ใจดี 0812345678 12 ม.4" + G)
    assert r.receiver == "จ่าสิบตำรวจหญิง สมหญิง ใจดี" and r.address_detail == "12 หมู่ 4"


def test_other_ranks_unchanged():
    r = P.parse("ร.ต.อ.หญิง สมหญิง ใจดี 0812345678 12 ม.4" + G)
    assert r.receiver == "ร้อยตำรวจเอกหญิง สมหญิง ใจดี" and r.address_detail == "12 หมู่ 4"
    r = P.parse(N + "12 ม.4" + G)
    assert r.receiver == "คุณสมชาย ใจดี" and r.address_detail == "12 หมู่ 4"
