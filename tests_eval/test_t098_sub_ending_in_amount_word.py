"""T-098: a sub-district name ending in the word ยอด must not be eaten by the amount strip."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

MSG = "คุณเอ 0814213780 12 ตลาดยอด 10200"
PAY = "คุณเอ 0814213780 12 ต.ศรีราชา อ.ศรีราชา จ.ชลบุรี 20110"


def test_sub_ending_in_amount_word_found_with_typed_zip():
    r = FULL.parse(MSG)
    assert r.sub_district == "ตลาดยอด"
    assert r.zipcode == "10200"


def test_amount_after_space_still_stripped():
    r = FULL.parse(PAY + " ยอด 590 บาท")
    assert r.zipcode == "20110" and "590" not in (r.address_detail or "")


def test_glued_pay_word_amount_still_stripped():
    r = FULL.parse(PAY + " โอนยอด 590")
    assert r.zipcode == "20110" and "590" not in (r.address_detail or "")


def test_money_zip_still_not_a_zip():
    r = FULL.parse("คุณเอ 0814213780 12 ต.ศรีราชา อ.ศรีราชา จ.ชลบุรี ยอด 30000 บาท")
    assert r.zipcode != "30000"


def test_plain_exact_sub_zip_unchanged():
    r = FULL.parse("คุณเอ 0814213780 12 ตลาดใหญ่ 83000")
    assert r.sub_district == "ตลาดใหญ่" and r.status == "Ready"
