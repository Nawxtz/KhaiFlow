"""T-044: connectors glued after more place words stay in the name; polite particles ending the word still go."""
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
TAIL = " ต.หนองปลาไหล อ.บางละมุง จ.ชลบุรี 20150 0812345678"


def _parse(text):
    r = P.parse(text)
    assert r.status == "Ready", text
    assert r.zipcode == "20150", text
    return r


def test_place_name_whole():
    for place in ["ห้างส่งเสริม", "ห้างให้ดี", "ตลาดส่งเสริม", "อพาร์ทเม้นท์ให้รัก", "วัดด้วยใจ", "โรงแรมเลยวิว", "บริษัทส่งดี"]:
        assert place in (_parse("คุณเอ 9 " + place + TAIL).address_detail or ""), place


def test_particle_after_house_removed():
    assert _parse("คุณเอ 9 ที่บ้านค่ะ" + TAIL).address_detail == "9 ที่บ้าน"


def test_particle_after_new_place_word_still_removed():
    assert _parse("คุณเอ 9 ใกล้วัดค่ะ" + TAIL).address_detail == "9 ใกล้วัด"
    assert _parse("คุณเอ 9 หน้าตลาดครับ" + TAIL).address_detail == "9 หน้าตลาด"
    assert _parse("คุณเอ 9 ในห้างนะคะ" + TAIL).address_detail == "9 ในห้าง"


def test_spaced_connector_still_removed():
    assert _parse("คุณเอ 9 ห้าง ส่งเสริม" + TAIL).address_detail == "9 ห้าง เสริม"
