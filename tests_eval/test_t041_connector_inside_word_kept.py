"""T-041: connector particles are not cut out of words (ลูกค้า, ซอยส่งเสริม); standalone particles still go."""
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
TAIL = " ต.หนองปลาไหล อ.บางละมุง จ.ชลบุรี 20150 0812345678"


def _detail(text):
    r = P.parse(text)
    assert r.status == "Ready", text
    assert r.zipcode == "20150", text
    return r.address_detail or ""


def test_connector_inside_word_whole():
    assert "ลูกค้าประจำ" in _detail("คุณมะลิ 5/7 ม.3" + TAIL + " ⭐️ลูกค้าประจำ⭐️")
    assert "ลูกค้าประจำ" in _detail("คุณมะลิ 5/7 ม.3" + TAIL + " ลูกค้าประจำ")
    assert "ส่งเสริม" in _detail("คุณเอ 99 ซ.ส่งเสริม" + TAIL)
    assert "หมู่บ้านด้วยรัก" in _detail("คุณเอ 12 หมู่บ้านด้วยรัก" + TAIL)
    assert "เลยวารี" in _detail("คุณเอ 45 ถ.เลยวารี" + TAIL)
    assert "พ่อค้าข้าวแกง" in _detail("คุณเอ 7 ร้านพ่อค้าข้าวแกง" + TAIL)
    assert "แม่ค้า" in _detail("คุณเอ 3 ตลาดแม่ค้า" + TAIL)
    assert "อาคารให้เช่า" in _detail("คุณเอ 8 อาคารให้เช่า ห้อง 5" + TAIL)


def test_standalone_particles_still_removed():
    for note in ["ค้า", "นะค้า", "ส่งด้วยนะคะ", "ด้วยค่ะ", "ให้ด้วย", "เลยครับ"]:
        assert _detail("คุณมะลิ 5/7 ม.3" + TAIL + " " + note) == "5/7 หมู่ 3", note
