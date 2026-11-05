"""T-137: bug: ParseResult.from_dict turns str tags into characters and crashes on int (quality Q-6)"""
import os
import sys

sys.path.insert(0, os.getcwd())
from models import ParseResult


def test_str_tags_one_item():
    assert ParseResult.from_dict({"tags": "COD"}).tags == ["COD"]


def test_int_tags_empty():
    assert ParseResult.from_dict({"tags": 5}).tags == []


def test_dict_warnings_empty():
    assert ParseResult.from_dict({"warnings": {"a": 1}}).warnings == []


def test_list_tags_unchanged():
    r = ParseResult.from_dict({"tags": ["COD"], "receiver": "คุณเอ"})
    assert r.tags == ["COD"] and r.receiver == "คุณเอ"
