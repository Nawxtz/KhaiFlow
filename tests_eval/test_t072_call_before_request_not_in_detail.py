"""T-072: "รบกวนโทรก่อนนะคะ" (call before delivery) must not leave "ก่อน" in address_detail."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
BASE = "ส่งให้ คุณอนันต์ ใจกล้า 0823456789 บ้านเลขที่ 7 ม.4 ต.สุเทพ อ.เมืองเชียงใหม่ จ.เชียงใหม่ 50200"


def test_call_before_request_dropped_from_detail():
    for tail in ("รบกวนโทรก่อนนะคะ", "โทรก่อนส่งนะครับ", "โทรก่อน"):
        r = FULL.parse(BASE + " " + tail)
        assert "ก่อน" not in (r.address_detail or ""), tail
        assert r.phone == "0823456789", tail


def test_house_number_kept_when_request_removed():
    r = FULL.parse(BASE + " รบกวนโทรก่อนนะคะ")
    assert "7" in (r.address_detail or "")
    assert r.status == "Ready"


def test_phone_label_still_stripped_unchanged():
    r = FULL.parse("คุณมานี โทร 0878901234 3/3 ต.ในเมือง อ.เมือง จ.นครราชสีมา 30000")
    assert r.phone == "0878901234"
    assert r.receiver == "คุณมานี"
