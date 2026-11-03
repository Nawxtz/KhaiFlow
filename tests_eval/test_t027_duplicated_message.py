"""T-027: a message pasted twice in one chat bubble parses like the single message."""
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())
MSG = "คุณโอ๋ 10/1 ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 0812345678"


def test_exact_double_paste_same_as_single():
    one = P.parse(MSG)
    for sep in (" ", "\n", "\n\n"):
        two = P.parse(MSG + sep + MSG)
        assert two.address_detail == one.address_detail == "10/1", repr(sep)
        assert two.receiver == one.receiver
        assert two.status == one.status


def test_different_second_address_not_dropped():
    other = MSG.replace("10/1", "10/2")
    assert "10/2" in P.parse(MSG + " " + other).address_detail


def test_repeated_short_phrase_kept():
    r = P.parse("คุณโอ๋ 10/1 ซอย 5 ซอย 5 ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 0812345678")
    assert r.address_detail == "10/1 ซอย 5 ซอย 5"
