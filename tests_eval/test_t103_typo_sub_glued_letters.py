"""T-103: sub_prefix_substring: a prefixed sub followed by extra Thai letters is a typo'd sub, not the shorter sub (backlog4 S-2, wrong Ready)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

SUBS = "คุณเอ 0871798416 99 "


def test_typo_sub_takes_whole_token():
    r = P.parse(SUBS + "แขวงทรายกองดินใ้ต เขตคลองสามวา กรุงเทพมหานคร 10510")
    assert r.sub_district == "ทรายกองดินใต้"
    assert "ใ้ต" not in (r.address_detail or "")


def test_second_typo_sub_takes_whole_token():
    r = P.parse(SUBS + "ต.กะลุวอเหนอ อ.เมืองนราธิวาส จ.นราธิวาส 96000")
    assert r.sub_district == "กะลุวอเหนือ"
    assert "เหนอ" not in (r.address_detail or "")


def test_exact_short_sub_still_ready():
    r = P.parse(SUBS + "แขวงทรายกองดิน เขตคลองสามวา กรุงเทพมหานคร 10510")
    assert (r.sub_district, r.status) == ("ทรายกองดิน", "Ready")
    r = P.parse(SUBS + "ต.กะลุวอ อ.เมืองนราธิวาส จ.นราธิวาส 96000")
    assert (r.sub_district, r.status) == ("กะลุวอ", "Ready")


def test_exact_sub_glued_to_next_prefix_unchanged():
    r = P.parse(SUBS + "ต.กะลุวออ.เมืองนราธิวาสจ.นราธิวาส 96000")
    assert r.sub_district == "กะลุวอ"
