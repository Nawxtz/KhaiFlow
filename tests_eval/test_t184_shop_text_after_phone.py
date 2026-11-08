"""T-184: shop/landmark text after the phone stays in address_detail (backlog16 FF-4, rest of T-170)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "
G = " ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000"


def test_shop_before_house_number():
    r = P.parse(N + "ร้านป้าแดง 12 ม.4" + G)
    assert r.receiver == "คุณสมชาย ใจดี" and r.address_detail == "ร้านป้าแดง 12 หมู่ 4"


def test_one_word_receiver_shop_in_detail():
    r = P.parse("คุณสมชาย 0812345678 ร้านป้าแดง 12 ม.4" + G)
    assert r.receiver == "คุณสมชาย" and r.address_detail.startswith("ร้านป้าแดง")


def test_ship_to_shop_in_detail():
    r = P.parse(N + "ส่งที่ร้าน ป้าแดงขายข้าว 12 ม.4" + G)
    assert "ร้าน" in r.address_detail and r.receiver == "คุณสมชาย ใจดี"


def test_market_shop_number_in_detail():
    r = P.parse(N + "ตลาดสด ร้านที่ 5" + G)
    assert "ตลาดสด ร้านที่ 5" in r.address_detail


def test_business_receiver_still_whole():
    assert P.parse("ร้านป้าแดง 0812345678 12 ม.4" + G).receiver == "ร้านป้าแดง"
    assert P.parse("บริษัท เอบีซี จำกัด 0812345678 12 ม.4" + G).receiver == "บริษัท เอบีซี จำกัด"


def test_plain_and_landmark_unchanged():
    r = P.parse(N + "12 ม.4" + G)
    assert r.receiver == "คุณสมชาย ใจดี" and r.address_detail == "12 หมู่ 4"
    r = P.parse(N + "หอพักสุขใจ 12 ม.4" + G)
    assert r.receiver == "คุณสมชาย ใจดี" and "หอพักสุขใจ" in r.address_detail
