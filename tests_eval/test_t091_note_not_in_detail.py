"""T-091: delivery note must not stay in address_detail."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

WITH_NOTE = 'คุณเต้ 0899010234 63 ม.8 ต.ศรีราชา อ.ศรีราชา จ.ชลบุรี 20110 ถึงแล้วโทรหาเลยนะครับ'
PLAIN = 'คุณเต้ 0899010234 63 ม.8 ต.ศรีราชา อ.ศรีราชา จ.ชลบุรี 20110'
LEAKS = ['หา']
HOUSE = '63'


def test_note_dropped_from_detail():
    d = FULL.parse(WITH_NOTE).address_detail or ""
    for leak in LEAKS:
        assert leak not in d


def test_house_number_kept_in_detail():
    d = FULL.parse(WITH_NOTE).address_detail or ""
    assert HOUSE in d


def test_plain_address_unchanged_and_still_clean():
    r = FULL.parse(PLAIN)
    for leak in LEAKS:
        assert leak not in (r.address_detail or "")
    assert HOUSE in (r.address_detail or "")
    assert r.status == FULL.parse(WITH_NOTE).status
