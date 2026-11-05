"""T-176: trailing delivery notes cut or dropped (backlog15 EE-7)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "
G = "ต.ในเมือง อ.เมือง จ.ขอนแก่น 40000"


def _d(note):
    return P.parse(N + "12 ม.4 " + G + " " + note).address_detail


def test_notes_complete():
    assert _d("ไม่รับวันอาทิตย์").endswith("ไม่รับวันอาทิตย์")
    assert _d("ส่งวันจันทร์").endswith("ส่งวันจันทร์")
    assert _d("ไม่อยู่บ้านวางไว้หน้าประตู").endswith("ไม่อยู่บ้านวางไว้หน้าประตู")
    assert _d("ส่งที่ทำงานค่ะ").endswith("ส่งที่ทำงาน")


def test_gift_note_still_kept():
    assert _d("ห่อของขวัญด้วยค่ะ") == "12 หมู่ 4 ห่อของขวัญ"


def test_plain_detail_stays():
    assert _d("") == "12 หมู่ 4"
