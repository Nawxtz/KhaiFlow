"""T-073: "โทรหาก่อนถึงนะ" (call before arriving) must not leave "หาก่อนถึงนะ" in address_detail."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
BASE = "0844445555 คุณแก้ว 9/9 ม.1 ต.บ้านใหม่ อ.ปากเกร็ด จ.นนทบุรี 11120"


def test_call_before_arriving_dropped_from_detail():
    for tail in ("โทรหาก่อนถึงนะ", "โทรหาก่อน", "โทรหาก่อนถึง"):
        r = FULL.parse(BASE + " " + tail)
        assert "ก่อน" not in (r.address_detail or ""), tail
        assert "หา" not in (r.address_detail or ""), tail
        assert r.phone == "0844445555", tail


def test_house_number_kept_when_request_removed():
    r = FULL.parse(BASE + " โทรหาก่อนถึงนะ")
    assert "9/9" in (r.address_detail or "")
    assert r.status == "Ready"


def test_earlier_call_before_form_unchanged():
    r = FULL.parse("ส่งให้ คุณอนันต์ ใจกล้า 0823456789 บ้านเลขที่ 7 ม.4 ต.สุเทพ อ.เมืองเชียงใหม่ จ.เชียงใหม่ 50200 รบกวนโทรก่อนนะคะ")
    assert "ก่อน" not in (r.address_detail or "")
    assert r.phone == "0823456789"
