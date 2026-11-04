"""T-100: "ถึงแล้วบอก" must not stay in address_detail (probe [L226])."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

WITH_NOTE = 'คุณปุ๊ก 0811230226 15 ม.4 ต.หนองป่าครั่ง อ.เมือง จ.เชียงใหม่ 50000 โทรมาก่อนนะคะ ถึงแล้วบอกด้วย'
PLAIN = 'คุณปุ๊ก 0811230226 15 ม.4 ต.หนองป่าครั่ง อ.เมือง จ.เชียงใหม่ 50000'
LEAK = 'ถึงแล้วบอก'
KEEP = '15'


def test_leak_dropped_from_detail():
    assert LEAK not in (P.parse(WITH_NOTE).address_detail or "")


def test_keep_still_in_detail():
    assert KEEP in (P.parse(WITH_NOTE).address_detail or "")


def test_plain_address_unchanged():
    r = P.parse(PLAIN)
    assert KEEP in (r.address_detail or "")
    assert r.status == P.parse(WITH_NOTE).status
