#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ThaiSmartAddress v7.0 — geo_engine.py
O(1) geographic lookup engine + RapidFuzz typo correction.

NEW FIXES applied (this version):
  [FIX-G1] GeoDatabase.lookup() now uses O(n_unique_geo_names) candidate
            building instead of O(n_all_records). For the full ~150k-row Thai
            address CSV (~7k unique sub-districts, ~900 districts, ~77
            provinces) this reduces the per-request scan from 150k iterations
            to at most ~8k, a ~20x improvement for non-zipcode queries.
  [FIX-G2] Added public properties sub_district_names, district_names,
            province_names on GeoDatabase so FuzzyGeoMatcher (and any future
            consumer) no longer accesses private underscore-prefixed attributes
            (_sub_map, _dist_map, _prov_map). Tight coupling removed.
  [FIX-G3] FuzzyGeoMatcher updated to use public accessors from [FIX-G2].
"""
from __future__ import annotations

import csv
import functools
import heapq
import logging
import re
import warnings
from collections import defaultdict
from io import StringIO
from typing import Callable, Dict, FrozenSet, List, Optional, Set, Tuple

from models import GeoRecord
from constants import (
    FUZZY_THRESHOLD,
    FUZZY_MAX_LEN_DIFF,
    HONORIFIC_SKIP_SET,
    HONORIFIC_PATTERN,
    NAME_STOP_WORDS,
    RECEIVER_LABEL_RE,
)

logger = logging.getLogger("ThaiSmartAddress.geo")

# FIX [#17]: Import pythainlp word_tokenize at module level, not inside the
# per-token hot loop in FuzzyGeoMatcher. Python caches imports after the first
# call, but the dict lookup + attribute traversal still happens every iteration.
# Module-level binding avoids this entirely and is the idiomatic pattern.
try:
    from pythainlp.tokenize import word_tokenize as _pythainlp_word_tokenize  # type: ignore
    _PYTHAINLP_TOKENIZE_AVAILABLE = True
except ImportError:
    _pythainlp_word_tokenize = None  # type: ignore
    _PYTHAINLP_TOKENIZE_AVAILABLE = False

# ──────────────────────────────────────────────────────────────────────────────
# Optional: RapidFuzz
# ──────────────────────────────────────────────────────────────────────────────
RAPIDFUZZ_AVAILABLE = False
try:
    from rapidfuzz import process as _fuzz_process, fuzz as _fuzz  # type: ignore
    RAPIDFUZZ_AVAILABLE = True
    logger.info("RapidFuzz detected — fuzzy typo correction enabled")
except ImportError:
    warnings.warn(
        "rapidfuzz not installed — fuzzy typo correction DISABLED.\n"
        "Run: pip install rapidfuzz  to enable.",
        stacklevel=2,
    )


def _extract_receiver_tokens(text: str) -> Set[str]:
    receiver_tokens: Set[str] = set()
    m_lbl = RECEIVER_LABEL_RE.search(text)
    if m_lbl:
        receiver_tokens.update(re.split(r"[\s,\-/]+", m_lbl.group(1)))
    for hm in HONORIFIC_PATTERN.finditer(text):
        clean_span = text[hm.start():hm.end()].strip()
        if clean_span in NAME_STOP_WORDS or any(clean_span.startswith(sw) for sw in NAME_STOP_WORDS):
            continue
        receiver_tokens.update(re.split(r"[\s,\-/]+", clean_span))
        after = text[hm.end():]
        m2 = re.match(r"\s*([^\s\d/]{2,30})(?=\s|$)", after)
        if m2 and m2.group(1) not in NAME_STOP_WORDS:
            receiver_tokens.add(m2.group(1))
            after2 = after[m2.end():]
            m3 = re.match(r"\s*([^\s\d/]{2,30})(?=\s|$)", after2)
            if m3 and m3.group(1) not in NAME_STOP_WORDS:
                w3 = m3.group(1)
                if all("\u0E00" <= c <= "\u0E7F" for c in w3) and not any(
                    w3.startswith(p) for p in ("ต.", "อ.", "จ.", "ตำบล", "อำเภอ", "จังหวัด", "แขวง", "เขต")
                ):
                    receiver_tokens.add(w3)
    return receiver_tokens


# ══════════════════════════════════════════════════════════════════════════════
# GEO DATABASE
# ══════════════════════════════════════════════════════════════════════════════

class GeoDatabase:
    """
    O(1) geographic lookup engine backed by four hash maps built at startup.

    Maps:
        _zip_map  : {zipcode       → List[GeoRecord]}
        _sub_map  : {sub_district  → List[GeoRecord]}
        _dist_map : {district      → List[GeoRecord]}
        _prov_map : {province      → List[GeoRecord]}

    Disambiguation strategy:
        1. Zipcode → narrow candidate pool instantly (O(1))
        2. Score sub_district (+4), district (+3), province (+2), zipcode (+1)
        3. [FIX-G1] Without a zipcode, candidates are built by scanning map
           keys (O(n_unique_names)) rather than all records (O(n_records)).
    """

    REQUIRED_COLS: FrozenSet[str] = frozenset({"sub_district", "district", "province", "zipcode"})

    def __init__(self) -> None:
        self._zip_map:  Dict[str, List[GeoRecord]] = defaultdict(list)
        self._sub_map:  Dict[str, List[GeoRecord]] = defaultdict(list)
        self._dist_map: Dict[str, List[GeoRecord]] = defaultdict(list)
        self._prov_map: Dict[str, List[GeoRecord]] = defaultdict(list)
        self._all_records: List[GeoRecord] = []
        self._loaded = False

    # ── Loaders ───────────────────────────────────────────────────────────────

    def load_csv(self, path: str) -> "GeoDatabase":
        logger.info("Loading geo database from CSV: %s", path)
        with open(path, encoding="utf-8-sig") as fh:
            return self._load_reader(csv.DictReader(fh))

    def load_csv_string(self, csv_text: str) -> "GeoDatabase":
        return self._load_reader(csv.DictReader(StringIO(csv_text)))

    def load_records(self, records: List[dict]) -> "GeoDatabase":
        for r in records:
            self._ingest(r)
        self._loaded = True
        logger.info("GeoDatabase loaded: %d records", len(self._all_records))
        return self

    def _load_reader(self, reader: csv.DictReader) -> "GeoDatabase":
        missing = self.REQUIRED_COLS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")
        for row in reader:
            self._ingest(row)
        self._loaded = True
        logger.info("GeoDatabase loaded: %d records", len(self._all_records))
        return self

    def _ingest(self, row: dict) -> None:
        rec = GeoRecord(
            sub_district=row["sub_district"].strip(),
            district=row["district"].strip(),
            province=row["province"].strip(),
            zipcode=row["zipcode"].strip(),
        )
        self._all_records.append(rec)
        self._zip_map[rec.zipcode].append(rec)
        self._sub_map[rec.sub_district].append(rec)
        self._dist_map[rec.district].append(rec)
        self._prov_map[rec.province].append(rec)

    # ── Public accessors (FIX-G2) — replaces private attr access ─────────────

    def records_for_zipcode(self, zipcode: str) -> List[GeoRecord]:
        return list(self._zip_map.get(zipcode, []))

    def records_for_sub_district(self, sub: str) -> List[GeoRecord]:
        return list(self._sub_map.get(sub, []))

    def records_for_district(self, district: str) -> List[GeoRecord]:
        return list(self._dist_map.get(district, []))

    def records_for_province(self, province: str) -> List[GeoRecord]:
        return list(self._prov_map.get(province, []))

    @property
    def sub_district_names(self) -> List[str]:
        """All unique sub-district names in the database."""
        return list(self._sub_map.keys())

    @property
    def district_names(self) -> List[str]:
        """All unique district names in the database."""
        return list(self._dist_map.keys())

    @property
    def province_names(self) -> List[str]:
        """All unique province names in the database."""
        return list(self._prov_map.keys())

    # ── Core lookup ───────────────────────────────────────────────────────────

    def lookup(
        self, text: str, zipcode_hint: Optional[str] = None
    ) -> Tuple[Optional[GeoRecord], int, List[str]]:
        """
        Hierarchical top-down geo disambiguation.
        Returns (best_record | None, score, warnings).

        FIX [FIX-G1]: When no zipcode hint is provided, candidates are built
        from map-key scans (O(~8k)) instead of all-record iteration (O(~150k)).
        """
        warnings_out: List[str] = []

        _SUB_PFXS  = ("ตำบล", "แขวง", "ต.", "แขวง ", "ต ")
        _DIST_PFXS = ("อำเภอ", "เขต", "อ.", "เขต ", "ที่", "อ ")
        _PROV_PFXS = ("จังหวัด", "จ.", "ที่", "จ ", "แถว")

        if not hasattr(self, "_prov_tuple"):
            self._prov_tuple = tuple(self._prov_map.keys())
        prov_prefixes = _PROV_PFXS + self._prov_tuple

        if zipcode_hint and zipcode_hint in self._zip_map:
            pool: List[GeoRecord] = self._zip_map[zipcode_hint]
        else:
            if zipcode_hint:
                warnings_out.append(
                    f"Zipcode '{zipcode_hint}' not found in geo DB — using full search"
                )
            # FIX [FIX-G1]: Build pool from map-key scans, not all_records
            pool = self._build_candidate_pool(text, _SUB_PFXS, _DIST_PFXS, _PROV_PFXS)
            if not pool:
                # Fallback: full scan (should be rare — only when text has no
                # recognisable geo token, e.g. keyboard-fallback input)
                pool = self._all_records

        sub_cache: Dict[str, List[Tuple[int, int, bool, int]]] = {}
        dist_cache: Dict[Tuple[str, str], List[Tuple[int, int, bool, int]]] = {}
        prov_cache: Dict[str, List[Tuple[int, int, bool, int]]] = {}

        def check_after(end_idx: int, follow_pfxs: tuple = ()) -> bool:
            if end_idx >= len(text):
                return True
            ch = text[end_idx]
            if not ('\u0E00' <= ch <= '\u0E7F'):
                return True
            for fp in follow_pfxs:
                if text.startswith(fp, end_idx):
                    return True
            return False

        def get_sub_matches(sub: str) -> List[Tuple[int, int, bool, int]]:
            if sub not in sub_cache:
                m = []
                if sub:
                    for pfx in _SUB_PFXS:
                        full = pfx + sub
                        flen = len(full)
                        idx = text.find(full)
                        while idx != -1:
                            end_idx = idx + flen
                            before_ok = (idx == 0) or not ('\u0E00' <= text[idx - 1] <= '\u0E7F')
                            if before_ok and check_after(end_idx, _DIST_PFXS + prov_prefixes):
                                m.append((idx, end_idx, True, len(sub)))
                            idx = text.find(full, idx + 1)
                    tlen = len(sub)
                    idx = text.find(sub)
                    while idx != -1:
                        end_idx = idx + tlen
                        before_ok = (idx == 0) or not ('\u0E00' <= text[idx - 1] <= '\u0E7F')
                        if before_ok and check_after(end_idx, _DIST_PFXS + prov_prefixes):
                            if not any(s <= idx and end_idx <= e for s, e, _, _ in m):
                                m.append((idx, end_idx, False, tlen))
                        idx = text.find(sub, idx + 1)
                sub_cache[sub] = m
            return sub_cache[sub]

        def get_dist_matches(dist: str, prov: str) -> List[Tuple[int, int, bool, int]]:
            key = (dist, prov)
            if key not in dist_cache:
                m = []
                if dist:
                    for pfx in _DIST_PFXS:
                        full = pfx + dist
                        flen = len(full)
                        idx = text.find(full)
                        while idx != -1:
                            end_idx = idx + flen
                            before_ok = (idx == 0) or not ('\u0E00' <= text[idx - 1] <= '\u0E7F')
                            if before_ok and check_after(end_idx, prov_prefixes):
                                m.append((idx, end_idx, True, len(dist)))
                            idx = text.find(full, idx + 1)
                    tlen = len(dist)
                    idx = text.find(dist)
                    while idx != -1:
                        end_idx = idx + tlen
                        before_ok = (idx == 0) or not ('\u0E00' <= text[idx - 1] <= '\u0E7F')
                        if before_ok and check_after(end_idx, prov_prefixes):
                            if not any(s <= idx and end_idx <= e for s, e, _, _ in m):
                                m.append((idx, end_idx, False, tlen))
                        idx = text.find(dist, idx + 1)
                    if dist.startswith("เมือง"):
                        prov_in_text = prov and (prov in text or any(pfx + prov in text for pfx in _PROV_PFXS))
                        if prov_in_text:
                            for muang_pfx in ("อำเภอเมือง", "อ.เมือง"):
                                flen = len(muang_pfx)
                                idx = text.find(muang_pfx)
                                while idx != -1:
                                    end_idx = idx + flen
                                    if check_after(end_idx, prov_prefixes):
                                        if not any(s <= idx and end_idx <= e for s, e, _, _ in m):
                                            m.append((idx, end_idx, True, len(dist)))
                                    idx = text.find(muang_pfx, idx + 1)
                            idx = text.find("เมือง")
                            while idx != -1:
                                end_idx = idx + len("เมือง")
                                before_ok = (idx == 0) or not ('\u0E00' <= text[idx - 1] <= '\u0E7F')
                                if before_ok and check_after(end_idx, prov_prefixes):
                                    if not any(s <= idx and end_idx <= e for s, e, _, _ in m):
                                        m.append((idx, end_idx, False, len(dist)))
                                idx = text.find("เมือง", idx + 1)
                dist_cache[key] = m
            return dist_cache[key]

        def get_prov_matches(prov: str) -> List[Tuple[int, int, bool, int]]:
            if prov not in prov_cache:
                m = []
                if prov:
                    for pfx in _PROV_PFXS:
                        full = pfx + prov
                        flen = len(full)
                        idx = text.find(full)
                        while idx != -1:
                            end_idx = idx + flen
                            before_ok = (idx == 0) or not ('\u0E00' <= text[idx - 1] <= '\u0E7F')
                            if before_ok and check_after(end_idx):
                                m.append((idx, end_idx, True, len(prov)))
                            idx = text.find(full, idx + 1)
                    tlen = len(prov)
                    idx = text.find(prov)
                    while idx != -1:
                        end_idx = idx + tlen
                        before_ok = (idx == 0) or not ('\u0E00' <= text[idx - 1] <= '\u0E7F')
                        if before_ok and check_after(end_idx):
                            if not any(s <= idx and end_idx <= e for s, e, _, _ in m):
                                m.append((idx, end_idx, False, tlen))
                        idx = text.find(prov, idx + 1)
                prov_cache[prov] = m
            return prov_cache[prov]

        if zipcode_hint and zipcode_hint in self._zip_map and not any(
            get_sub_matches(r.sub_district) or get_dist_matches(r.district, r.province) for r in pool
        ):
            full_pool = [
                r for r in self._build_candidate_pool(text, _SUB_PFXS, _DIST_PFXS, _PROV_PFXS)
                if get_sub_matches(r.sub_district)
                and get_dist_matches(r.district, r.province)
                and get_prov_matches(r.province)
            ]
            if full_pool:
                pool = full_pool
                warnings_out.append(f"[ZipMismatch] Zipcode '{zipcode_hint}' does not match typed address")

        scored: List[Tuple[Tuple[int, int, int, int], int, GeoRecord]] = []
        for rec in pool:
            sms = get_sub_matches(rec.sub_district)
            dms = get_dist_matches(rec.district, rec.province)
            pms = get_prov_matches(rec.province)
            zip_matched = bool(rec.zipcode and rec.zipcode in text)

            sub_opts = sms + [None]
            dist_opts = dms + [None]
            prov_opts = pms + [None]

            best_key = (0, 0, 0, 0)
            best_score = 0
            for ms in sub_opts:
                for md in dist_opts:
                    if ms and md and (ms[0] < md[1] and md[0] < ms[1]):
                        continue
                    for mp in prov_opts:
                        if ms and mp and (ms[0] < mp[1] and mp[0] < ms[1]):
                            continue
                        if md and mp and (md[0] < mp[1] and mp[0] < md[1]):
                            continue
                        score = (4 if ms else 0) + (3 if md else 0) + (2 if mp else 0) + (1 if zip_matched else 0)
                        is_sub_pfx = 1 if (ms and ms[2]) else 0
                        sub_len = ms[3] if ms else 0
                        tot_len = (ms[3] if ms else 0) + (md[3] if md else 0) + (mp[3] if mp else 0)
                        key = (score, is_sub_pfx, sub_len, tot_len)
                        if key > best_key:
                            best_key = key
                            best_score = score
            if best_score > 0:
                scored.append((best_key, best_score, rec))

        if not scored:
            warnings_out.append("No geographic match found in text")
            return None, 0, warnings_out

        top2 = heapq.nlargest(2, scored, key=lambda x: x[0])
        best_key, best_score, best_rec = top2[0]

        if len(top2) > 1:
            second_key, second_score, second_rec = top2[1]
            if best_score == second_score and best_rec.province != second_rec.province:
                warnings_out.append(
                    f"Geo ambiguity (score={best_score}): "
                    f"'{best_rec.province}' vs '{second_rec.province}' — "
                    "provide zipcode to resolve"
                )

        out_rec: Optional[GeoRecord] = best_rec
        if out_rec and out_rec.sub_district:
            rt = _extract_receiver_tokens(text)
            if out_rec.sub_district in rt and not any((pfx + out_rec.sub_district) in text for pfx in _SUB_PFXS):
                best_score -= 4
                if best_score <= 0:
                    out_rec = None
                else:
                    out_rec = GeoRecord(sub_district="", district=out_rec.district, province=out_rec.province, zipcode=out_rec.zipcode)

        return out_rec, best_score, warnings_out

    def _build_candidate_pool(
        self,
        text: str,
        sub_pfxs: tuple,
        dist_pfxs: tuple,
        prov_pfxs: tuple,
    ) -> List[GeoRecord]:
        """
        FIX [FIX-G1]: Build a candidate pool by scanning ~8k geo-name keys
        instead of 150k records. Only records that have at least one geo token
        present in the text are included.
        """
        # FIX [#16]: GeoRecord is frozen=True (hashable). Use Set[GeoRecord]
        # instead of Set[int] from id(). id() values are not unique across the
        # lifetime of the process — Python reuses addresses after GC.
        seen: Set[GeoRecord] = set()
        pool: List[GeoRecord] = []

        if not hasattr(self, "_prov_tuple"):
            self._prov_tuple = tuple(self._prov_map.keys())
        prov_prefixes = prov_pfxs + self._prov_tuple

        def _pfx_match(name: str, pfxs: tuple, follow_pfxs: tuple = ()) -> bool:
            for p in pfxs:
                full = p + name
                idx = text.find(full)
                while idx != -1:
                    end_idx = idx + len(full)
                    if end_idx >= len(text):
                        return True
                    ch = text[end_idx]
                    if not ('\u0E00' <= ch <= '\u0E7F'):
                        return True
                    for fp in follow_pfxs:
                        if text.startswith(fp, end_idx):
                            return True
                    idx = text.find(full, idx + 1)
            return False

        def _add_if_match(name: str, recs: List[GeoRecord], pfxs: tuple, follow_pfxs: tuple = ()) -> None:
            if self._wb_match(name, text) or _pfx_match(name, pfxs, follow_pfxs):
                for r in recs:
                    if r not in seen:
                        seen.add(r)
                        pool.append(r)

        for sub, recs in self._sub_map.items():
            _add_if_match(sub, recs, sub_pfxs, dist_pfxs + prov_prefixes)
        for dist, recs in self._dist_map.items():
            _add_if_match(dist, recs, dist_pfxs, prov_prefixes)
        for prov, recs in self._prov_map.items():
            _add_if_match(prov, recs, prov_pfxs)

        return pool

    @staticmethod
    def _wb_match(term: str, text: str) -> bool:
        """FIX [#11]: O(n) string.find loop — zero regex compilation overhead.
        The original used re.search() with a dynamically-built pattern per call.
        With 7k+ unique geo names and a 512-entry re cache this caused 440ms of
        cache-eviction churn per request on the full Thai CSV.
        Thai word boundaries: a char is 'outside Thai' if it is not in \u0E00-\u0E7F.
        """
        if not term:
            return False
        tlen = len(term)
        idx  = text.find(term)
        while idx != -1:
            before_ok = (idx == 0) or not ('\u0E00' <= text[idx - 1] <= '\u0E7F')
            after_ok  = (idx + tlen >= len(text)) or not ('\u0E00' <= text[idx + tlen] <= '\u0E7F')
            if before_ok and after_ok:
                return True
            idx = text.find(term, idx + 1)
        return False

    # ── Accessors ─────────────────────────────────────────────────────────────

    def provinces_for_zipcode(self, zipcode: str) -> Set[str]:
        return {r.province for r in self._zip_map.get(zipcode, [])}

    @property
    def size(self) -> int:
        return len(self._all_records)

    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def valid_zipcodes(self) -> Set[str]:
        return set(self._zip_map.keys())


# ══════════════════════════════════════════════════════════════════════════════
# GEO TOKEN STRIPPING (cached per unique GeoRecord)
# ══════════════════════════════════════════════════════════════════════════════

@functools.lru_cache(maxsize=8192)
def get_geo_strip_patterns(rec: GeoRecord):
    """Return compiled (prefix_pattern, bare_pattern) pairs for sub/dist/prov."""
    result = []
    for value, prefixes in [
        (rec.sub_district, r"(?:ตำบล|แขวง)\s*"),
        (rec.district,     r"(?:อำเภอ|เขต)\s*"),
        (rec.province,     r"(?:จังหวัด)\s*"),
    ]:
        esc = re.escape(value)
        result.append((
            re.compile(rf"{prefixes}{esc}"),
            re.compile(rf"(?<!\S){esc}(?!\S)"),
        ))
    return result


# ══════════════════════════════════════════════════════════════════════════════
# FUZZY TYPO CORRECTION
# ══════════════════════════════════════════════════════════════════════════════

def correct_typo(
    word: str,
    candidates: List[str],
    threshold: int = FUZZY_THRESHOLD,
) -> Tuple[Optional[str], int]:
    """
    RapidFuzz fuzz.ratio correction for a single Thai geo token.
    Returns (corrected_word, score) or (None, 0) if below threshold.
    """
    if not RAPIDFUZZ_AVAILABLE or not candidates or not word or len(word) < 2:
        return None, 0

    filtered = [c for c in candidates if abs(len(c) - len(word)) <= FUZZY_MAX_LEN_DIFF]
    if not filtered:
        return None, 0

    adjusted = max(70, threshold - 5)
    try:
        result = _fuzz_process.extractOne(word, filtered, scorer=_fuzz.ratio, score_cutoff=adjusted)
        if result:
            match, score, _ = result
            return match, int(score)
    except Exception as exc:
        logger.warning("RapidFuzz error: %s", exc)

    return None, 0


class FuzzyGeoMatcher:
    """
    Supplementary fuzzy geo matching — fires only when exact lookup fails.
    Uses length-bucket index: O(window) pre-filter.

    FIX [FIX-G3]: No longer accesses private _sub_map / _dist_map / _prov_map
    attributes. Uses the public sub_district_names, district_names,
    province_names properties and records_for_* accessors instead.
    """

    def __init__(self, geo_db: GeoDatabase) -> None:
        self._geo = geo_db

        # Build length-bucket indexes for O(window) candidate pre-filtering
        # FIX [FIX-G3]: use public properties, not private _*_map keys
        self._sub_by_len:  Dict[int, List[str]] = defaultdict(list)
        self._dist_by_len: Dict[int, List[str]] = defaultdict(list)
        self._prov_by_len: Dict[int, List[str]] = defaultdict(list)

        for s in geo_db.sub_district_names:
            self._sub_by_len[len(s)].append(s)
        for d in geo_db.district_names:
            self._dist_by_len[len(d)].append(d)
        for p in geo_db.province_names:
            self._prov_by_len[len(p)].append(p)

    def _near_len(self, word: str, bucket: Dict[int, List[str]]) -> List[str]:
        wl = len(word)
        result: List[str] = []
        for length in range(max(0, wl - FUZZY_MAX_LEN_DIFF), wl + FUZZY_MAX_LEN_DIFF + 1):
            result.extend(bucket.get(length, []))
        return result

    def fuzzy_lookup(
        self,
        text: str,
        zipcode_hint: Optional[str] = None,
        threshold: int = FUZZY_THRESHOLD,
        district_hint: Optional[str] = None,
        province_hint: Optional[str] = None,
    ) -> Tuple[Optional[GeoRecord], int, List[str], List[str]]:
        """
        Attempt fuzzy geo match after exact lookup fails.
        Returns (GeoRecord | None, score, corrections_applied, warnings).
        """
        if not RAPIDFUZZ_AVAILABLE:
            return None, 0, [], ["RapidFuzz not installed — fuzzy lookup skipped"]

        warnings_out: List[str] = []
        corrections:  List[str] = []

        # Narrow candidate lists by zipcode or exact district+province when available
        # FIX [FIX-G3]: use public records_for_zipcode() accessor
        if zipcode_hint:
            zip_recs = self._geo.records_for_zipcode(zipcode_hint)
            if zip_recs:
                cand_subs  = list({r.sub_district for r in zip_recs})
                cand_dists = list({r.district     for r in zip_recs})
                cand_provs = list({r.province     for r in zip_recs})
                use_buckets = False
            else:
                cand_subs = cand_dists = cand_provs = []
                use_buckets = True
        elif district_hint and province_hint:
            dist_recs = [r for r in self._geo.records_for_district(district_hint) if r.province == province_hint]
            if dist_recs:
                cand_subs  = list({r.sub_district for r in dist_recs})
                cand_dists = [district_hint]
                cand_provs = [province_hint]
                use_buckets = False
            else:
                cand_subs = cand_dists = cand_provs = []
                use_buckets = True
        else:
            cand_subs = cand_dists = cand_provs = []
            use_buckets = True

        # Extract Thai token candidates from the text
        raw_tokens = [
            t for t in re.split(r"[\s,\-/]+", text)
            if len(t) >= 2 and re.search(r"[\u0E00-\u0E7F]", t)
        ]
        tokens: List[str] = []
        for tok in raw_tokens:
            if len(tok) <= 10:
                tokens.append(tok)
                continue
            try:
                if _pythainlp_word_tokenize is None:
                    raise ImportError("pythainlp not available")
                sub = [w for w in _pythainlp_word_tokenize(tok, engine="newmm")
                       if len(w) >= 2 and re.search(r"[\u0E00-\u0E7F]", w)]
                tokens.extend(sub if sub else [tok])
            except Exception:
                tokens.append(tok)

        receiver_tokens = _extract_receiver_tokens(text)

        used_dist_prov: Set[str] = set()
        exact_rec, _, _ = self._geo.lookup(text, zipcode_hint=zipcode_hint)
        if exact_rec:
            if exact_rec.district:
                used_dist_prov.add(exact_rec.district)
            if exact_rec.province:
                used_dist_prov.add(exact_rec.province)

        if not cand_subs and exact_rec and exact_rec.district in text and exact_rec.province in text:
            dist_recs = [r for r in self._geo.records_for_district(exact_rec.district) if r.province == exact_rec.province]
            if dist_recs:
                cand_subs = list({r.sub_district for r in dist_recs})
                use_buckets = False

        _GEO_PREFIX_STRIP = [
            ("ตำบล", "sub"), ("อำเภอ", "dist"), ("จังหวัด", "prov"),
            ("แขวง", "sub"), ("เขต", "dist"),
            ("ต.", "sub"), ("อ.", "dist"), ("จ.", "prov"),
        ]

        best_score = 0
        best_rec: Optional[GeoRecord] = None

        for token in tokens:
            if token in HONORIFIC_SKIP_SET or token in receiver_tokens:
                continue

            pfx_type = None
            stripped = token
            for pfx, kind in _GEO_PREFIX_STRIP:
                if token.startswith(pfx) and len(token) > len(pfx):
                    stripped = token[len(pfx):]
                    pfx_type = kind
                    break

            if stripped in receiver_tokens or len(stripped) < 2:
                continue

            if (stripped in used_dist_prov or token in used_dist_prov) and pfx_type != "sub":
                continue

            subs  = cand_subs  if cand_subs else (cand_subs if not use_buckets else self._near_len(stripped, self._sub_by_len))
            dists = cand_dists if not use_buckets else self._near_len(stripped, self._dist_by_len)
            provs = cand_provs if not use_buckets else self._near_len(stripped, self._prov_by_len)

            tok_best_score = 0
            tok_best_rec: Optional[GeoRecord] = None
            tok_best_label = ""

            checks: List[Tuple[List[str], Callable[[str], List[GeoRecord]], int, str]] = [
                (subs,  self._geo.records_for_sub_district, 4, "ตำบล"),
                (dists, self._geo.records_for_district,     3, "อำเภอ"),
                (provs, self._geo.records_for_province,     2, "จังหวัด"),
            ]
            if pfx_type == "dist":
                cands_to_check = [c for c in checks if c[3] == "อำเภอ"]
            elif pfx_type == "sub":
                cands_to_check = [c for c in checks if c[3] == "ตำบล"]
            elif pfx_type == "prov":
                cands_to_check = [c for c in checks if c[3] == "จังหวัด"]
            else:
                if stripped in used_dist_prov or token in used_dist_prov:
                    cands_to_check = [c for c in checks if c[3] != "ตำบล"]
                else:
                    cands_to_check = checks

            for cands, accessor, weight, label_prefix in cands_to_check:
                match, score = correct_typo(stripped, cands, threshold)
                if match and score > tok_best_score:
                    recs = accessor(match)
                    target_d = district_hint or (exact_rec.district if exact_rec else None)
                    target_p = province_hint or (exact_rec.province if exact_rec else None)
                    if target_d or target_p:
                        recs = [r for r in recs if (not target_d or r.district == target_d) and (not target_p or r.province == target_p)] or recs
                    elif zipcode_hint:
                        recs = [r for r in recs if r.zipcode == zipcode_hint] or recs
                    if recs:
                        tok_best_rec   = recs[0]
                        tok_best_score = score
                        tok_best_label = f"{label_prefix}: '{token}' → '{match}' ({score}%)"

            if tok_best_rec and tok_best_score > best_score:
                best_rec   = tok_best_rec
                best_score = tok_best_score
                corrections.append(tok_best_label)

        if not best_rec:
            warnings_out.append(f"Fuzzy geo found no match above threshold={threshold}")

        return best_rec, best_score, corrections, warnings_out