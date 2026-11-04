"""T-082: delivery note must not stay in address_detail."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

WITH_NOTE = 'คุณสุ 0833450218 7 ถ.มิตรภาพ ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000 ไม่ต้องกดกริ่งนะคะ'
PLAIN = 'คุณสุ 0833450218 7 ถ.มิตรภาพ ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000'
LEAK = 'กดกริ่ง'
HOUSE = '7'


def test_note_dropped_from_detail():
    d = FULL.parse(WITH_NOTE).address_detail or ""
    assert LEAK not in d


def test_house_number_kept_in_detail():
    d = FULL.parse(WITH_NOTE).address_detail or ""
    assert HOUSE in d


def test_plain_address_unchanged_and_still_clean():
    r = FULL.parse(PLAIN)
    assert LEAK not in (r.address_detail or "")
    assert HOUSE in (r.address_detail or "")
    assert r.status == FULL.parse(WITH_NOTE).status
