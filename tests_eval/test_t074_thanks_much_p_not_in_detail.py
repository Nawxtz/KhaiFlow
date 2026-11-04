"""T-074: "ขอบคุณมากค่ะพี่" must not leave "ขอบคุณมาก พี่" in address_detail."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
BASE = "คุณจุ๊บ 0800001112 ซ.อ่อนนุช 17 แขวงสวนหลวง เขตสวนหลวง กรุงเทพมหานคร 10250"


def test_thanks_much_with_p_dropped_from_detail():
    r = FULL.parse(BASE + " ขอบคุณมากค่ะพี่")
    assert "ขอบคุณ" not in (r.address_detail or "")
    assert "พี่" not in (r.address_detail or "")
    assert r.phone == "0800001112"


def test_soi_number_kept_when_thanks_removed():
    r = FULL.parse(BASE + " ขอบคุณมากค่ะพี่")
    assert "17" in (r.address_detail or "")
    assert r.status == "Ready"


def test_receiver_prefix_p_still_kept():
    r = FULL.parse("พี่ต้อม 0855556666 5 ม.3 ต.ท่าศาลา อ.เมือง จ.นครศรีธรรมราช 80000")
    assert "ต้อม" in (r.receiver or "")
