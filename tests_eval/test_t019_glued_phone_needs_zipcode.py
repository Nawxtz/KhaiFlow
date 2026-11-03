"""T-019: a phone is read out of a longer digit run only when the 5 digits before it are a known zipcode."""
from parser import SmartAddressParser, build_mock_geo_db

P = SmartAddressParser(build_mock_geo_db())


def test_order_number_is_not_a_phone():
    # 12345 is not a zipcode in the geo database, so 123450812345678 is one number, not zip + phone
    r = P.parse("ออเดอร์ 123450812345678 คุณแม็ค 99/9 ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี 20130 0898765432")
    assert (r.phone, r.zipcode) == ("0898765432", "20130")


def test_order_number_glued_input():
    r = P.parse("ออเดอร์123450812345678คุณแม็ค99/9ต.แสนสุขอ.เมืองชลบุรีจ.ชลบุรี201300898765432")
    assert (r.phone, r.zipcode) == ("0898765432", "20130")


def test_known_zipcode_glued_still_splits():
    r = P.parse("คุณแม็ค99/9ต.แสนสุขอ.เมืองชลบุรีจ.ชลบุรี201300812345678")
    assert (r.phone, r.zipcode) == ("0812345678", "20130")
