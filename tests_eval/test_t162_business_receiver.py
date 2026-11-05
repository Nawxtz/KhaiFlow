"""T-162: ร้าน/บริษัท names are read whole as the receiver (backlog13 CC-3, U-6 (a))"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
ADDR = "12 ม.4 ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000"


def test_shop_receiver():
    r = P.parse("ร้านป้าแดง 0812345678 " + ADDR)
    assert r.receiver == "ร้านป้าแดง" and r.status == "Ready"
    assert "หมู่ 4" in r.address_detail and "ร้าน" not in r.address_detail


def test_company_receiver_whole():
    r = P.parse("บริษัท เอบีซี จำกัด 0812345678 " + ADDR)
    assert r.receiver == "บริษัท เอบีซี จำกัด"


def test_shop_word_in_address_stays_in_detail():
    r = P.parse("คุณสมชาย ใจดี 0812345678 12 ร้านกาแฟ ม.4 ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000")
    assert "สมชาย ใจดี" in r.receiver
    assert "ร้านกาแฟ" in r.address_detail


def test_person_receiver_unchanged():
    r = P.parse("คุณสมชาย ใจดี 0812345678 " + ADDR)
    assert r.status == "Ready" and "สมชาย" in r.receiver
