"""T-193: commas typed around the phone leave no punctuation in the receiver (backlog19 II-4)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

ADDR = " 12/3 ต.ช้างคลาน อ.เมือง จ.เชียงใหม่ 50100"


def test_plain_name_commas():
    assert P.parse("สมชาย, 0812345678," + ADDR).receiver == "สมชาย"


def test_honorific_dashed_phone():
    assert P.parse("คุณสมชาย, 081-234-5678," + ADDR).receiver == "คุณสมชาย"


def test_surname_commas():
    assert P.parse("สมชาย ใจดี, 0812345678," + ADDR).receiver == "สมชาย ใจดี"


def test_no_comma_unchanged():
    r = P.parse("สมชาย ใจดี 0812345678" + ADDR)
    assert r.receiver == "สมชาย ใจดี" and r.status == "Ready", (r.receiver, r.status)
