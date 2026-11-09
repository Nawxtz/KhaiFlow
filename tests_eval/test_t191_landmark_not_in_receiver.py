"""T-191: a landmark phrase (ตรงข้าม/ใกล้/ข้าง) typed after the phone is not part of the receiver (backlog19 II-1)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

N = "0812345678 "
ADDR = " 12/3 ต.ช้างคลาน อ.เมือง จ.เชียงใหม่ 50100"


def _recv(name, lm):
    return P.parse(name + " " + N + lm + ADDR)


def test_trongkham():
    r = _recv("สมชาย", "ตรงข้ามเซเว่น")
    assert r.receiver == "สมชาย" and "ตรงข้ามเซเว่น" in (r.address_detail or ""), (r.receiver, r.address_detail)


def test_klai():
    r = _recv("สมชาย", "ใกล้ตลาด")
    assert r.receiver == "สมชาย", r.receiver


def test_khang():
    r = _recv("สมชาย", "ข้างวัดป่า")
    assert r.receiver == "สมชาย", r.receiver


def test_surname_receiver_still_kept():
    r = P.parse("สมชาย ใจดี " + N.strip() + ADDR)
    assert r.receiver == "สมชาย ใจดี" and r.status == "Ready", (r.receiver, r.status)
