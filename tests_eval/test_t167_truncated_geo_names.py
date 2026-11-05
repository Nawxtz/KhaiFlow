"""T-167: truncated district/province prefix dropped (backlog13 CC-8)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))
N = "คุณสมชาย ใจดี 0812345678 "


def _d(tail):
    return P.parse(N + tail).address_detail


def test_prefixes_dropped():
    assert _d("12 ม.4 ต.ตลาด เมืองสุราษ จ.สุราษฎร์ธานี 84000") == "12 หมู่ 4"
    assert _d("55 แขวงคลองเตย เขตคลองเตย กรุงเทพมหานค 10110") == "55"


def test_real_detail_words_kept():
    assert _d("12 ม.4 ซ.เมืองใหม่ ต.ตลาด อ.เมือง จ.สุราษฎร์ธานี 84000") == "12 หมู่ 4 ซอยเมืองใหม่"
