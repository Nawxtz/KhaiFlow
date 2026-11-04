"""T-075: a request word right after the receiver name must not become part of the receiver."""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

FULL = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))


def test_request_words_dropped_from_receiver():
    cases = [
        "คุณปิยะ 0811112222 ส่งก่อน 5 โมงเย็นนะคะ 8/1 ซ.ลาดพร้าว 71 แขวงลาดพร้าว เขตลาดพร้าว กรุงเทพมหานคร 10230",
        "คุณเอก 0833334444 ขอเบิกใบกำกับภาษี 120 ถ.สุขุมวิท แขวงคลองเตย เขตคลองเตย กรุงเทพ 10110",
        "พี่ต้อม 0855556666 ที่อยู่เดิม 5 ม.3 ต.ท่าศาลา อ.เมือง จ.นครศรีธรรมราช 80000 เปลี่ยนเป็น 7 ม.3 ต.ท่าศาลา",
    ]
    for t in cases:
        recv = FULL.parse(t).receiver or ""
        for w in ("ก่อน", "เดิม", "ขอเบิก"):
            assert w not in recv, (t, recv)


def test_receiver_name_still_kept():
    r = FULL.parse("คุณเอก 0833334444 ขอเบิกใบกำกับภาษี 120 ถ.สุขุมวิท แขวงคลองเตย เขตคลองเตย กรุงเทพ 10110")
    assert (r.receiver or "").startswith("คุณเอก")


def test_normal_surname_unchanged():
    r = FULL.parse("คุณอนันต์ ใจกล้า 0823456789 บ้านเลขที่ 7 ม.4 ต.สุเทพ อ.เมืองเชียงใหม่ จ.เชียงใหม่ 50200")
    assert r.receiver == "คุณอนันต์ ใจกล้า"
