"""T-084: delivery note must not stay in address_detail."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

WITH_NOTE = 'ป้าหน่อย 0855670220 21 ม.2 ต.ท่าช้าง อ.เมือง จ.จันทบุรี 22000 วางไว้หน้าบ้านได้เลยจ้ะ'
PLAIN = 'ป้าหน่อย 0855670220 21 ม.2 ต.ท่าช้าง อ.เมือง จ.จันทบุรี 22000'
LEAK = 'วางไว้หน้าบ้าน'
HOUSE = '21'


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
