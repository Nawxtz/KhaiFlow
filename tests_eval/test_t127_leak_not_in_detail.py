"""T-127: "กทม" must not stay in address_detail (probe [L273])."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

WITH_NOTE = 'คุณสมชาย ใจดี 0812345678 12/3 แขวงคลองเตยเขตคลองเตยกทม.10110'
PLAIN = ''
LEAK = 'กทม'
KEEP = '12/3'


def test_leak_dropped_from_detail():
    assert LEAK not in (P.parse(WITH_NOTE).address_detail or "")


def test_keep_still_in_detail():
    assert KEEP in (P.parse(WITH_NOTE).address_detail or "")


def test_glued_krungthep_phi_dropped():
    pre = "คุณสมชาย ใจดี 0812345678 "
    assert (P.parse(pre + "12/3 แขวงคลองเตยเขตคลองเตยกรุงเทพฯ10110").address_detail or "") == "12/3"


def test_plain_bangkok_unchanged():
    pre = "คุณสมชาย ใจดี 0812345678 "
    assert (P.parse(pre + "12/3 แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร 10110").address_detail or "") == "12/3"
