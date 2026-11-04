"""T-078: "ถึงแล้วโทรนะ" / "ถึงแล้วโทรเลย" must not leave "ถึงแล้ว" or "นะ" in address_detail."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
BASE = "น้องบอส 0800001112 9 ม.8 ต.บ้านใหม่ อ.ปากเกร็ด จ.นนทบุรี 11120"


def test_arrived_call_na_dropped_from_detail():
    r = FULL.parse(BASE + " ถึงแล้วโทรนะ")
    d = r.address_detail or ""
    assert "ถึงแล้ว" not in d
    assert "นะ" not in d
    assert r.phone == "0800001112"


def test_arrived_call_now_dropped_from_detail():
    r = FULL.parse(BASE + " ถึงแล้วโทรเลย")
    assert "ถึงแล้ว" not in (r.address_detail or "")


def test_house_and_moo_kept_when_note_removed():
    r = FULL.parse(BASE + " ถึงแล้วโทรนะ")
    d = r.address_detail or ""
    assert "9" in d and "หมู่ 8" in d
    assert r.status == "Ready"


def test_real_na_word_in_address_still_kept():
    r = FULL.parse("คุณนะ 0811112222 5 ม.3 ต.ท่าศาลา อ.เมือง จ.นครศรีธรรมราช 80000")
    assert "นะ" in (r.receiver or "")
