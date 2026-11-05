"""T-141: bug: paste-twice dedupe misses 3+ copies, Ready with the other copies in detail (quality Q-7)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
BASE = "คุณสมชาย ใจดี 99/9 ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 0812345678"


def test_three_spaced_copies_deduped():
    r = P.parse(" ".join([BASE] * 3))
    assert r.address_detail == P.parse(BASE).address_detail


def test_five_spaced_copies_deduped():
    r = P.parse(" ".join([BASE] * 5))
    assert r.receiver == "คุณสมชาย ใจดี"
    assert r.address_detail == P.parse(BASE).address_detail


def test_base_and_twice_unchanged():
    a = P.parse(BASE)
    b = P.parse(BASE + " " + BASE)
    assert a.address_detail == b.address_detail and a.status == b.status == "Ready"
