"""T-130: "ไวๆ" must not stay in address_detail (probe [L280])."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

WITH_NOTE = 'คุณสมชาย ใจดี 0812345678 12 ม.4 ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000 ส่งไวๆ'
PLAIN = 'คุณสมชาย ใจดี 0812345678 12 ม.4 ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000'
LEAK = 'ไวๆ'
KEEP = '12'


def test_leak_dropped_from_detail():
    assert LEAK not in (P.parse(WITH_NOTE).address_detail or "")


def test_keep_still_in_detail():
    assert KEEP in (P.parse(WITH_NOTE).address_detail or "")


def test_plain_address_unchanged():
    r = P.parse(PLAIN)
    assert KEEP in (r.address_detail or "")
    assert r.status == P.parse(WITH_NOTE).status


def test_urgent_tag_set():
    assert "Urgent" in P.parse(WITH_NOTE).tags


def test_word_with_wai_in_address_kept():
    text = "คุณสมชาย ใจดี 0812345678 12 ซ.ไวไว 2 ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000"
    assert "ไวไว" in (P.parse(text).address_detail or "")
    assert "Urgent" not in P.parse(text).tags
