"""T-077: "ขอบคุณครับพี่" must not leave "พี่" in address_detail."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
BASE = "คุณเอ 0899990009 14 ถ.ศรีนครินทร์ แขวงสวนหลวง เขตสวนหลวง กทม 10250"


def test_thanks_krub_p_dropped_from_detail():
    r = FULL.parse(BASE + " ขอบคุณครับพี่")
    d = r.address_detail or ""
    assert "พี่" not in d
    assert "ขอบคุณ" not in d
    assert r.phone == "0899990009"


def test_house_number_kept_when_thanks_removed():
    r = FULL.parse(BASE + " ขอบคุณครับพี่")
    assert "14" in (r.address_detail or "")
    assert r.status == "Ready"


def test_receiver_prefix_p_still_kept():
    r = FULL.parse("พี่ต้อม 0855556666 5 ม.3 ต.ท่าศาลา อ.เมือง จ.นครศรีธรรมราช 80000")
    assert "ต้อม" in (r.receiver or "")
