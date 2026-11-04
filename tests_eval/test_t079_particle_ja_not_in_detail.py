"""T-079: "นะจ๊ะ" must not leave "จ๊ะ" in address_detail."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

BASE = "น้องเนย 0800000011 23 ม.6 ต.ท่าศาลา อ.เมือง จ.ลพบุรี 15000"


def test_ja_dropped():
    r = FULL.parse(BASE + " ส่งด่วนที่สุดเลยนะจ๊ะ")
    assert "จ๊ะ" not in (r.address_detail or "")
    assert r.phone == "0800000011"


def test_house_and_moo_kept():
    d = FULL.parse(BASE + " ส่งด่วนที่สุดเลยนะจ๊ะ").address_detail or ""
    assert "23" in d and "หมู่ 6" in d


def test_other_particle_still_dropped_unchanged():
    assert "จ้า" not in (FULL.parse(BASE + " ส่งเลยจ้า").address_detail or "")
