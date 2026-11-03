"""T-034: a dorm, flat or apartment name right after the receiver stays in address_detail."""
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
TAIL = " ต.หนองปลาไหล อ.บางละมุง จ.ชลบุรี 20150 0812345678"


def test_building_name_kept():
    for b in ("หอพักสุขใจ", "แฟลตสุขใจ", "อพาร์ตเมนต์สุขใจ", "อพาร์ทเม้นท์สุขใจ"):
        r = P.parse(f"คุณมะลิ {b} ห้อง 204" + TAIL)
        assert r.receiver == "คุณมะลิ", b
        assert r.address_detail == f"{b} ห้อง 204", b


def test_leading_noise_still_dropped_and_names_unchanged():
    r = P.parse("แอดมิน คุณมะลิ หอพักสุขใจ ห้อง 204" + TAIL)
    assert r.address_detail == "หอพักสุขใจ ห้อง 204"
    r = P.parse("คุณหอมหวล 5/7 หมู่ 3" + TAIL)
    assert r.receiver == "คุณหอมหวล" and r.address_detail == "5/7 หมู่ 3"
