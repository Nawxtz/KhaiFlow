"""T-106: "ขอบคุณมาก" must not stay in address_detail (probe [L208])."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

WITH_NOTE = 'คุณโอ๋ 0833330003 66 ถ.พหลโยธิน แขวงจตุจักร เขตจตุจักร กทม 10900 ขอบคุณมากครับผม'
PLAIN = 'คุณโอ๋ 0833330003 66 ถ.พหลโยธิน แขวงจตุจักร เขตจตุจักร กทม 10900'
LEAK = 'ขอบคุณมาก'
KEEP = '66'


def test_leak_dropped_from_detail():
    assert LEAK not in (P.parse(WITH_NOTE).address_detail or "")


def test_keep_still_in_detail():
    assert KEEP in (P.parse(WITH_NOTE).address_detail or "")


def test_plain_address_unchanged():
    r = P.parse(PLAIN)
    assert KEEP in (r.address_detail or "")
    assert r.status == P.parse(WITH_NOTE).status
