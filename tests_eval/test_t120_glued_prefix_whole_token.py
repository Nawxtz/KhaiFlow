"""T-120: glued-prefix split protections are whole-token (backlog10 Z-1)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
NAME = "คุณสมชาย ใจดี 0812345678 "


def test_sub_ending_in_ob_split():
    r = P.parse("นายอรุณีบุญมา0632160059220/90ม.11ถนนมิตรภาพต.ทาแม่ลอบอ.แม่ทาจ.ลำพูน")
    assert r.address_detail == "220/90 หมู่ 11 ถนนมิตรภาพ"


def test_district_ending_in_ob_province_no_leak():
    r = P.parse("(กาญจนา รักไทย) +66697123837 731 หมู่ 12 ต.น้ำเชี่ยวอ.แหลมงอบจ.ตราด23120")
    assert "ตราด" not in r.address_detail


def test_asm_whole():
    r = P.parse(NAME + "99 ม.3 ใกล้ อสม.บ้านดง ต.บ้านดง อ.อุบลรัตน์ จ.ขอนแก่น 40250")
    assert "อสม.บ้านดง" in r.address_detail


def test_obt_prefix_still_kept():
    r = P.parse(NAME + "9 หน้า อบต.หนองระเวียง ต.บ้านใหม่ อ.เมืองนครราชสีมา จ.นครราชสีมา 30000")
    assert r.sub_district == "บ้านใหม่"
    assert "อบต.หนองระเวียง" in r.address_detail
