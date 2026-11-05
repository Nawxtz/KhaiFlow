"""T-125: "ชร" must not stay in address_detail (probe [L267])."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

WITH_NOTE = 'คุณสมชาย ใจดี 0812345678 1 ม.2 ต.เวียง อ.เมือง จ.ชร. 57000'
PLAIN = ''
LEAK = 'ชร'
KEEP = '1'


def test_leak_dropped_from_detail():
    assert LEAK not in (P.parse(WITH_NOTE).address_detail or "")


def test_keep_still_in_detail():
    assert KEEP in (P.parse(WITH_NOTE).address_detail or "")


def test_other_probe_lines_fixed():
    pre = "คุณสมชาย ใจดี 0812345678 "
    d = P.parse(pre + "12 ม.4 ต.ประตูชัย อ.อยุธยา จ.อยุธยา 13000").address_detail or ""
    assert d == "12 หมู่ 4"
    assert "จังหวัด" not in (P.parse(pre + "12 ม.4 ต.ในเมือง อ.เมือง จ.อุบลฯ 34000").address_detail or "")


def test_code_contradicting_zip_still_kept():
    d = P.parse("คุณสมชาย ใจดี 0812345678 12 ม.4 ต.ช้างเผือก อ.เมือง จ.ชร 50300").address_detail or ""
    assert "จังหวัดชร" in d
