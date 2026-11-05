"""T-142: bug: marks-only receiver and punctuation-only address_detail (quality Q-9)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
BASE = "คุณสมชาย ใจดี 99/9 ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 0812345678"


def test_marks_only_receiver_none():
    assert P.parse("ััั่").receiver is None


def test_punct_only_detail_none():
    assert P.parse(":::::::").address_detail is None


def test_base_unchanged():
    r = P.parse(BASE)
    assert r.receiver == "คุณสมชาย ใจดี" and "99/9" in r.address_detail
