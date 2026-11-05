"""T-139: bug: mock geo DB reported as 26 records, it has more (quality Q-11)"""
import os
import re

SRC = open(os.path.join(os.getcwd(), "api.py"), encoding="utf-8").read()


def test_no_hardcoded_26():
    assert "mock:26-records" not in SRC and "26-record MOCK" not in SRC


def test_geo_source_derived():
    assert re.search(r'mock:\{[^}]+\}-records', SRC)


def test_real_csv_source_still_present():
    assert "geo_source" in SRC and "csv:" in SRC
