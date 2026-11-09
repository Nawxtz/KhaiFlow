"""T-196: a name after a 👤 emoji that follows the address and phone is the receiver (backlog19 II-6)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

ADDR = "🏠 12/3 ต.แม่ริม อ.แม่ริม จ.เชียงใหม่ 50180 "


def test_name_after_emoji_last():
    r = P.parse(ADDR + "📞 0812345678 👤 สมชาย")
    assert r.receiver == "สมชาย" and "สมชาย" not in (r.address_detail or ""), (r.receiver, r.address_detail)


def test_name_after_emoji_first_stays():
    r = P.parse("👤 สมชาย " + ADDR + "📞 0812345678")
    assert r.receiver == "สมชาย", r.receiver


def test_no_name_still_none():
    r = P.parse(ADDR + "📞 0812345678")
    assert r.receiver is None, r.receiver
