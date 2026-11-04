"""T-070: a thanks word with a polite particle ("ขอบคุณค่า") is not address detail."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
BASE = "รบกวนส่งที่ คุณวิภา รักดี โทร 0845556666 เลขที่ 5 ต.ช้างคลาน อ.เมืองเชียงใหม่ จ.เชียงใหม่ 50100"


def test_thanks_with_particle_dropped_from_detail():
    for tail in ("ขอบคุณค่า", "ขอบคุณค่ะ", "ขอบคุณครับ"):
        r = FULL.parse(BASE + " " + tail)
        assert "ขอบคุณ" not in (r.address_detail or ""), tail
        assert r.status == "Ready"


def test_house_number_kept_when_thanks_removed():
    r = FULL.parse(BASE + " ขอบคุณค่า")
    assert "5" in (r.address_detail or "")


def test_plain_address_unchanged_without_thanks():
    r = FULL.parse(BASE)
    assert (r.sub_district, r.district, r.province) == ("ช้างคลาน", "เมืองเชียงใหม่", "เชียงใหม่")
    assert "5" in (r.address_detail or "")
