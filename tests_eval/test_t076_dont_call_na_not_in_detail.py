"""T-076: "ไม่ต้องโทรนะ" must not leave "หมู่ นะ" in address_detail."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
BASE = "น้องฟ้า 0822220002 12 ซ.ลาดพร้าว 71 แขวงลาดพร้าว เขตลาดพร้าว กทม. 10230"


def test_dont_call_na_dropped_from_detail():
    r = FULL.parse(BASE + " ไม่ต้องโทรนะ")
    d = r.address_detail or ""
    assert "นะ" not in d
    assert "หมู่" not in d
    assert r.phone == "0822220002"


def test_soi_number_kept_when_note_removed():
    r = FULL.parse(BASE + " ไม่ต้องโทรนะ")
    assert "71" in (r.address_detail or "")
    assert r.status == "Ready"


def test_note_without_suffix_unchanged():
    r = FULL.parse(BASE + " ไม่ต้องโทร")
    assert "71" in (r.address_detail or "")
    assert "นะ" not in (r.address_detail or "")


def test_real_na_word_in_address_still_kept():
    r = FULL.parse("คุณนะ 0811112222 5 ม.3 ต.ท่าศาลา อ.เมือง จ.นครศรีธรรมราช 80000")
    assert "นะ" in (r.receiver or "")
