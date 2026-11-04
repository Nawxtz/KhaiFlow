"""T-081: "ฝากไว้กับรปภ." must not leave "ฝากไว้กับ" in address_detail."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

BASE = "คุณปอ 0855550005 7 ถ.นิมมานเหมินทร์ ต.สุเทพ อ.เมือง จ.เชียงใหม่ 50200"


def test_guard_prefix_dropped():
    r = FULL.parse(BASE + " ฝากไว้กับรปภ.นะครับ")
    assert "ฝากไว้กับ" not in (r.address_detail or "")
    assert "Drop_at_guard" in (r.tags or [])


def test_street_kept():
    d = FULL.parse(BASE + " ฝากไว้กับรปภ.นะครับ").address_detail or ""
    assert "นิมมานเหมินทร์" in d


def test_plain_guard_note_still_tagged_unchanged():
    r = FULL.parse(BASE + " ฝากป้อมยามได้เลยครับ")
    assert "Drop_at_guard" in (r.tags or [])
