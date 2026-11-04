"""T-105: sub_guessed_when_absent: a receiver name inside "()" must not be reused as the sub-district (backlog4 S-1, wrong Ready)"""
import os

from geo_engine import GeoDatabase
from parser import SmartAddressParser

P = SmartAddressParser(GeoDatabase().load_csv(os.path.join(os.getcwd(), "data/thai_address_full.csv")))

TAIL = " 0857456999 868/83 ม.14 {}อ.เมืองแพร่ จ.แพร่ 54000"


def test_bracketed_receiver_is_no_sub():
    r = P.parse("(นายกาญจนา พงษ์พันธ์)" + TAIL.format(""))
    assert r.sub_district is None
    assert r.status == "Needs confirmation"


def test_bracketed_spaced_honorific_is_no_sub():
    r = P.parse("(น.ส. ในเวียง ใจดี)" + TAIL.format(""))
    assert r.sub_district is None
    assert r.status == "Needs confirmation"


def test_unbracketed_receiver_unchanged():
    r = P.parse("นายกาญจนา พงษ์พันธ์" + TAIL.format(""))
    assert (r.sub_district, r.status) == (None, "Needs confirmation")


def test_typed_sub_with_bracketed_receiver_still_ready():
    r = P.parse("(น.ส. ในเวียง ใจดี)" + TAIL.format("ต.ในเวียง "))
    assert (r.sub_district, r.status) == ("ในเวียง", "Ready")
