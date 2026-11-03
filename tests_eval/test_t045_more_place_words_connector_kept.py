"""T-045: connectors glued after ปั๊ม, โรงเรียน, โรงพยาบาล, มหาวิทยาลัย, สำนักงาน, ร.พ., ร.ร. stay in the name."""
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
TAIL = " ต.หนองปลาไหล อ.บางละมุง จ.ชลบุรี 20150 0812345678"


def _parse(text):
    r = P.parse(text)
    assert r.status == "Ready", text
    assert r.zipcode == "20150", text
    return r


def test_place_name_whole():
    for place in ["ปั๊มส่งสุข", "ปั๊มให้ดี", "โรงเรียนส่งเสริมวิทยา", "โรงเรียนด้วยรัก", "โรงพยาบาลให้ใจ",
                  "โรงพยาบาลเลยวิว", "มหาวิทยาลัยส่งเสริมปัญญา", "สำนักงานให้บริการ", "สำนักงานด้วยใจ",
                  "ร.พ.ส่งเสริมสุข", "ร.ร.ให้ดี"]:
        assert place in (_parse("คุณเอ 9 " + place + TAIL).address_detail or ""), place


def test_particle_after_new_place_word_still_removed():
    assert _parse("คุณเอ 9 ใกล้ปั๊มค่ะ" + TAIL).address_detail == "9 ใกล้ปั๊ม"
    assert _parse("คุณเอ 9 หน้าโรงเรียนนะคะ" + TAIL).address_detail == "9 หน้าโรงเรียน"
    assert _parse("คุณเอ 9 โรงพยาบาลค่ะ" + TAIL).address_detail == "9 โรงพยาบาล"


def test_spaced_connector_still_removed():
    assert _parse("คุณเอ 9 ปั๊ม ส่งสุข" + TAIL).address_detail == "9 ปั๊ม สุข"


def test_dot_not_wildcard_unchanged():
    # "รxพx" is not ร.พ.: the connector after it is still cut
    assert "รอพอส่งสุข" not in (_parse("คุณเอ 9 รอพอส่งสุข" + TAIL).address_detail or "")
