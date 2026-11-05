#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ThaiSmartAddress v7.0 — parser.py
Unified hybrid NLP pipeline.

Parse pipeline per request:
    Phase -1  Intent Shield        — reject non-address chat junk (O(1))
    Phase  0  Keyboard Fallback    — convert English-layout Thai input
    Phase  A  Rule-Based Core      — normalise -> phone -> zip -> geo -> tags -> leftovers
    Phase  B  Fuzzy Geo            — RapidFuzz typo correction (if Phase A geo missed)
    Phase  C  NER Fallback         — PyThaiNLP thainer (if receiver still missing)
    Final     Strict Validation    — confidence + flag low-quality results

NEW FIXES applied (this version):
  [FIX-P2] Text is normalised ONCE in parse() and passed to both
            _rule_based_parse() and _apply_fuzzy_geo(). Previously
            _apply_fuzzy_geo() called _normalise() a second time on an already-
            normalised string, wasting an O(n) regex pass on every request.
  [FIX-P3] NER worker call in ner_extract() now has a 10-second timeout.
            Without it, a malformed string could hang the single NER thread
            permanently, blocking every subsequent NER call for all users.
"""
from __future__ import annotations

import concurrent.futures
import logging
import re
import time
import threading
import unicodedata
import warnings as _warnings
from typing import Dict, List, Optional, Set, Tuple

from constants import (
    CHAT_JUNK_PATTERN, CONNECTOR_PATTERN,
    COURIER_STRIP_RE,
    FUZZY_THRESHOLD, GREETING_LEAD_PATTERN, HONORIFIC_PATTERN,
    INTENT_NEG_KEYWORDS,
    NAME_STOP_WORDS, NER_FALLBACK_THRESHOLD,
    PHONE_RE, RECEIVER_LABEL_RE, TAG_PATTERNS,
    ZIPCODE_COMPLAINT_RE, ZIPCODE_RE,
    expand_abbreviations,
)
from geo_engine import (
    DIST_PFXS,
    FuzzyGeoMatcher,
    GeoDatabase,
    PROV_PFXS,
    RAPIDFUZZ_AVAILABLE,
    SUB_PFXS,
    correct_typo,
    get_geo_strip_patterns,
)
from models import CorrectionRecord, NERResult, ParseResult

logger = logging.getLogger("ThaiSmartAddress")

ADDRESS_DETAIL_RE = re.compile(
    r"(?:"
    r"(?:^|(?<![฀-๿A-Za-z]))(?:หมู่บ้าน|ซอย|ซ\.|ถนน|ถ\.|ตรอก|อาคาร|ตึก|คอนโด|หอพัก|แฟลต|อพาร์ทเม้นท์|อพาร์ตเมนต์|ห้อง|ชั้น|โครงการ|ตู้\s*ปณ\.?|ร้านกาแฟ)[^\n]{2,120}"
    r"|"
    r"\d+(?:/\d+)?"
    r"(?:\s*(?:หมู่\s*\d+|ม\.\s*\d+))?"
    r"(?:\s*[^\n]{0,120})?"
    r")"
)

# ──────────────────────────────────────────────────────────────────────────────
# OPTIONAL: PyThaiNLP
# ──────────────────────────────────────────────────────────────────────────────

PYTHAINLP_AVAILABLE = False

try:
    from pythainlp.tag import NER as _ThaiNER  # type: ignore
    PYTHAINLP_AVAILABLE = True
    logger.info("PyThaiNLP detected — NER fallback enabled")
except ImportError:
    _warnings.warn("pythainlp not installed — NER fallback DISABLED.", stacklevel=2)


# NER worker: single dedicated thread prevents OOM (model ~200 MB)
_ner_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="ner-worker"
)
_global_ner_model = None
# FIX [#20]: Use threading.Event instead of bare bool for thread-safe signalling.
# The NER thread sets this flag; the TSA worker threads read it. A plain bool
# assignment is safe on CPython (GIL) but is unsafe on PyPy / no-GIL Python.
# threading.Event uses an internal Condition + RLock for full memory-barrier semantics.
_ner_load_failed = threading.Event()


def _do_ner_task(text: str) -> List[Tuple[str, str]]:
    global _global_ner_model

    if _ner_load_failed.is_set():
        raise RuntimeError("NER model previously failed to load — skipping")

    if _global_ner_model is None:
        try:
            _global_ner_model = _ThaiNER("thainer")
        except TypeError:
            try:
                _global_ner_model = _ThaiNER("thainer", pos=False, crf_parallel=False)
            except Exception as exc:
                _ner_load_failed.set()
                raise RuntimeError(f"NER model load failed: {exc}") from exc
        except Exception as exc:
            _ner_load_failed.set()
            raise RuntimeError(f"NER model load failed: {exc}") from exc

    return _global_ner_model.get_ner(text)


# ──────────────────────────────────────────────────────────────────────────────
# NER FALLBACK  (Phase C)
# ──────────────────────────────────────────────────────────────────────────────

_NER_PERSON_TAGS:   Set[str] = {"B-PERSON", "I-PERSON"}
_NER_LOCATION_TAGS: Set[str] = {"B-LOCATION", "I-LOCATION", "B-LOC", "I-LOC"}

# FIX [FIX-P3]: Added timeout=10 to .result() call.
# Without this, a hanging NER model on one request blocks the single-worker
# executor permanently, causing every subsequent NER call to queue indefinitely.
_NER_TIMEOUT_SECONDS: int = 10


def ner_extract(text: str) -> NERResult:
    """
    Run PyThaiNLP 'thainer' NER via the dedicated single-worker thread.
    Degrades gracefully if PyThaiNLP is absent or the model fails.
    """
    result = NERResult()
    if not PYTHAINLP_AVAILABLE:
        return result

    try:
        # FIX [FIX-P3]: timeout prevents permanent hang on malformed input
        tagged: List[Tuple[str, str]] = _ner_executor.submit(
            _do_ner_task, text
        ).result(timeout=_NER_TIMEOUT_SECONDS)

        result.raw_entities = tagged
        result.used_ner = True

        person_tokens = [
            tok for tok, tag in tagged
            if tag in _NER_PERSON_TAGS and not re.match(r"^[\d/]+$", tok) and tok
        ]
        if person_tokens:
            result.receiver = "".join(person_tokens).strip()

        location_tokens = [tok for tok, tag in tagged if tag in _NER_LOCATION_TAGS and len(tok) > 1]
        if location_tokens:
            result.location_hint = " ".join(location_tokens).strip()

    except concurrent.futures.TimeoutError:
        logger.warning("NER extraction timed out after %ds — skipping for this request", _NER_TIMEOUT_SECONDS)
        result.used_ner = False
    except Exception as exc:
        logger.warning("NER extraction failed: %s", exc)
        result.used_ner = False

    return result


_DETAIL_NOISE_RES: List[re.Pattern] = [
    re.compile(p, flags=re.IGNORECASE)
    for p in (
        # Chat leftovers
        r"(?:ออเดอร์|รหัสลูกค้า)\s*[:#\-]?\s*\d+",
        r"[\U00010000-\U0010ffff\u200d\u2300-\u27bf\u2b00-\u2bff\ufe00-\ufe0f]+",
        r"\([^)]*(?:ตอน\s*(?:เช้า|สาย|เที่ยง|บ่าย|เย็น|ค่ำ|ดึก)|ช่วง\s*(?:เช้า|สาย|เที่ยง|บ่าย|เย็น|ค่ำ|ดึก|\d+)|(?:ก่อน|หลัง)\s*(?:\d+\s*โมง|\d+[:.]\d+|เที่ยง|บ่าย)|(?:โทร|ติดต่อ)\s*(?:ก่อน|แจ้ง|บอก|หา|นัด|ตาม|ส่ง|\d)|(?<=\s|\()ก่อน(?:\s*ส่ง)?(?=\s|\)))[^)]*\)",
        r"(?:ขอ|ต้องการ)?ใบกำกับภาษี(?:\s*เต็มรูปแบบ)?[^\s]*",

        # Urgent & instructions
        r"ของต้องถึง(?:ภายใน[^\s]+|วัน[^\s]+|พรุ่งนี้|ด่วน)?",
        r"ต้องถึง(?:ภายใน[^\s]+|วัน[^\s]+|พรุ่งนี้|ด่วน)?",
        r"ของขวัญต้องถึงภายใน[^\s]+",
        r"(?:ต้อง)?ใช้(?:ในงาน)?(?:วัน[^\s]+|พรุ่งนี้|ด่วน)?",
        r"ต้องการใช้พรุ่งนี้",
        r"เพราะต้องใช้[^\s]*",
        r"ขอให้ถึง(?:ก่อนวัน[^\s]+|เร็วที่สุด|ภายใน[^\s]+)",
        r"(?:ขอให้|ฝาก)?(?:จัด)?ส่ง(?:ให้)?(?:ภายในวัน[^\s]+|วันนี้นะคะ|วันนี้|ก่อนวัน[^\s]+|ด่วน(?:ที่สุด|มาก)?|เร็ว(?:ที่สุด)?)",
        r"(?:ขอ)?ส่งก่อนเที่ยง[^\s]*",
        r"ก่อนเที่ยง[^\s]*",
        r"(?:ขอ)?ส่งก่อนบ่าย[^\s]*",
        r"ก่อนบ่าย[^\s]*",
        r"ฝากจัด[^\s]*",
        r"รบกวนส่งด่วนมาก|รบกวนส่งเร็ว",
        r"ขอส่งด่วน(?:ที่สุด)?",
        r"ขอส่งเร็ว(?:ที่สุด)?",
        r"รีบส่ง(?:ให้หน่อย|นะคะ|นะ|ด้วย)?",
        r"ถ้าเป็นไปได้ขอ[^\s]*",
        r"(?:ถึงก่อน|ถึงภายใน|ก่อนวัน|ภายในวัน|ในงาน|วันเสาร์|วันอาทิตย์|วันจันทร์|วันอังคาร|วันพุธ|วันพฤหัส|วันศุกร์|วันพรุ่งนี้|วันนี้|พรุ่งนี้)[^\s]*",
        r"(?:จัด)?ส่ง(?:ให้)?(?:เร็ว|ด่วน)[^\s]*",
        r"(?:เร็ว|ด่วน)(?:ที่สุด|มาก|ๆ)?",
        r"(?:จัด)?ภายใน[^\s]*",
        r"ใช้พรุ่งนี้",
        r"วันพรุ่งนี้",
        r"พรุ่งนี้",
        r"ด่วนจี๋",
        r"ด่วนมาก",
        r"ด่วนที่สุด",
        r"ด่วน",

        # Fragile & products
        r"(?:ของ)?(?:มี)?(?:เครื่องแก้วและเซรามิก|จานเซรามิกและแก้วไวน์|จานเซรามิก|เซรามิก|ขวดน้ำหอม|แก้วกาแฟ|แก้วไวน์|แจกันแก้ว|ขวดแก้ว|เครื่องแก้ว|กระจก|จานกระเบื้อง|กระเบื้อง|ของเปราะบาง|จาน|แก้ว|ขวด|ชาม|สิ่งของ|สินค้า)?\s*(?:แตกง่าย|เปราะบาง|แตกได้)(?:และ|ค่ะ|ครับ|นะคะ)?",
        r"(?:ของ|สินค้า|ข้างใน|ในกล่อง|กล่องนี้|กล่อง)?\s*(?:เป็น|มี)?\s*(?:เครื่องแก้วและเซรามิก|จานเซรามิกและแก้วไวน์|จานเซรามิก|เซรามิก|ขวดน้ำหอม|แก้วกาแฟ|แก้วไวน์|แจกันแก้ว|ขวดแก้ว|เครื่องแก้ว|กระจก|จานกระเบื้อง|กระเบื้อง|ของเปราะบาง)(?:หลายใบ)?(?:ค่ะ|ครับ|นะคะ)?",
        r"(?:ฝาก)?ระวัง(?:ของ)?แตก(?:ด้วย(?:ค่ะ|ครับ|นะคะ)?)?",
        r"กล่องแก้ว|กล่องมีแก้ว|มีแก้ว",
        r"(?:ขอ)?(?:ห่อ)?(?:กันกระแทก|บับเบิล)(?:หลายชั้น)?",
        r"ขอแพ็กแน่นๆ",
        r"กล่องนี้ไม่แตกง่าย(?:ครับ|ค่ะ)?",
        r"กล่องนี้มี(?:แจกัน)?แก้ว",
        r"มีแจกันแก้ว|มีแก้ว",
        r"กล่องนี้",
        r"(?:รบกวน|ฝาก)?ติด(?:สติ๊กเกอร์)?\s*(?:fragile)?",
        r"ของแตกง่าย(?:นะคะ|นะ|ครับ|ค่ะ)?",
        r"แตกง่าย(?:และ|ค่ะ|ครับ|นะคะ)?",
        r"หลายใบ|หลายชั้น",
        r"ฝากติด",
        r"(?:วันนี้ต้องใช้|ต้องใช้วันนี้)(?:ค่ะ|ครับ|นะคะ)?",

        # Guard / fold / dry instructions
        r"(?:(?:ฝาก|วาง)(?:ไว้)?(?:ที่|กับ)?)?(?:ป้อมยาม|ป้อมหน้า|ป้อมประตู|รปภ\.?|security)(?:\s*ไว้)?(?:\s*(?:ได้|เลย|นะ|ด้วย|นะคะ|นะค่ะ|ค่ะ|คะ|ครับ))*",
        r"(?:ห้าม|อย่า)พับ(?:\s*เด็ดขาด)?(?:\s*(?:ได้|เลย|นะ|ด้วย|นะคะ|นะค่ะ|ค่ะ|คะ|ครับ))*",
        r"(?:ห้าม|อย่า)เปียก(?:\s*(?:ได้|เลย|นะ|ด้วย|นะคะ|นะค่ะ|ค่ะ|คะ|ครับ))*",
        r"(?:ห้าม|อย่า)วาง(?:ไว้)?หน้า(?:ประตู|บ้าน|ห้อง)(?:\s*(?:ได้|เลย|นะ|ด้วย|นะคะ|นะค่ะ|ค่ะ|คะ|ครับ))*",
        r"(?:ไม่(?:ต้อง)?\s*)?(?:(?:เก็บ|ชำระ|จ่าย)(?:เงิน)?ปลายทาง|\bcod\b)(?:\s*(?:นะคะ|นะ|ค่ะ|คะ|ครับ|ด้วย))*",

        # Delivery mode / negative
        r"ไม่มีของแตก(?:ครับ|ค่ะ)?",
        r"(?:[0-9๐-๙]+|หนึ่ง|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า|สิบ)\s*นาที(?:ค่ะ|ครับ|นะคะ|นะ)?",
        r"ของไม่แตก(?:ครับ|ค่ะ)?",
        r"มี(?:สุนัข|หมา)ดุ(?:ระวัง)?(?:ด้วย)?(?:\s*(?:นะคะ|นะ|ครับ|ค่ะ))?",
        r"ไม่มีคำสั่งพิเศษ(?:ครับ|ค่ะ)?",
        r"วางไว้หน้า(?:บ้าน|ประตู|ห้อง)(?:ได้)?(?:เลย)?(?:\s*(?:นะคะ|นะ|ครับ|ค่ะ|จ้ะ|จ้า))?",
        r"ไม่ต้อง\s*(?:ติด)?\s*แท็ก(?:ครับ|ค่ะ)?",
        r"ไม่ต้องรีบ(?:นะคะ|นะ|ครับ|ค่ะ)?",
        r"(?:ไม่ต้อง|อย่า)\s*กดกริ่ง(?:\s*(?:นะคะ|นะ|ครับ|ค่ะ))?",
        r"(?:ไม่อยู่บ้าน)?ฝากเพื่อนบ้าน(?:ได้)?(?:เลย)?(?:\s*(?:นะคะ|นะ|ครับ|ค่ะ))?",
        r"(?:^|\s)ถึงแล้ว(?:\s*(?:นะคะ|นะ|ครับ|ค่ะ))?(?=\s|$)",
        r"(?:^|\s)(?:มาก่อน\s*)?ถึงแล้วบอก(?:ด้วย)?(?:\s*(?:นะคะ|นะ|ครับ|ค่ะ))?(?=\s|$)",
        r"ไม่ต้อง(?:\s*(?:นะคะ|นะ|ครับ|ค่ะ))?",
        r"(?:ส่ง)?ตามรอบ(?:ปกติ)?(?:ได้)?(?:เลย)?(?:ครับ|ค่ะ|นะคะ)?",
        r"ส่ง(?:ได้ตาม)?ปกติ(?:ครับ|ค่ะ)?",
        r"ส่งธรรมดาได้(?:เลย(?:ครับ|ค่ะ)?)?",
        r"ฝาก(?:ไว้)?(?:ที่|กับ)\s*(?:แม่บ้าน|นิติบุคคล|นิติ|เจ้าหน้าที่|เคาน์เตอร์)(?:ได้)?(?:เลย)?(?:\s*(?:นะคะ|นะ|ครับ|ค่ะ))?",
        r"ได้ตามปกติ",
        r"ถึง(?:หน้า)?ปากซอยแล้ว(?:\s*(?:นะคะ|นะ|ครับ|ค่ะ))?",
        r"ปกติ",

        # Stray remaining connectors / preambles / suffixes / isolated province tokens
        r"(?:^|\s)ที่(?:เชียงใหม่|นนทบุรี|กรุงเทพมหานคร|ภูเก็ต|ชลบุรี|ขอนแก่น|ปทุมธานี|กาญจนบุรี|ลพบุรี|เพชรบุรี|ลำพูน|อุดรธานี|นครราชสีมา)(?=\s|$)",
        r"(?:^|\s)(?:ช่วยส่งให้|ช่วยส่ง|ส่งให้|จัดส่งให้|ช่วย|จัดส่ง|ของเป็น|เป็นจาน|เป็นขวด|ในกล่องมี|ข้างในเป็น|มีของ|สิน|ของ|เป็น|และ|หรือ|ขอ|ฝาก|รบกวน|เพราะ|หน่อย|รหัส|เลยนะ|เลย|หา|กรุณา|อย่าลืม|พี่|ด้วยนะ|ด้วย|ครับ|ค่ะ|คะ|นะคะ|นะค่ะ|จ้า|จ๊ะ|จ้ะ|ค้า|วันน|พรุ่งน|จัด|ภายใน|เร็ว|ด่วน|สุด|มี|ถึงก่อนวันเสาร|ภายในวันศุกร)(?=\s|$)",
    )
]


def _strip_empty_brackets(t: str) -> str:
    while re.search(r"[\(\[\{<（【［｛]\s*[\)\]\}>）】］｝]", t):
        t = re.sub(r"[\(\[\{<（【［｛]\s*[\)\]\}>）】］｝]", " ", t)
    return t


def _strip_greeting_lead(t: str) -> str:
    while True:
        gm = GREETING_LEAD_PATTERN.match(t)
        if not gm or not gm.group(0).strip():
            break
        t = t[gm.end():].strip()
    return t


# ══════════════════════════════════════════════════════════════════════════════
# SMART ADDRESS PARSER
# ══════════════════════════════════════════════════════════════════════════════

class SmartAddressParser:
    """
    Production-grade Thai address parser — Hybrid Elimination Strategy.
    """

    _CONFIDENCE_FIELDS = [
        "receiver", "phone", "address_detail",
        "sub_district", "district", "province", "zipcode",
    ]

    _STOP_PREFIXES: Tuple[str, ...] = (
        "ซอย", "ซ.", "ถนน", "ถ.", "ตรอก", "หมู่บ้าน", "หมู่", "ม.",
        "อาคาร", "ตึก", "ชั้น", "ห้อง", "คอนโด", "แฟลต", "หอพัก",
        "อพาร์ท", "อพาร์ต", "ตำบล", "อำเภอ", "จังหวัด", "แขวง", "เขต",
        "โรงพยาบาล", "โรงแรม", "โรงเรียน", "มหาวิทยาลัย", "เลขที่", "แอดมิน",
    )

    @classmethod
    def _is_name_stop(cls, tok: str) -> bool:
        return tok in NAME_STOP_WORDS or tok.startswith(cls._STOP_PREFIXES)

    def __init__(
        self,
        geo_db: GeoDatabase,
        fuzzy_threshold: int = FUZZY_THRESHOLD,
        ner_threshold: float = NER_FALLBACK_THRESHOLD,
    ) -> None:
        if not geo_db.is_loaded():
            raise ValueError("GeoDatabase must be loaded before creating the parser.")
        self._geo             = geo_db
        self._valid_zips      = geo_db.valid_zipcodes
        self._fuzzy           = FuzzyGeoMatcher(geo_db)
        self._fuzzy_threshold = fuzzy_threshold
        logger.info(
            "SmartAddressParser ready — geo=%d NER=%s Fuzzy=%s",
            geo_db.size, PYTHAINLP_AVAILABLE, RAPIDFUZZ_AVAILABLE,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def parse(self, raw_text: str) -> ParseResult:
        t0 = time.perf_counter()
        if not isinstance(raw_text, str):
            return ParseResult(
                status="Error",
                warnings=["Input must be a string"],
                processing_ms=self._elapsed(t0),
            )

        # FIX [#19]: Strip chat junk BEFORE the Intent Shield.
        # The shield runs on the raw string and looks for negative keywords.
        # "โอนแล้วค่ะ ต.แสนสุข อ.เมืองชลบุรี จ.ชลบุรี" would be rejected
        # because "โอนแล้ว" is a neg-keyword and digit_density is 0%. Pre-
        # stripping junk tokens removes the false signal before classification.
        preshield_text = CHAT_JUNK_PATTERN.sub(" ", raw_text).strip() or raw_text

        # Phase -1: Intent Shield (run on junk-stripped text)
        reject = self._intent_shield(preshield_text, t0)
        if reject:
            return reject

        text = raw_text

        # FIX [FIX-P2]: Normalise ONCE here, then pass the result to both
        # _rule_based_parse and _apply_fuzzy_geo. Previously _apply_fuzzy_geo
        # called _normalise() a second time on an already-normalised string.
        try:
            normalised = self._normalise(text)
        except ValueError as exc:
            result = ParseResult(
                status="Error",
                warnings=[str(exc)],
                processing_ms=self._elapsed(t0),
            )
            return result

        normalised, is_multi = self._split_multi_address(text, normalised)

        # Phase A: Rule-Based Core (receives pre-normalised text)
        result = self._rule_based_parse(normalised, t0)

        if is_multi:
            result.warnings.append("[MultiAddress] Multiple addresses detected in one message")

        # Phase B: Fuzzy Geo Correction
        geo_incomplete = not all([result.province, result.district, result.sub_district])
        if geo_incomplete and RAPIDFUZZ_AVAILABLE:
            # FIX [FIX-P2]: pass already-normalised text — no second _normalise call
            result = self._apply_fuzzy_geo(normalised, result)

        # Phase C: NER Fallback
        if result.receiver is None and PYTHAINLP_AVAILABLE:
            result = self._apply_ner(normalised, result)

        # Final: Strict Validation + Confidence
        result = self._compute_confidence(result)
        result = self._strict_validate(result)
        result.processing_ms = self._elapsed(t0)
        return result

    def parse_batch(self, texts: List[str]) -> List[ParseResult]:
        """FIX [#26]: Each address is isolated in its own try/except.
        A crash on one input must not abort the remaining 99 items."""
        results: List[ParseResult] = []
        for t in texts:
            try:
                results.append(self.parse(t))
            except Exception as exc:
                logger.error("parse_batch: unhandled error for input %r: %s", repr(t)[:80], exc, exc_info=True)
                results.append(ParseResult(
                    status="Error",
                    confidence=0.0,
                    warnings=["Internal error during parsing"],
                ))
        return results

    # ── Phase -1 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _is_monetary_zip(text: str, m: re.Match) -> bool:
        before = text[: m.start()].strip()
        after = text[m.end() :].lstrip()
        return bool(
            re.search(r"(?:^|[^฀-๿]|โอน|รวม|ชำระ|จ่าย)ยอด\s*$", before) or
            after.startswith("บาท")
        )

    def _intent_shield(self, raw_text: str, t0: float) -> Optional[ParseResult]:
        text_lower = raw_text.lower()
        has_money_zip = any(self._is_monetary_zip(raw_text, m) for m in ZIPCODE_RE.finditer(raw_text))
        has_neg_kw = any(kw in text_lower for kw in INTENT_NEG_KEYWORDS) or has_money_zip
        if not has_neg_kw:
            return None

        digits = re.sub(r"[^0-9]", "", raw_text)
        density = len(digits) / max(len(raw_text.strip()), 1)
        # [FIX-P4]: Use structured-digit check instead of digit density.
        # Density >= 4% passed any 3-digit monetary amount causing FPs.
        # [FIX-P6]: Before accepting a zipcode as a bypass signal, verify it is
        # not a monetary amount. "ยอด 30000 บาท" matches ZIPCODE_RE (30000 is
        # a real NE zipcode) but is a payment line. Check for monetary context
        # (preceded by ยอด or followed by บาท); if present, do not bypass.
        if PHONE_RE.search(raw_text):
            return None
        for m in ZIPCODE_RE.finditer(raw_text):
            if not self._is_monetary_zip(raw_text, m):
                return None

        result = ParseResult(
            status="Cannot ship",
            confidence=0.0,
            processing_ms=self._elapsed(t0),
            warnings=[
                f"[IntentShield] Rejected: non-address or missing delivery address "
                f"(neg_keyword=True, digit_density={density:.1%})"
            ],
        )
        logger.debug("IntentShield rejected input (density=%.1f%%): %r", density * 100, raw_text[:80])
        return result

    # ── Phase A: Rule-Based Core ──────────────────────────────────────────────

    # FIX [FIX-P2]: Accepts pre-normalised text — no longer calls _normalise internally.
    def _rule_based_parse(self, normalised_text: str, t0: float) -> ParseResult:
        result = ParseResult()
        text = normalised_text

        result.phone,   text = self._extract_phone(text)
        text = re.sub(
            r'(?<!\d)(?:0[6-9]\d[\s\-\./]?\d{3,4}[\s\-\./]?\d{3,4}|0[2-5]\d[\s\-\./]?\d{3}[\s\-\./]?\d{3,4})(?!\d)',
            ' ', text
        )  # Strip remaining phones after first extraction
        result.zipcode, text = self._extract_zipcode(text)

        geo_rec, geo_score, geo_warns = self._geo.lookup(text, zipcode_hint=result.zipcode)
        result.warnings.extend(geo_warns)

        # A bare word equal to a sub-district (e.g. a surname) must not beat a district the customer typed:
        # when the record's district is not in the text, look again without that word.
        if geo_rec and geo_rec.sub_district and not self._geo._wb_match(geo_rec.district, text) and not any(
            (p + geo_rec.district) in text for p in ("อำเภอ", "เขต")
        ):
            alt_rec, alt_score, _ = self._geo.lookup(text.replace(geo_rec.sub_district, " "), zipcode_hint=result.zipcode)
            if (
                alt_rec and alt_rec.province == geo_rec.province and alt_rec.district != geo_rec.district
                and any((p + alt_rec.district) in text for p in ("อำเภอ", "เขต"))
            ):
                geo_rec, geo_score = alt_rec, alt_score

        if geo_rec:
            if self._geo._wb_match(geo_rec.sub_district, text) or any(
                re.search(re.escape(pfx + geo_rec.sub_district) + r"(?![\u0E00-\u0E7F])|" + re.escape(pfx + geo_rec.sub_district) + r"(?=อ\.|อำเภอ|เขต|จ\.|จังหวัด)", text)
                for pfx in SUB_PFXS
            ):
                result.sub_district = geo_rec.sub_district

            if (geo_rec.district and (result.sub_district or
                self._geo._wb_match(geo_rec.district, text) or 
                any((pfx + geo_rec.district) in text for pfx in DIST_PFXS) or
                (geo_rec.district.startswith("เมือง") and ("เมือง" in text or "อ.เมือง" in text or "อำเภอเมือง" in text)))):
                result.district = geo_rec.district

            result.province = geo_rec.province
            if result.sub_district and geo_rec.zipcode and not result.zipcode:
                result.zipcode = geo_rec.zipcode
                if not (geo_score == 9 and not geo_warns and result.sub_district and result.district and result.province):
                    result.warnings.append(f"[AutoFill] Zipcode '{geo_rec.zipcode}' auto-filled from database")
            elif result.district and not result.zipcode:
                dist_zips = {r.zipcode for r in self._geo.records_for_district(result.district) if not result.province or r.province == result.province}
                if len(dist_zips) == 1:
                    result.zipcode = next(iter(dist_zips))
                    result.warnings.append(f"[AutoFill] Zipcode '{result.zipcode}' auto-filled from database")
            text = self._strip_geo_tokens(text, geo_rec)

        # Zipcode-driven Auto-Fill: Infer missing province, district, and sub-district from Zipcode
        if result.zipcode and result.zipcode in self._geo._zip_map and not any("ZipMismatch" in w for w in result.warnings):
            zip_pool = self._geo._zip_map[result.zipcode]
            if not result.province and zip_pool:
                result.province = zip_pool[0].province
                result.warnings.append(f"[AutoFill] Province '{result.province}' auto-filled from zipcode {result.zipcode}")
            if not result.district and zip_pool:
                dists = list(dict.fromkeys(r.district for r in zip_pool))
                if len(dists) == 1:
                    result.district = dists[0]
                    result.warnings.append(f"[AutoFill] District '{result.district}' auto-filled from zipcode {result.zipcode}")
            if not result.sub_district and zip_pool:
                subs = list(dict.fromkeys(r.sub_district for r in zip_pool))
                if len(subs) == 1:
                    result.sub_district = subs[0]
                    result.warnings.append(f"[AutoFill] Sub-district '{result.sub_district}' auto-filled from zipcode {result.zipcode}")
                else:
                    m = re.search(r'(?:ตำบล|แขวง|ต\.)\s*([ก-๙]+)', normalised_text)
                    if m:
                        match, score = correct_typo(m.group(1), subs, self._fuzzy_threshold)
                        if match != m.group(1) and sum(1 for s in subs if m.group(1) in s) > 1:
                            match = None
                        recs = [r for r in zip_pool if r.sub_district == match and (not result.district or r.district == result.district)]
                        if match and recs:
                            result.sub_district = match
                            result.district = recs[0].district
                            result.warnings.append(f"[FuzzyCorrection] ตำบล: '{m.group(1)}' → '{match}' ({score}%)")
                            text = re.sub(r"\s+", " ", re.sub(r"(?:ตำบล|แขวง)\s*" + re.escape(m.group(1)), " ", text)).strip()

        result.tags, text = self._extract_tags(text)
        result.receiver, result.address_detail = self._extract_receiver_and_address(text)
        return result

    # ── Step helpers ──────────────────────────────────────────────────────────

    _MULTI_GEO_RE = re.compile(
        r"ตำบล|แขวง|อำเภอ|เขต|จังหวัด|(?<!\d)\d{5}(?!\d)|(?<!\S)[ตอจ]\s+[ก-๙]"
    )

    def _find_phones(self, text: str) -> List[Tuple[re.Match, str]]:
        out: List[Tuple[re.Match, str]] = []
        for m in PHONE_RE.finditer(text):
            if m.start() > 0 and text[m.start() - 1].isdigit():
                if m.start() < 5 or text[m.start() - 5 : m.start()] not in self._valid_zips:
                    continue
            p = re.sub(r"[\s\-\./]", "", m.group())
            if p.startswith("+66"):
                p = "0" + p[3:]
            elif p.startswith("66") and not p.startswith("0"):
                p = "0" + p[2:]
            out.append((m, p))
        return out

    def _has_geo_signal(self, seg: str) -> bool:
        if not seg or not seg.strip():
            return False
        if self._MULTI_GEO_RE.search(seg):
            return True
        return bool(self._geo._build_candidate_pool(seg, SUB_PFXS, DIST_PFXS, PROV_PFXS))

    def _split_multi_address(self, raw_text: str, normalised: str) -> Tuple[str, bool]:
        num_m = re.search(r"(?:^|\s)1[.)]\s+(.+?)\s+2[.)]\s+(.+)$", normalised)
        if num_m:
            part1, part2 = num_m.group(1).strip(), num_m.group(2).strip()
            if self._find_phones(part1) and self._has_geo_signal(part1) and self._has_geo_signal(part2):
                return part1, True

        phones = self._find_phones(normalised)
        if len(phones) < 2:
            return normalised, False

        if "\n" in raw_text:
            lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
            norm_cache: Dict[int, str] = {}

            def _get_norm(i: int) -> str:
                if i not in norm_cache:
                    try:
                        norm_cache[i] = self._normalise(lines[i])
                    except ValueError:
                        norm_cache[i] = ""
                return norm_cache[i]

            head_has_phone = False
            for k in range(1, len(lines)):
                if not head_has_phone:
                    prev_ln = lines[k - 1].translate(str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789"))
                    if not self._find_phones(prev_ln):
                        continue
                    head_has_phone = True

                head_norm = " ".join(_get_norm(i) for i in range(k) if _get_norm(i)).strip()
                tail_norm = " ".join(_get_norm(i) for i in range(k, len(lines)) if _get_norm(i)).strip()
                if not head_norm or not tail_norm:
                    continue
                if re.match(r"^\s*1[.)]\s+", head_norm) and re.match(r"^\s*2[.)]\s+", tail_norm):
                    head_norm = re.sub(r"^\s*1[.)]\s+", "", head_norm).strip()
                p_head = self._find_phones(head_norm)
                p_tail = self._find_phones(tail_norm)
                if (
                    p_head
                    and p_tail
                    and p_head[0][1] != p_tail[0][1]
                    and self._has_geo_signal(head_norm)
                    and self._has_geo_signal(tail_norm)
                ):
                    return head_norm, True

        m1, p1 = phones[0]
        for m2, p2 in phones[1:]:
            if p2 == p1:
                continue
            before1 = normalised[: m1.start()]
            between = normalised[m1.end() : m2.start()]
            after2 = normalised[m2.end() :]
            b1_geo = bool(self._MULTI_GEO_RE.search(before1))
            if b1_geo + self._has_geo_signal(between) + self._has_geo_signal(after2) >= 2:
                if b1_geo:
                    return normalised[: m1.end()].strip(), True
                slash_m = re.search(r"\s+[/|;]\s+", between)
                if slash_m and self._has_geo_signal(between[: slash_m.start()]):
                    return normalised[: m1.end() + slash_m.start()].strip(), True
                zip_m = ZIPCODE_RE.search(between)
                if zip_m:
                    return normalised[: m1.end() + zip_m.end()].strip(), True
                return normalised[: m2.start()].strip(), True

        return normalised, False

    @staticmethod
    def _normalise(text: str) -> str:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Input must be a non-empty string")
        text = unicodedata.normalize("NFC", text)
        # Drop Unicode pictographs (So/Sk) and variation selectors
        text = "".join(
            " " if unicodedata.category(c) in ("So", "Sk")
            else ("" if (0xFE00 <= ord(c) <= 0xFE0F or 0xE0100 <= ord(c) <= 0xE01EF) else c)
            for c in text
        )
        if not text.strip():
            raise ValueError("Input must be a non-empty string")
        # FIX [#18]: Normalize Thai digits ๐–๙ to ASCII 0–9.
        # Without this, zipcodes/phones written in Thai numerals (e.g. ๒๐๑๓๐)
        # are invisible to ZIPCODE_RE, PHONE_RE, and the digit-density
        # calculation in the Intent Shield.
        text = text.translate(str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789"))
        # Strip invisible / zero-width Unicode chars
        text = re.sub(r"[\u200b\u200c\u200d\u200e\u200f\ufeff\u00a0]", " ", text)
        text = re.sub(r"[\n\r\t]+", " ", text)
        def _replace_o_zipcode(m: re.Match) -> str:
            tok = m.group(1)
            if sum(1 for c in tok if c.isdigit()) >= 3 and any(c in "Oo" for c in tok):
                return tok.replace("O", "0").replace("o", "0")
            return tok

        text = re.sub(r"(?<![^\W_]|[\u0E00-\u0E7F])([0-9Oo]{5})(?![^\W_]|[\u0E00-\u0E7F])", _replace_o_zipcode, text)
        # Inject spaces between Thai chars and digits (no-space input like "เอกราช0894561234บ้านเลขที่9")
        text = re.sub(r'([\u0E00-\u0E7F])(\d)', r'\1 \2', text)
        text = re.sub(r'(\d)([\u0E00-\u0E7F])', r'\1 \2', text)
        # "เขตคลองเตยกทม.10110" / "…กรุงเทพฯ10110": split glued Bangkok short names
        text = re.sub(r"([\u0E00-\u0E7F])(กทม\.|กรุงเทพฯ)", r"\1 \2", text)
        # Inject space before geo abbreviation prefixes glued to previous Thai word
        # "บางโฉลงอ.บางพลีจ.สมุทรปราการ" → "บางโฉลง อ.บางพลี จ.สมุทรปราการ"
        text = re.sub(r'([\u0E00-\u0E7F])(?<!กท)(?<!(?<![\u0E00-\u0E7F])อบ)(?<!\.ส)(?!(?<=(?<![\u0E00-\u0E7F])อส)ม\.)(ม\.|[ตอจซถ]\.)', r'\1 \2', text)
        # "จ.ชม." (Chiang Mai): undo the split of its trailing "ม."
        text = re.sub(r'(จ\.[ชน]) (ม\.)', r'\1\2', text)
        # Normalise decomposed Thai sara-am (ํา → ำ) from some keyboards/copy-paste
        # U+0E4D U+0E32  → U+0E33  (affects ตำ อำ จำ etc.)
        text = text.replace('\u0e4d\u0e32', '\u0e33')
        # Fix common geo-prefix typos that survive sara-am normalisation:
        #   ตำบน → ตำบล  (น/ล swap on Thai keyboard)
        #   อำเพอ → อำเภอ  (เพอ → เภอ)
        #   จังหว้ด → จังหวัด  (สระโอ้ → สระอา + วัจ)
        text = re.sub(r'ตำบน(?=[\u0E00-\u0E7F])', 'ตำบล', text)
        text = re.sub(r'อำเพอ(?=[\u0E00-\u0E7F])', 'อำเภอ', text)
        text = re.sub(r'จังหว้ด(?=[\u0E00-\u0E7F])', 'จังหวัด', text)
        # "Last delivery connector wins" — but ONLY when the preamble contains
        # geo signals (ตำบล/อำเภอ/zipcode), meaning the customer wrote their old
        # address first. Without that guard, "แพรว 0998887777 ค่ะ จัดส่งที่ ..."
        # would strip the receiver+phone before the connector.
        _LATE_CONN_RE = re.compile(
            r'(?s)(.{15,}?)(ส่งมาที่|จัดส่งที่|รบกวนส่งที่|ส่งไปที่)\s*[:\-]?\s*'
        )
        _GEO_SIGNAL_RE = re.compile(r'ตำบล|แขวง|อำเภอ|เขต|จังหวัด|\d{5}')
        lm = _LATE_CONN_RE.match(text)
        _PHONE_IN_PREAMBLE = re.compile(r'0\d{8,9}|\+66\d{9}')
        if (lm and lm.end() < len(text)
                and _GEO_SIGNAL_RE.search(lm.group(1))
                and not _PHONE_IN_PREAMBLE.search(lm.group(1))):
            text = text[lm.end():]

        # [FIX-N2] Strip negated parenthetical content.
        # "...(แต่อันนี้ไม่ต้องส่งนะ)..." tells the admin to ignore that block.
        text = re.sub(r'\([^)]{2,120}(?:ไม่ต้องส่ง|ไม่ต้อง|อย่าส่ง|ยกเลิก)[^)]{0,60}\)', ' ', text)
        text = re.sub(r'(?:เลข)?(?:ออเดอร์|(?i:order)|รหัสลูกค้า)\s*[:#\-]?\s*#?[A-Za-z]{0,3}\d+', ' ', text)
        text = re.sub(r'(?:(?:(?<![฀-๿])|(?<=โอน)|(?<=รวม)|(?<=ชำระ)|(?<=จ่าย))ยอด(?:โอน|รวม)?|ค่าส่ง)\s*[:\-]?\s*\d[\d,]*(?:\.\d+)?\s*(?:บาท|บ\.)?', ' ', text)
        text = re.sub(r'(?:ราคา\s*[:\-]?\s*)?(?<![\d/.,])\d[\d,]*(?:\.\d+)?\s*บาท', ' ', text)
        text = CHAT_JUNK_PATTERN.sub(" ", text)
        # Strip social media handle lines: "Line ID: xxx", "FB: xxx", "IG: xxx"
        # These must be removed before receiver extraction or they corrupt the name field.
        # Strip social media handle + all trailing tokens until next key-value pattern
        # "FB: ก้องเกียรติ สุดเท่" → " " (strips both words after FB:)
        text = re.sub(
            r'(?i)(?:line\s*(?:id|ID)|\b(?:id\s*)?line(?=\s*:)|facebook|fb|instagram|ig|twitter)\s*[:\-]?\s*[^\n\r:]+?(?=\s+(?:[ก-๙A-Za-z]+\s*:|$|\d{5})|$)',
            ' ', text
        )
        text = re.sub(r'(?:เบอร์สำรอง|เบอร์หลัก|เบอร์รอง)', ' ', text)
        text = re.sub(r'(?:^|\s)(?:หลัก|สำรอง|รอง)(?=\s|$)', ' ', text)
        # Strip brackets wrapping field labels: [ชื่อ]:, [เบอร์]:, [ที่อยู่]:
        text = re.sub(
            r'(?:^|(?<=\s))[(\[{<（【［｛](ผู้รับ|ชื่อผู้รับ|ชื่อลูกค้า|ลูกค้าชื่อ|ผู้รับคือ|ชื่อจริง|ชื่อเล่น|ชื่อ|เบอร์โทรศัพท์|เบอร์โทร|โทรศัพท์|โทร|tel|ติดต่อ|เบอร์|ที่อยู่|ตำบล|อำเภอ|จังหวัด|ไปรษณีย์|รหัสไปรษณีย์)[)\]}>）】］｝]',
            r'\1', text, flags=re.IGNORECASE
        )
        # A call-before-delivery request ("โทรก่อนส่ง") is not a phone label: drop it whole
        text = re.sub(r'โทร(?:ไป|หา)?ก่อน(?:ส่ง|ถึง)?(?:นะ(?:คะ|ครับ)?)?', ' ', text)
        # Strip phone labels WITH optional trailing colon/dash
        text = re.sub(
            r'(?i)(?:รหัสไปรษณีย์|เบอร์โทรศัพท์|เบอร์โทร|โทรศัพท์|โทร(?![\u0e31\u0e34-\u0e3a\u0e47-\u0e4e])\.?|tel\.|tel|ติดต่อ|เบอร์)\s*[:\-]?\s*',
            ' ', text
        )
        text = re.sub(r'([฀-๿])(\d)', r'\1 \2', text)
        text = re.sub(r'(\d)([฀-๿])', r'\1 \2', text)
        text = re.sub(r'ปณจ\.?', 'ปณจ', text)
        # FIX [P-F1]: Strip "รหัสไปรษณีย์ [customer complaint]" noise.
        text = ZIPCODE_COMPLAINT_RE.sub("", text)
        # [FIX-N3] Strip phone-extension suffixes ("ต่อ 15") before they bleed
        # into address_detail. Must run after phone-label stripping.
        text = re.sub(r'\s+ต่อ\s*\d+', ' ', text)
        text = expand_abbreviations(text)
        # [FIX-N4] Strip highway direction phrases e.g. "ขาเข้า กรุงเทพมหานคร"
        # "กทม." in "ขาเข้า กทม." means direction toward Bangkok, not the delivery province.
        # Must run after abbreviation expansion so "กทม." is already expanded.
        text = re.sub(r'ขา(?:เข้า|ออก)\s+(?:กรุงเทพมหานคร|[฀-๿]{3,20})', ' ', text)
        # [FIX-N10] Strip inline key-value labels (except receiver labels which are needed in Pass -1)
        text = re.sub(r'(?:^|(?<=\s))(?:ที่อยู่|ตำบล|อำเภอ|จังหวัด|ไปรษณีย์|Line\s*ID|FB|IG|Twitter)\s*[:\-]\s*', ' ', text, flags=re.IGNORECASE)
        text = re.sub(r'(?:^|(?<=\s))(?!ผู้รับ|ชื่อผู้รับ|ชื่อลูกค้า|ลูกค้าชื่อ|ผู้รับคือ)[ก-๙A-Za-z][ก-๙A-Za-z_0-9]*\s*:\s*', ' ', text)
        # Strip stray trailing dot after Thai char (end-of-string only, not mid-string)
        # Mid-string removal was breaking น.ส. → น.ส (dropped the dot before space)
        text = re.sub(r"([฀-๿])\.$", r"\1", text)
        text = re.sub(r"\s+", " ", text).strip()
        tokens = text.split()
        n = len(tokens)
        if n >= 8:
            for p in range(4, n // 2 + 1):
                if n % p == 0:
                    k = n // p
                    if tokens == tokens[:p] * k:
                        return " ".join(tokens[:p])
        return text

    def _extract_phone(self, text: str) -> Tuple[Optional[str], str]:
        # Uses self._find_phones(text) which validates adjacent self._valid_zips
        matches = self._find_phones(text)
        if not matches:
            return None, text
        m, raw = matches[0]
        start = m.start()
        end = m.end()
        if start > 0 and text[start - 1] in "([{" and end < len(text) and text[end] in ")]}":
            start -= 1
            end += 1
        text = text[: start] + " " + text[end:]
        while True:
            more = self._find_phones(text)
            if not more:
                break
            m2, _ = more[0]
            start = m2.start()
            end = m2.end()
            prefix = text[:start]
            sep_m = re.search(r"\s*(?:/|,|หรือ)\s*$", prefix)
            if sep_m:
                start = sep_m.start()
            elif start > 0 and text[start - 1] in "([{" and end < len(text) and text[end] in ")]}":
                start -= 1
                end += 1
            text = text[:start] + " " + text[end:]
        text = _strip_empty_brackets(text)
        return raw, re.sub(r"\s+", " ", text).strip()

    def _extract_zipcode(self, text: str) -> Tuple[Optional[str], str]:
        matches = [m for m in ZIPCODE_RE.finditer(text) if not self._is_monetary_zip(text, m)]
        if not matches:
            return None, text
        for m in matches:
            candidate = m.group()
            if candidate in self._valid_zips:
                text = text[: m.start()] + " " + text[m.end():]
                return candidate, re.sub(r"\s+", " ", text).strip()
        m    = matches[0]
        text = text[: m.start()] + " " + text[m.end():]
        return m.group(), re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _strip_geo_tokens(text: str, rec) -> str:
        for _i, (prefix_pat, bare_pat) in enumerate(get_geo_strip_patterns(rec)):
            _typed_pfx = _i == 0 and bool(rec.sub_district) and bool(re.search(r"(?:ต\.|ตำบล|แขวง)\s*" + re.escape(rec.sub_district) + r"(?![\u0E00-\u0E7F])", text))
            text = prefix_pat.sub(" ", text)
            if _typed_pfx:
                continue
            text = bare_pat.sub(" ", text)
        text = re.sub(ZIPCODE_RE, " ", text)
        _zc = getattr(rec, "zipcode", None)
        if _zc and len(_zc) == 5 and _zc.isdigit():
            text = re.sub(r"(?<!\d)" + r"[ \-]?".join(_zc) + r"(?!\d)", " ", text)
        # FIX [P-F2]: Remove orphaned geo-prefix stubs left when district name
        # was split across tokens (e.g. "เมือง เชียงใหม่" → "เมือง" stub after
        # "เมืองเชียงใหม่" is stripped as a unit).  Only strip when surrounded
        # by whitespace/boundary to avoid clipping legitimate place-name parts.
        if getattr(rec, "district", None) and rec.district.startswith("เมือง"):
            text = re.sub(r"(?<!\S)อำเภอ\s*เมือง(?!\S)", " ", text)
        def _abbr_of(m, name):
            s = m.group(2).rstrip("ฯ.").replace("์", "")
            it = iter(name or "")
            return " " if len(s) >= 2 and all(ch in it for ch in s) else m.group(0)
        text = re.sub(r"(?<!\S)(จังหวัด)(\S+)", lambda m: _abbr_of(m, getattr(rec, "province", None)), text)
        text = re.sub(r"(?<!\S)(อำเภอ)(\S+)", lambda m: _abbr_of(m, getattr(rec, "district", None)), text)
        text = re.sub(r"(?<!\S)(?:เมือง|อำเภอ|เขต|จังหวัด|ตำบล|แขวง)(?!\S)", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _extract_tags(text: str) -> Tuple[List[str], str]:
        tags: List[str] = []
        for pattern, tag in TAG_PATTERNS:
            if pattern.search(text):
                tags.append(tag)
        text = COURIER_STRIP_RE.sub(" ", text)
        text = re.sub(r"(?<!\S)(?:จัด)?ส่งไว(?:ๆ|มาก|หน่อย|ด้วย|นะ(?:คะ|ครับ)?|ค่ะ|ครับ|คะ)*(?!\S)", " ", text)
        return list(dict.fromkeys(tags)), text

    def _extract_receiver_and_address(
        self, text: str
    ) -> Tuple[Optional[str], Optional[str]]:
        receiver: Optional[str] = None

        # Pass -1: Explicit "ชื่อผู้รับ:" label anywhere in text  [FIX P-F3]
        # Real-world: customers append "ชื่อผู้รับ: ป้าสมศรี สู้ชีวิต" at the end.
        # This pass has highest priority — if present, trust it unconditionally.
        label_m = RECEIVER_LABEL_RE.search(text)
        if label_m:
            candidate = label_m.group(1).strip()
            candidate = re.sub(r"^[(\[{<\"'/（）【】［］｛｝\s]+|[)\]}>\"'/（）【】［］｛｝\s]+$", "", candidate).strip()
            if len(candidate) >= 2:
                receiver = candidate
                # Remove the entire label+name span from text
                end = label_m.end()
                while end < len(text) and text[end] in ")]}>/（）【】［］｛｝ ":
                    end += 1
                text = text[:label_m.start()] + " " + text[end:]
                text = re.sub(r"\s+", " ", text).strip()

        # [FIX-T8] Protect "เลขที่ N" from connector stripping — preserves house nums
        text = re.sub(r'เลขที่\s*(\d)', r'\1', text)
        text = _strip_greeting_lead(text)
        text = re.sub(r'(?:^|\s)ขอบคุณมาก(?:ๆ)?\s*เลย(?:\s*(?:นะคะ|นะค่ะ|นะ|ครับ|คับ|ค่ะ|คะ|ค่า|จ้า|จ้ะ))?(?=\s|$)', ' ', text)
        text = re.sub(r'(?:^|\s)ขอบคุณมาก(?:ๆ)?(?:\s*(?:นะคะ|นะค่ะ|นะครับ|นะ|ครับผม|ครับ|คับ|ค่ะ|คะ|ค่า|จ้า|จ้ะ))?(?=\s|$)', ' ', text)
        text = CONNECTOR_PATTERN.sub(" ", text)
        text = re.sub(r"\b(ด้วยนะ|หน่อยนะ|ด้วย)\b", " ", text)
        text = re.sub(r'[ก-๙A-Za-z_]+\s*:\s*', ' ', text)  # FIX-R1 orphan labels
        text = re.sub(r'(?:ขอบคุณมาก(?:ๆ)?(?:\s*พี่)|ขอบคุณ(?:ค่ะ|ค่า|คะ|ครับ|คับ)?\s*(?:คุณ)?พี่|ขอบคุณมากๆ|ขอบคุณนะ|ขอบคุณ(?:ค่ะ|ค่า|คะ|ครับ|คับ)?|รีบส่งนะ|รีบส่ง|รีบนะ|รีบ)(?:\s|$)', ' ', text)
        text = re.sub(r'(?:^|\s)(?:กท|มา|ด่วนๆ)(?=\s|$)', ' ', text)
        text = re.sub(r"\s+", " ", text).strip()
        text = _strip_greeting_lead(text)

        # Strip brackets wrapping receiver at start of text
        wrap_m = re.match(r"^\s*([(\[{<（【［｛])([ก-๙A-Za-z\s.]+?)([)\]}>）】］｝])", text)
        if wrap_m:
            candidate = wrap_m.group(2).strip()
            if len(candidate) >= 2 and not self._is_name_stop(candidate):
                rem = text[wrap_m.end():].strip()
                text = f"{candidate} {rem}".strip()

        # Pass A: Honorific anchor — include honorific in returned receiver
        # e.g. "คุณจิรายุ" → receiver = "คุณจิรายุ" (not just "จิรายุ")
        if receiver is None:
            for hm in HONORIFIC_PATTERN.finditer(text):
                start_idx = hm.start()
                end_idx   = hm.end()

                # Full span from honorific start to end of matched name
                full_honorific_span = text[start_idx:end_idx].strip()
                clean_span = re.sub(r"^ของ", "", full_honorific_span).strip()
                clean_span = re.sub(r"\s*ที่[ก-๙].*$", "", clean_span).strip()

                # Skip if matched span is actually a stop-word (e.g. "อาคาร", "ซอย", "ตึก")
                if clean_span in NAME_STOP_WORDS or any(
                    clean_span.startswith(sw) for sw in NAME_STOP_WORDS
                ):
                    continue

                after_text = text[end_idx:]
                second_m   = re.match(r"\s*([^\s\d/]{2,30})(?=\s|$)", after_text)

                if second_m:
                    candidate = second_m.group(1)
                    is_stop   = (
                        self._is_name_stop(candidate)
                        or candidate.startswith("ที่")
                        or candidate in ("ก่อน", "เดิม")
                        or candidate.startswith("ขอเบิก")
                    )
                    if not is_stop:
                        receiver  = f"{clean_span} {candidate}".strip()
                        end_idx  += second_m.end()
                    else:
                        receiver  = clean_span
                else:
                    receiver = clean_span

                if receiver:
                    text = text[:start_idx] + " " + text[end_idx:]
                    break

        # If receiver was set by Pass -1 (label), still strip pre-address preamble
        if receiver is not None:
            _pre = ADDRESS_DETAIL_RE.search(text)
            if _pre and _pre.start() > 0:
                text = text[_pre.start():].strip()
        # Pass B: house-number anchor
        if receiver is None:
            qty = ""
            qm = re.match(r"\s*\d+\s*(?:ชิ้น|ตัว|กล่อง|ชุด|ขวด|แพ็ค|อัน)(?![ก-๙])", text)
            if qm:
                qty = qm.group(0).strip()
                text = text[qm.end():].strip()
            am = ADDRESS_DETAIL_RE.search(text)
            if am:
                before = text[: am.start()].strip()
                if before:
                    clean_name = re.sub(r"(?i)(tel|โทร|เบอร์โทร)\s*$", "", before).strip()
                    clean_name = _strip_greeting_lead(clean_name)
                    trimmed: List[str] = []
                    started = False
                    for tok in clean_name.split():
                        if not started and (
                            tok in ("บริษัท", "บจก", "บ.", "หจก", "ห้างหุ้นส่วน")
                            or tok.startswith(("บริษัท", "บจก", "บ.", "หจก", "ห้างหุ้นส่วน"))
                            or (tok.startswith("ร้าน") and not tok.startswith("ร้านกาแฟ"))
                        ):
                            started = True
                            trimmed.append(tok)
                            continue
                        is_stop = self._is_name_stop(tok)
                        if is_stop:
                            if started:
                                # Stop-word after real name tokens → end of name
                                break
                            else:
                                # FIX [P-F5]: Leading noise token (e.g. แอดมิน) before
                                # the real receiver — skip it instead of aborting.
                                continue
                        else:
                            started = True
                            trimmed.append(tok)
                    clean_name = " ".join(trimmed).strip()
                    if clean_name:
                        receiver = clean_name
                        # [FIX-P2] Strip the entire "before" span from text, not just
                        # the extracted receiver tokens. The old approach tried
                        # re.sub("^" + receiver, ...) which failed when stop-word
                        # prefixes (e.g. "แอดมิน") preceded the receiver and were
                        # already skipped in the loop — leaving them in address_detail.
                        text = text[am.start():].strip()
            if qty:
                text = f"{qty} {text}".strip()

        # [FIX-P6] Strip leading company/org prefix before building digit/word.
        # GUARD: only fire when text starts with a company marker (บจก/บริษัท/หจก)
        # within the first 40 chars, so landmark addresses ("ร้านกาแฟหน้าปากซอย 2")
        # are NOT destroyed.
        _CO_RE = re.compile(r'(?:^|\s)(?:บจก|บริษัท|ห้างหุ้นส่วน|หจก|บ\.)\b', re.IGNORECASE)
        if receiver is not None and _CO_RE.search(text[:40]):
            _stripped = re.sub(r'^.*?(?=\d|(?:อาคาร|ตึก|คอนโด|ห้อง|ชั้น))', '', text, count=1, flags=re.DOTALL).strip()
            if _stripped and _stripped != text:
                text = _stripped
        # FIX [P-F4]: Strip trailing bracket/quote punctuation and location connectors from receiver.
        if receiver:
            receiver = re.sub(r"\s+ที่\s*[ก-๙]+.*$", "", receiver).strip()
            receiver = re.sub(r"^[\s()\[\]{}<>\"'/（）【】［］｛｝]+|[\s()\[\]{}<>\"'/（）【】［］｛｝]+$", "", receiver).strip()
            if len(receiver) < 2 or self._is_name_stop(receiver) or receiver.startswith("ร้านกาแฟ"):
                receiver = None

        # [FIX-P3] Pass D: Trailing personal name.
        # Some customers append their name at the very end of the message after
        # a complete address and phone number. By this point, phone/zipcode/geo
        # have already been extracted and stripped. If receiver is still None,
        # check whether the tail of the remaining text looks like a Thai name:
        # 1-3 Thai-character tokens, no digits, not a stop word, length ≤ 12 chars.
        # Guard: only fire when text starts with a digit (house-number pattern) —
        # meaning we have a real address and the trailing tokens are extra, not
        # the only content (avoids treating bare-name inputs as address+receiver).
        if receiver is None:
            remaining = re.sub(r"\s+", " ", text).strip()
            # [FIX-P3b] Fire Pass D even when text doesn't start with a digit.
            # Condo/building addresses ("หอพักป้าจุ๋ม ห้อง 305...") start with Thai
            # characters, not digits. We guard quality with token validation below.
            if remaining:
                tail_m = re.search(
                    r"(?:^|\s)((?:[^\s\d/]{2,20}\s*){1,2})\s*$",
                    remaining
                )
                if tail_m:
                    candidate = tail_m.group(1).strip()
                    tokens = candidate.split()
                    valid = (
                        len(tokens) >= 1 and
                        all(
                            re.search(r"[฀-๿]", t) and
                            not self._is_name_stop(t) and
                            not re.search(r"\d", t)
                            for t in tokens
                        )
                    )
                    if valid:
                        receiver = candidate
                        text = remaining[:tail_m.start(1)].rstrip()

        text = re.sub(r"\s+", " ", text).strip()
        address_detail = self._clean_address_detail(text.strip(" ,.-")) or None

        receiver = receiver.strip() if receiver else None
        if receiver and not any(c.isalnum() for c in receiver):
            receiver = None
        if address_detail and not any(c.isalnum() for c in address_detail):
            address_detail = None

        return (
            receiver,
            address_detail,
        )

    @staticmethod
    def _clean_address_detail(text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        t = text
        for p in _DETAIL_NOISE_RES:
            t = p.sub(" ", t)
        # Strip isolated stray vowels / tone marks at word boundaries or ends
        t = re.sub(r"(?:^|\s)[\u0E30-\u0E39\u0E47-\u0E4E]+(?=\s|$)", " ", t)
        t = re.sub(r"(?:^|\s)หมู่\s*$", " ", t)

        # Remove empty or unpaired bracket leftovers
        t = _strip_empty_brackets(t)

        _pairs = {"(": ")", "[": "]", "{": "}", "<": ">", "（": "）", "【": "】", "［": "］", "｛": "｝"}
        _closers = {")": "(", "]": "[", "}": "{", ">": "<", "）": "（", "】": "【", "］": "［", "｝": "｛"}
        _stack = []
        _unpaired = set()
        for idx, c in enumerate(t):
            if c in _pairs:
                _stack.append((c, idx))
            elif c in _closers:
                if _stack and _stack[-1][0] == _closers[c]:
                    _stack.pop()
                else:
                    _unpaired.add(idx)
        for _, idx in _stack:
            _unpaired.add(idx)
        if _unpaired:
            t = "".join(c for idx, c in enumerate(t) if idx not in _unpaired)

        t = re.sub(r"\s+", " ", t).strip(" ,.-")
        if t in ("ช่วย", "ส่ง", "จัดส่ง", "รบกวน", "ฝาก", "ที่", "แถว", "ช่วยส่งให้", "ส่งให้", "ค่ะ", "ครับ", "นะคะ"):
            return None
        if len(t) < 2 and not t.isdigit():
            return None
        return t or None

    # ── Phase B ───────────────────────────────────────────────────────────────

    # FIX [FIX-P2]: Removed internal _normalise() call — text is already
    # normalised by the time this method is called from parse().
    def _apply_fuzzy_geo(self, normalised_text: str, result: ParseResult) -> ParseResult:
        fuzzy_rec, _, corrections, fuzzy_warns = self._fuzzy.fuzzy_lookup(
            normalised_text,
            zipcode_hint=result.zipcode,
            threshold=self._fuzzy_threshold,
            district_hint=result.district,
            province_hint=result.province,
        )
        result.warnings.extend(fuzzy_warns)

        if fuzzy_rec:
            # If result already has a known province and fuzzy_rec belongs to a different province, reject cross-province hallucination
            if result.province and fuzzy_rec.province != result.province:
                return result

            # Only copy sub_district when fuzzy actually matched a sub_district token.
            sub_corrected = not result.sub_district and any(c.startswith('ตำบล') and fuzzy_rec.sub_district in c for c in corrections)
            if sub_corrected:
                result.sub_district = fuzzy_rec.sub_district
            dist_corrected = not result.district and any(c.startswith('อำเภอ') and fuzzy_rec.district in c for c in corrections)
            if dist_corrected:
                result.district = fuzzy_rec.district
            result.province     = result.province     or fuzzy_rec.province
            if not result.zipcode and (sub_corrected or dist_corrected):
                result.zipcode  = fuzzy_rec.zipcode
                result.warnings.append(f"[AutoFill] Zipcode '{fuzzy_rec.zipcode}' auto-filled from database")
            if sub_corrected or dist_corrected:
                for c in corrections:
                    result.warnings.append(f"[FuzzyCorrection] {c}")
                    m_src = re.match(r"(?:ตำบล|อำเภอ): '((?:ตำบล|อำเภอ|แขวง|เขต|ต\.|อ\.)[^']+)' →", c)
                    if m_src and result.address_detail and m_src.group(1) in result.address_detail:
                        result.address_detail = re.sub(r"\s{2,}", " ", result.address_detail.replace(m_src.group(1), " ")).strip() or None

        return result

    # ── Phase C ───────────────────────────────────────────────────────────────

    def _apply_ner(self, text: str, result: ParseResult) -> ParseResult:
        ner = ner_extract(text)
        if not ner.used_ner:
            return result

        if result.receiver is None and ner.receiver:
            result.receiver = ner.receiver
            result.warnings.append(f"[NERFallback] Receiver: '{ner.receiver}'")

        if result.province is None and ner.location_hint:
            geo_rec, _, geo_warns = self._geo.lookup(ner.location_hint, zipcode_hint=result.zipcode)
            result.warnings.extend(geo_warns)
            if geo_rec:
                result.sub_district = result.sub_district or geo_rec.sub_district
                result.district     = result.district     or geo_rec.district
                result.province     = result.province     or geo_rec.province
                result.zipcode      = result.zipcode      or geo_rec.zipcode
                result.warnings.append(f"[NERFallback] Geo from: '{ner.location_hint}'")
            elif RAPIDFUZZ_AVAILABLE:
                fuzzy_rec, _, corrections, _ = self._fuzzy.fuzzy_lookup(
                    ner.location_hint,
                    zipcode_hint=result.zipcode,
                    threshold=self._fuzzy_threshold,
                    district_hint=result.district,
                    province_hint=result.province,
                )
                if fuzzy_rec:
                    result.province = result.province or fuzzy_rec.province
                    result.district = result.district or fuzzy_rec.district
                    for c in corrections:
                        result.warnings.append(f"[NER+Fuzzy] {c}")

        return result

    # ── Confidence & Validation ───────────────────────────────────────────────

    def _compute_confidence(self, result: ParseResult) -> ParseResult:
        filled = sum(1 for f in self._CONFIDENCE_FIELDS if getattr(result, f, None))
        result.confidence = round(filled / len(self._CONFIDENCE_FIELDS), 2)
        return result

    @staticmethod
    def _strict_validate(result: ParseResult) -> ParseResult:
        if result.receiver and not any(c.isalnum() for c in result.receiver):
            result.receiver = None
        if result.address_detail and not any(c.isalnum() for c in result.address_detail):
            result.address_detail = None

        receiver_val  = result.receiver or ""
        receiver_bare = re.sub(r"[^฀-๿a-zA-Z]", "", receiver_val)
        receiver_garbage = bool(receiver_val) and len(receiver_bare) < 2

        fields_filled = sum(
            1 for f in SmartAddressParser._CONFIDENCE_FIELDS
            if getattr(result, f, None)
        )

        # 1. CANNOT SHIP (Insufficient core prerequisites to dispatch a courier)
        if result.status in ("Not an Address", "Cannot ship", "Error") or fields_filled <= 1:
            result.status     = "Cannot ship"
            result.confidence = 0.0
            if "[StrictValidation] Cannot ship: insufficient data" not in result.warnings:
                result.warnings.append("[StrictValidation] Cannot ship: insufficient data")
            return result

        if not result.receiver or not result.phone:
            result.status     = "Cannot ship"
            result.confidence = min(result.confidence, 0.40)
            missing = []
            if not result.receiver: missing.append("receiver")
            if not result.phone: missing.append("phone")
            result.warnings.append(f"[StrictValidation] Cannot ship: missing {', '.join(missing)}")
            return result

        if not result.province and not result.district and not result.sub_district:
            result.status     = "Cannot ship"
            result.confidence = min(result.confidence, 0.30)
            result.warnings.append("[StrictValidation] Cannot ship: zero geographic data")
            return result

        if not result.address_detail and not result.district and not result.sub_district and not result.zipcode:
            result.status     = "Cannot ship"
            result.confidence = min(result.confidence, 0.30)
            result.warnings.append("[StrictValidation] Cannot ship: only province mentioned without district, zipcode, or address detail")
            return result

        # 2. NEEDS CONFIRMATION (Actionable partial address, missing house number, or unconfirmed auto-fills)
        needs_confirm_reasons: List[str] = []
        addr_val = result.address_detail or ""
        has_house_num = bool(
            re.search(r"\d", addr_val)
            or re.search(r"(?:คอนโด|อาคาร|ตึก|ห้อง|ชั้น|หอพัก)", addr_val)
        )
        if not result.address_detail or "ไม่มี" in addr_val or not has_house_num:
            needs_confirm_reasons.append("missing house number / address detail")
        if not result.sub_district:
            needs_confirm_reasons.append("missing sub_district")
        if not result.district:
            needs_confirm_reasons.append("missing district")
        if not result.zipcode:
            needs_confirm_reasons.append("missing zipcode")
        if receiver_garbage:
            needs_confirm_reasons.append(f"receiver '{receiver_val}' is too short")
        if (
            result.confidence < 0.90
            or any("AutoFill" in w for w in result.warnings)
        ):
            needs_confirm_reasons.append("auto-filled or partial match")
        if any("ZipMismatch" in w for w in result.warnings):
            needs_confirm_reasons.append("zipcode does not match province")
        if any("not found in geo DB" in w for w in result.warnings):
            needs_confirm_reasons.append("unknown zipcode")
        if any("MultiAddress" in w for w in result.warnings):
            needs_confirm_reasons.append("multiple addresses in message")

        if needs_confirm_reasons:
            result.status     = "Needs confirmation"
            result.confidence = min(result.confidence, 0.75) if result.confidence == 1.0 else result.confidence
            result.warnings.append("[StrictValidation] Needs confirmation: " + "; ".join(needs_confirm_reasons))
            return result

        # 3. READY (All 7 fields present, verified and consistent)
        result.status     = "Ready"
        result.confidence = 1.0
        return result

    @staticmethod
    def _elapsed(t0: float) -> float:
        return round((time.perf_counter() - t0) * 1000, 3)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════════
# DATA FLYWHEEL — HITL CORRECTION LOGGER
# ══════════════════════════════════════════════════════════════════════════════

def log_correction(
    original_text:  str,
    parsed_result:  ParseResult,
    corrected_json: dict,
    db_connection:  object,
    corrected_by:   str = "admin",
    session_id:     Optional[str] = None,
    request_id:     Optional[str] = None,
    model_version:  str = "v7.0",
) -> CorrectionRecord:
    diff_fields = [
        k for k in ParseResult.__dataclass_fields__
        if k not in ("confidence", "processing_ms", "warnings", "tags", "status")
        and getattr(parsed_result, k, None) != corrected_json.get(k)
    ]
    geo_fields = {"sub_district", "district", "province", "zipcode"}
    diff_set   = set(diff_fields)
    # FIX [#22]: Old code required ALL four geo fields to differ for "geo_only".
    # A correction that fixes only "province" was misclassified as "full",
    # polluting the training signal. New logic: any non-empty subset of geo
    # fields with no non-geo changes → "geo_only".
    correction_type = (
        "geo_only"   if diff_set and diff_set <= geo_fields
        else "name_only" if diff_fields == ["receiver"]
        else "full"
    )
    record = CorrectionRecord(
        original_text=original_text,
        parsed_output=parsed_result.to_dict(),
        corrected_output=corrected_json,
        corrected_by=corrected_by,
        correction_type=correction_type,
        session_id=session_id,
        request_id=request_id,
        model_version=model_version,
    )
    try:
        if hasattr(db_connection, "save_correction"):
            db_connection.save_correction(record)
            logger.info("Correction logged: type=%s fields=%s", correction_type, diff_fields)
        else:
            logger.warning("db_connection has no save_correction() — correction not persisted.")
    except Exception as exc:
        # FIX [#5]: Attach the error to the record so api.py's submit_feedback
        # can detect it and return HTTP 500 instead of a silent HTTP 201.
        object.__setattr__(record, "_db_error", str(exc)) if hasattr(record, "__dataclass_fields__") \
            else setattr(record, "_db_error", str(exc))
        logger.error("Failed to log correction: %s", exc, exc_info=True)
    return record


# ══════════════════════════════════════════════════════════════════════════════
# MOCK GEO DB  (for tests and local dev without the full CSV)
# ══════════════════════════════════════════════════════════════════════════════

_MOCK_CSV = """\
sub_district,district,province,zipcode
แสนสุข,เมืองชลบุรี,ชลบุรี,20130
บ้านสวน,เมืองชลบุรี,ชลบุรี,20000
หนองปลาไหล,บางละมุง,ชลบุรี,20150
หนองปรือ,บางละมุง,ชลบุรี,20150
ท่าแร้ง,บางเขน,กรุงเทพมหานคร,10220
บางเขน,บางเขน,กรุงเทพมหานคร,10220
ในเมือง,เมืองนครราชสีมา,นครราชสีมา,30000
โพธิ์กลาง,เมืองนครราชสีมา,นครราชสีมา,30000
ช้างเผือก,เมืองเชียงใหม่,เชียงใหม่,50300
ท่าศาลา,เมืองเชียงใหม่,เชียงใหม่,50000
สุเทพ,เมืองเชียงใหม่,เชียงใหม่,50200
หาดใหญ่,หาดใหญ่,สงขลา,90110
บ่อยาง,เมืองสงขลา,สงขลา,90000
บางนา,บางนา,กรุงเทพมหานคร,10260
ลาดยาว,จตุจักร,กรุงเทพมหานคร,10900
จอมพล,จตุจักร,กรุงเทพมหานคร,10900
จันทร์เกษม,จตุจักร,กรุงเทพมหานคร,10900
คลองหลวง,คลองหลวง,ปทุมธานี,12120
คลองสาม,คลองหลวง,ปทุมธานี,12120
ในเมือง,เมืองขอนแก่น,ขอนแก่น,40000
โคกสว่าง,เมืองขอนแก่น,ขอนแก่น,40000
ดอนช้าง,เมืองขอนแก่น,ขอนแก่น,40000
พระสิงห์,เมืองเชียงใหม่,เชียงใหม่,50200
ธาตุเชิงชุม,เมืองสกลนคร,สกลนคร,47000
ดงมะไฟ,เมืองสกลนคร,สกลนคร,47000
หนองไผ่ล้อม,เมืองนครราชสีมา,นครราชสีมา,30000
มะลวน,พุนพิน,สุราษฎร์ธานี,84130
นาเกลือ,พระสมุทรเจดีย์,สมุทรปราการ,10290
บางโฉลง,บางพลี,สมุทรปราการ,10540
บางพลีใหญ่,บางพลี,สมุทรปราการ,10540
ไร่สะท้อน,บ้านลาด,เพชรบุรี,76150
ท่าลาด,ชุมพวง,นครราชสีมา,30270
บางระกำ,บางระกำ,พิษณุโลก,65140
สีกัน,ดอนเมือง,กรุงเทพมหานคร,10210
ตลาด,เมืองมหาสารคาม,มหาสารคาม,44000
อนุสาวรีย์,บางเขน,กรุงเทพมหานคร,10220
ห้วยขวาง,ห้วยขวาง,กรุงเทพมหานคร,10310
คลองเตย,คลองเตย,กรุงเทพมหานคร,10110
สามเสนใน,พญาไท,กรุงเทพมหานคร,10400
หัวหมาก,บางกะปิ,กรุงเทพมหานคร,10240
ท่าทราย,เมืองนนทบุรี,นนทบุรี,11000
บางม่วง,บางใหญ่,นนทบุรี,11140
พระราชนิเวศน์,เมืองนนทบุรี,นนทบุรี,11000
"""


def build_mock_geo_db() -> GeoDatabase:
    """Build a test GeoDatabase from embedded mock CSV (covers all test cases)."""
    return GeoDatabase().load_csv_string(_MOCK_CSV)