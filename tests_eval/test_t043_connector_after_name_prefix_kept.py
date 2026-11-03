"""T-043: connectors glued after คุณ or a place word stay in the name; ขอบคุณค่ะ and spaced particles still go."""
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
TAIL = " ต.หนองปลาไหล อ.บางละมุง จ.ชลบุรี 20150 0812345678"


def _parse(text):
    r = P.parse(text)
    assert r.status == "Ready", text
    assert r.zipcode == "20150", text
    return r


def test_name_after_khun_whole():
    for name in ["คุณส่งศรี", "คุณคะนึง", "คุณจ้าว"]:
        assert _parse(name + " 5/7 ม.3" + TAIL).receiver == name, name


def test_place_name_whole():
    for place in ["ร้านส่งสุข", "บ้านให้เช่า", "หอพักด้วยรัก", "คอนโดให้รัก", "ตึกส่งสุข", "แฟลตเลยวารี", "โครงการด้วยใจ"]:
        assert place in (_parse("คุณเอ 9 " + place + TAIL).address_detail or ""), place


def test_khob_khun_and_spaced_particles_still_removed():
    assert _parse("คุณมะลิ 5/7 ม.3" + TAIL + " ขอบคุณค่ะ").address_detail == "5/7 หมู่ 3"
    for note in ["ค้า", "นะค้า", "ส่งด้วยนะคะ", "ด้วยค่ะ", "ให้ด้วย", "เลยครับ"]:
        assert _parse("คุณมะลิ 5/7 ม.3" + TAIL + " " + note).address_detail == "5/7 หมู่ 3", note
