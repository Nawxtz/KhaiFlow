"""T-101: "ขอบคุณมาก" must not stay in address_detail (probe [L232])."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

WITH_NOTE = 'น้องมุก 0877890232 44 ม.2 ต.เวียง อ.เมือง จ.เชียงราย 57000 ขอบคุณมากเลยค่ะ'
PLAIN = 'น้องมุก 0877890232 44 ม.2 ต.เวียง อ.เมือง จ.เชียงราย 57000'
LEAK = 'ขอบคุณมาก'
KEEP = '44'


def test_leak_dropped_from_detail():
    assert LEAK not in (P.parse(WITH_NOTE).address_detail or "")


def test_keep_still_in_detail():
    assert KEEP in (P.parse(WITH_NOTE).address_detail or "")


def test_plain_address_unchanged():
    r = P.parse(PLAIN)
    assert KEEP in (r.address_detail or "")
    assert r.status == P.parse(WITH_NOTE).status
