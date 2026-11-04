"""T-104: receiver_other: a connector word inside a typo'd sub-district must not expose a glued honorific as the receiver (backlog4 S-3)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

BASE = " 0871798416 222 ซ.5 แขวง{} เขตวังทองหลาง กรุงเทพมหานคร 10310"


def test_receiver_survives_typo_sub():
    r = P.parse("รัชนี สุขสวัสดิ์" + BASE.format("คลออเจ้าคุณสิงห์"))
    assert r.receiver == "รัชนี สุขสวัสดิ์"


def test_exact_sub_receiver_unchanged():
    assert P.parse("รัชนี สุขสวัสดิ์" + BASE.format("คลองเจ้าคุณสิงห์")).receiver == "รัชนี สุขสวัสดิ์"


def test_honorific_receiver_still_found():
    assert P.parse("ส่งที่ คุณมะลิ" + BASE.format("คลองเจ้าคุณสิงห์")).receiver == "คุณมะลิ"


def test_trailing_particle_still_stripped():
    r = P.parse("คุณมะลิ 0871798416 222 ซ.5 แขวงคลองเจ้าคุณสิงห์ เขตวังทองหลาง กรุงเทพมหานคร 10310 จ้า")
    assert "จ้า" not in (r.address_detail or "")
