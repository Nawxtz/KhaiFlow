"""T-071: the phone label "โทร." leaves no stray "." on the receiver."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
TAIL = "ห้อง 305 อาคาร B คอนโดริมน้ำ ซ.เจริญนคร 14 แขวงบางลำภูล่าง เขตคลองสาน กทม. 10600"


def test_dotted_phone_label_leaves_clean_receiver():
    r = FULL.parse("ธนพร ใจเย็น โทร.0866667777 " + TAIL)
    assert r.receiver == "ธนพร ใจเย็น"
    assert r.phone == "0866667777"


def test_undotted_phone_label_still_clean():
    r = FULL.parse("ธนพร ใจเย็น โทร 0866667777 " + TAIL)
    assert r.receiver == "ธนพร ใจเย็น"


def test_abbreviation_dot_in_address_kept_unchanged():
    r = FULL.parse("ธนพร ใจเย็น โทร.0866667777 " + TAIL)
    assert "กทม" not in (r.receiver or "")
    assert "305" in (r.address_detail or "")
