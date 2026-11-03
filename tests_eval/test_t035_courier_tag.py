"""T-035: a requested courier becomes a Courier_* tag and leaves address_detail; a post office landmark stays."""
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
HEAD = "คุณมะลิ 5/7 ม.3 "
TAIL = " ต.หนองปลาไหล อ.บางละมุง จ.ชลบุรี 20150 0812345678"


def parse_end(note):
    return P.parse(HEAD + TAIL.strip() + " " + note)


def test_courier_tagged_and_dropped():
    cases = {
        "ส่งKerryนะคะ": "Courier_Kerry", "ส่งเคอรี่": "Courier_Kerry",
        "ขอส่ง Flash นะคะ": "Courier_Flash", "ส่งแฟลช": "Courier_Flash",
        "ส่ง J&T": "Courier_JT",
        "ส่งEMSค่ะ": "Courier_EMS", "ส่ง ems": "Courier_EMS",
        "ส่งไปรษณีย์ธรรมดาค่ะ": "Courier_ThaiPost", "ส่งทางไปรษณีย์ไทย": "Courier_ThaiPost",
    }
    for note, tag in cases.items():
        r = parse_end(note)
        assert tag in r.tags, note
        assert r.address_detail == "5/7 หมู่ 3", note


def test_post_office_landmark_kept_untagged():
    r = P.parse(HEAD + "ตรงข้ามไปรษณีย์" + TAIL)
    assert r.address_detail == "5/7 หมู่ 3 ตรงข้ามไปรษณีย์"
    assert not any(t.startswith("Courier_") for t in r.tags)


def test_other_tags_still_work():
    r = parse_end("ส่งKerry ห้ามพับ เก็บเงินปลายทาง")
    assert sorted(r.tags) == ["COD", "Courier_Kerry", "Do_not_fold"]
    assert r.address_detail == "5/7 หมู่ 3"
