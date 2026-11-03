"""T-047: a leading quantity ("2 ชิ้น") is not a house number; receiver found after it, quantity stays in detail."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))


def test_order_layout_receiver_after_quantity():
    r = FULL.parse("ออเดอร์ #A6865 2 ชิ้น ยอด 190 บาท\nอรุณี บุญมา\n0864054405\n788 ถ.พหลโยธิน แขวงลำผักชี เขตหนองจอก กทม 10530")
    assert r.receiver == "อรุณี บุญมา"
    assert r.address_detail == "2 ชิ้น 788 ถนนพหลโยธิน"
    assert r.status == "Ready"


def test_other_unit_receiver_after_quantity():
    r = FULL.parse("3 ตัว สมศรี ใจงาม 0812345678 55/1 ถ.มิตรภาพ ต.ในเมือง อ.เมืองขอนแก่น จ.ขอนแก่น 40000")
    assert r.receiver == "สมศรี ใจงาม"
    assert r.address_detail == "3 ตัว 55/1 ถนนมิตรภาพ"


def test_quantity_after_honorific_still_in_detail():
    r = FULL.parse("คุณมานี มีนา 0812345678 2 ชิ้น 99 ม.3 ต.ท่ายาง อ.ท่ายาง จ.เพชรบุรี 76130")
    assert r.receiver == "คุณมานี มีนา"
    assert r.address_detail == "2 ชิ้น 99 หมู่ 3"


def test_house_number_at_start_unchanged():
    r = FULL.parse("12 ม.3 ต.ท่ายาง อ.ท่ายาง จ.เพชรบุรี 76130 สมชาย ดีใจ 0812345678")
    assert r.receiver == "สมชาย ดีใจ"
    assert r.address_detail == "12 หมู่ 3"
