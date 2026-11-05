"""T-123: a receiver surname equal to the typed sub-district is kept (backlog10 Z-3)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))


def test_surname_equal_sub_is_receiver_part():
    r = P.parse("ชื่อ: นางสาวมาลัย ศรีสุข\nเบอร์: 084 754 9423\nที่อยู่: 218/37 ซอยสุขุมวิท 21 ต.ศรีสุข อ.กันทรวิชัย จ.มหาสารคาม 44150")
    assert r.receiver == "นางสาวมาลัย ศรีสุข"
    assert r.sub_district == "ศรีสุข"


def test_bare_sub_first_still_stripped_unchanged():
    r = P.parse("ในเวียง ใจดี 0812345678 9 อ.เมืองแพร่ จ.แพร่ 54000")
    assert "ในเวียง" not in (r.address_detail or "")


def test_sub_name_not_left_in_detail_still():
    r = P.parse("คุณสมชาย ใจดี 0812345678 9 ม.2 ต.ศรีสุข อ.กันทรวิชัย จ.มหาสารคาม 44150")
    assert "ศรีสุข" not in (r.address_detail or "")
