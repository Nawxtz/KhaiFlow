"""T-080: neighbour-drop note must not stay in address_detail."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

BASE = "พี่ติ๊ก 0888880008 15 ม.4 ต.ในเมือง อ.เมือง จ.นครราชสีมา 30000"


def test_neighbor_note_dropped():
    r = FULL.parse(BASE + " ไม่อยู่บ้านฝากเพื่อนบ้านได้")
    assert "เพื่อนบ้าน" not in (r.address_detail or "")
    assert r.phone == "0888880008"


test_neighbor_dropped = test_neighbor_note_dropped


def test_house_and_moo_kept():
    d = FULL.parse(BASE + " ไม่อยู่บ้านฝากเพื่อนบ้านได้").address_detail or ""
    assert "15" in d and "หมู่ 4" in d


def test_guard_note_still_tagged_unchanged():
    r = FULL.parse(BASE + " ฝากป้อมยามได้เลยครับ")
    assert "Drop_at_guard" in (r.tags or [])
