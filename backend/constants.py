#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ThaiSmartAddress v7.0 — constants.py
All pre-compiled regexes, linguistic resources, and classification tables.

FIXES applied (original):
  [C1] Added มบ. -> หมู่บ้าน abbreviation
  [C2] Added กม.ม. -> กรุงเทพมหานคร abbreviation
  [C3] Added เลขที่อยู่ / เลขที่ to CONNECTOR_PATTERN
  [C4] Added hashtag (#) variants to CONNECTOR_PATTERN
  [C5] Extended Do_not_fold tag to catch เด็ดขาด suffix
  [C6] Lowered FUZZY_THRESHOLD 85->80
  [C7] Added expanded military rank forms to HONORIFIC_LIST

NEW FIXES applied (v7.0, earlier round):
  [FIX-C8]  Removed "นะคะ", "คะ", "ครับ" from INTENT_NEG_KEYWORDS — these are
            polite Thai particles that appear in almost all address messages.
            With digit_density = 0% (no house number) they caused the Intent
            Shield to reject valid addresses as "Not an Address".
            Only genuine shopping-intent keywords are now in the set.
  [FIX-C9]  Added "ส่งฟรีไหม", "พร้อมส่ง", "โอนให้แล้ว" as high-signal
            shopping keywords to compensate for the narrowed particle set.

NEW FIXES applied (this round — from the 2nd-round production audit):
  [FIX-C13] Added a bare "กรุงเทพ" -> "กรุงเทพมหานคร" abbreviation rule.
            Previously only "กรุงเทพฯ" (with the Thai abbreviation mark ฯ)
            and "กทม."/"กทม" were recognised. Real customer messages very
            often write plain "กรุงเทพ" with no trailing ฯ (e.g. "...เขตดินแดง
            กรุงเทพ 10400"). Because _NLA already asserts "not followed by a
            Thai/Latin character", this new rule cannot double-fire inside
            "กรุงเทพฯ" (ฯ is itself in the Thai Unicode block) or inside
            "กรุงเทพมหานคร" (next char ม is Thai) — so it's safe to add
            without touching the existing rules or their ordering.
  [FIX-C14] Broadened the Fragile tag pattern. It previously required the
            literal phrase "...ของแตก(ง่าย)?" anchored optionally after
            "ระวัง". Real messages use many synonyms that never contain the
            substring "ของแตก" at all: "ของแตกง่าย" said without ระวัง,
            "ระวังแตก" (แตก without ของ), "ห่อกันกระแทก"/"กันกระแทก",
            "เซรามิก", "fragile" (English), and "มีแก้ว"/"บรรจุแก้ว"/
            "ใส่แก้ว" style phrasing for glass contents. The bare word "แก้ว"
            is deliberately NOT matched on its own — it's an extremely common
            Thai given name/place-name component (e.g. "คุณแก้ว", "บ้านแก้ว"),
            so it's only treated as a fragile signal when preceded by a
            containment verb (มี/บรรจุ/ใส่) that a name or place name would
            never precede.
  [FIX-C15] Broadened the Urgent tag pattern to catch "เร็วที่สุด" /
            "ขอให้ถึงเร็วที่สุด" style phrasing that carries no "ด่วน" token
            at all.
  [FIX-C16] Added "ของ" to NAME_STOP_WORDS. Messages phrased as "ส่งของให้
            เอกชัยนะครับ" (lit. "send [the] stuff to Ekkachai") were leaking
            the connector "ของ" into the extracted receiver name ("ของ
            เอกชัย" instead of "เอกชัย") because "ส่ง"/"ให้"/"นะครับ" are all
            stripped by CONNECTOR_PATTERN but "ของ" was never in any
            stop-word or connector list. It's now skipped the same way
            leading-noise tokens like "แอดมิน" already are in
            _extract_receiver_and_address()'s Pass B leading-token loop.
"""
from __future__ import annotations

import re
from typing import Dict, FrozenSet, List, Tuple

THAI_BLOCK = r"[฀-๿]"

# ══════════════════════════════════════════════════════════════════════════════
# ABBREVIATION EXPANSION
# ══════════════════════════════════════════════════════════════════════════════

_NLB = r"(?<![฀-๿A-Za-z])"
_NLA = r"(?![฀-๿A-Za-z])"

ABBREV_EXPAND: List[Tuple[str, str]] = [
    # 1. Military & police ranks (must be first to expand before geo tokens)
    (rf"{_NLB}จ\.ส\.อ\.?{_NLA}", "จ่าสิบเอก"),
    (rf"{_NLB}ส\.อ\.?{_NLA}",    "สิบเอก"),
    (rf"{_NLB}ร\.ต\.ต\.?{_NLA}", "ร้อยตำรวจตรี"),
    (rf"{_NLB}พล\.ต\.ต\.?{_NLA}","พลตำรวจตรี"),
    (rf"{_NLB}พ\.ต\.ท\.?{_NLA}", "พันตำรวจโท"),
    (rf"{_NLB}พ\.ต\.อ\.?{_NLA}", "พันตำรวจเอก"),
    (rf"{_NLB}ร\.อ\.?{_NLA}",    "ร้อยเอก"),

    # 2. Province aliases
    (rf"{_NLB}กรุงเทพฯ{_NLA}",   "กรุงเทพมหานคร"),
    (rf"{_NLB}กทม\.?{_NLA}",      "กรุงเทพมหานคร"),
    (rf"{_NLB}กม\.ม\.?{_NLA}",    "กรุงเทพมหานคร"),
    # [FIX-C13]: bare "กรุงเทพ" with no trailing ฯ. Safe against
    # double-firing inside "กรุงเทพฯ" or "กรุงเทพมหานคร" because _NLA already
    # requires the next character NOT be Thai/Latin — ฯ and ม both are.
    (rf"{_NLB}กรุงเทพ{_NLA}",     "กรุงเทพมหานคร"),
    (rf"{_NLB}(?<!ต\.)(?<!ตำบล)(?<!ตำบล )โคราช{_NLA}",       "นครราชสีมา"),
    (rf"{_NLB}จ\.\s*ชม\.?{_NLA}", "จังหวัดเชียงใหม่"),
    (rf"{_NLB}จ\.\s*ขก\.?{_NLA}", "จังหวัดขอนแก่น"),
    (rf"{_NLB}จ\.\s*สข\.?{_NLA}", "จังหวัดสงขลา"),
    (rf"{_NLB}จ\.\s*นศ\.?{_NLA}", "จังหวัดนครศรีธรรมราช"),
    (rf"{_NLB}จ\.\s*นม\.?{_NLA}", "จังหวัดนครราชสีมา"),
    (rf"{_NLB}จ\.\s*ภก\.?{_NLA}", "จังหวัดภูเก็ต"),
    (rf"{_NLB}จ\.\s*อบ\.?{_NLA}", "จังหวัดอุบลราชธานี"),
    (rf"{_NLB}นครศรีฯ", "นครศรีธรรมราช"),
    (rf"{_NLB}แปดริ้ว{_NLA}",     "ฉะเชิงเทรา"),

    # 3. Geo-prefix abbreviations (after rank expansion to avoid collisions)
    (rf"{_NLB}มบ\.\s*(?={THAI_BLOCK})", "หมู่บ้าน "),
    (rf"{_NLB}จ\.\s*(?={THAI_BLOCK})(?!\s*{THAI_BLOCK}\.)",  "จังหวัด"),
    (rf"{_NLB}อ\.\s*(?={THAI_BLOCK})(?!\s*{THAI_BLOCK}\.)",  "อำเภอ"),
    (rf"{_NLB}ต\.\s*(?={THAI_BLOCK})(?!\s*{THAI_BLOCK}\.)",  "ตำบล"),
    (rf"{_NLB}ม\.\s*(?=\d)",            "หมู่ "),
    (rf"{_NLB}ซ\.\s*(?=[฀-๿A-Za-z\d])","ซอย"),
    (rf"{_NLB}ถ\.\s*(?=[฀-๿A-Za-z])",  "ถนน"),
]

_ABBREV_RE = re.compile(
    "|".join(f"(?P<a{i}>{pat})" for i, (pat, _) in enumerate(ABBREV_EXPAND)),
    re.IGNORECASE,
)
_ABBREV_REPL_MAP: Dict[str, str] = {
    f"a{i}": repl for i, (_, repl) in enumerate(ABBREV_EXPAND)
}


def abbrev_sub(m: re.Match) -> str:
    for name, repl in _ABBREV_REPL_MAP.items():
        if m.group(name) is not None:
            return repl
    return m.group(0)


def expand_abbreviations(text: str) -> str:
    return _ABBREV_RE.sub(abbrev_sub, text)


# ══════════════════════════════════════════════════════════════════════════════
# CHAT JUNK & CONNECTOR PATTERNS
# ══════════════════════════════════════════════════════════════════════════════

_CHAT_JUNK: List[str] = [
    # Greetings
    "สวัสดีค่ะ", "สวัสดีครับ", "สวัสดีคะ", "สวัสดีจ้า", "สวัสดีจ้ะ",
    "หวัดดีค่ะ", "หวัดดีครับ", "หวัดดีคะ", "หวัดดีจ้า",
    "แอดคะ", "แอดครับ", "พี่แอดคะ", "พี่แอดครับ", "แม่ค้าคะ", "แม่ค้าครับ",
    "โอนแล้วค่ะ", "โอนแล้วครับ", "โอนเงินแล้ว",
    "cf ", "ยืนยันออเดอร์", "ยืนยัน",
    "สลิปแนบด้านบนค่ะ", "สลิปแนบ", "สลิป",
    "เอา 2 ชิ้นคะ", "เอา 1 ชิ้น",
    "ออเดอร์", "order ",
    "ที่อยู่ตามบัตร", "ตามบัตร ปชช", "ตามบัตรปชช", "ปชช:",
    "รับสายยากหน่อย", "รับสายยาก",
    "ไลน์มานะ", "ไลน์มา", "ไลน์ได้เลย",
    "รบกวนแอดมินหาให้หน่อย", "รบกวนแอดมินหา",
    "จำไม่ได้จ้า", "จำไม่ได้ค่ะ", "จำไม่ได้ครับ", "จำไม่ได้",
    "หาให้หน่อยนะ", "หาให้หน่อย",
]
CHAT_JUNK_PATTERN = re.compile(
    "|".join(re.escape(j) for j in sorted(_CHAT_JUNK, key=len, reverse=True)),
    re.IGNORECASE,
)

_CONNECTORS: List[str] = [
    # Hashtag-prefixed variants — longest first
    "#ที่อยู่จัดส่ง", "#ที่อยู่",
    # Delivery labels
    "รบกวนส่งที่", "ส่งที่ที่อยู่", "ส่งที่นี้ครับ", "ส่งที่นี้นะคะ",
    "ส่งที่นี่นะคะ", "ส่งที่นี่ครับ", "ส่งที่นี่นะ", "ส่งที่นี่", "ส่งที่นี้นะ", "ส่งที่นี้",
    "จัดส่งที่", "ที่อยู่จัดส่ง",
    # House-number label prefix
    "เลขที่อยู่", "เลขที่",
    "ที่อยู่:", "ที่อยู่",
    "ส่งที่", "ส่งไปที่", "ส่งตามนี้นะคะ", "ส่งตามนี้ครับ",
    # FIX [C-F1]: Add variants with เลย/ด้วย suffixes and เอา prefix
    "ส่งตามนี้เลยค่ะ", "ส่งตามนี้เลยครับ", "ส่งตามนี้เลยนะ", "ส่งตามนี้เลย",
    "ส่งตามนี้ค่ะ", "ส่งตามนี้",
    "ส่งให้ด้วยนะคะ", "ส่งให้ด้วยครับ", "ส่งให้ด้วย", "ส่งให้",
    "เอาส่งมาที่", "เอาส่งที่", "ส่งมาที่", "ส่งมา",
    "To:", "to:", "ส่ง",
    "ครับผม", "นะครับ", "นะคะ", "นะค่ะ", "นะค้า", "นะจ้า",
    "ครับ", "ค่ะ", "คะ", "จ้า",
    "เลยนะ", "เลย",
    "ให้ด้วย", "ด้วย", "ให้",
]
_CONNECTOR_GUARD = (
    "".join(f"(?<!{w})(?<!{w} )" for w in ["ซอย", "ถนน", "หมู่บ้าน", "อาคาร"])
    + "(?<!(?<!ขอบ)คุณ)"
    + "(?:(?=(?:ครับผม|นะครับ|นะคะ|นะค่ะ|นะค้า|นะจ้า|ครับ|ค่ะ|คะ|จ้า)(?![ก-๙]))|"
    + "".join(
        f"(?<!{re.escape(w)})"
        for w in [
            "เ", "ร้าน", "บ้าน", "หอพัก", "คอนโด", "ตึก", "แฟลต", "โครงการ",
            "ห้าง", "ตลาด", "อพาร์ทเม้นท์", "วัด", "โรงแรม", "บริษัท",
            "ปั๊ม", "โรงเรียน", "โรงพยาบาล", "มหาวิทยาลัย", "สำนักงาน", "ร.พ.", "ร.ร.",
        ]
    )
    + ")"
)
CONNECTOR_PATTERN = re.compile(
    r"(?<!\S)ที่(?!\S)|"
    + _CONNECTOR_GUARD
    + rf"(?:{'|'.join(re.escape(c) for c in sorted(_CONNECTORS, key=len, reverse=True))}|(?<!ลูก)(?<!พ่อ)(?<!แม่)(?<!การ)ค้า)"
)

_GREETING_LEAD_PARTS: List[str] = [
    r"(?:สวัสดี|หวัดดี)(?:[!,\-.]|\s*(?:ครับผม|นะครับ|นะคะ|นะค่ะ|นะค้า|นะจ้า|ครับ|ค่ะ|คะ|จ้า|จ้ะ)|\s*(?=(?:แอดมิน|แอด|พี่แอด|น้องแอด|แม่ค้า|พ่อค้า|ส่ง|จัดส่ง|รบกวน|โอน)))",
    r"ดี(?:\s*(?:ครับผม|นะครับ|นะคะ|นะค่ะ|นะค้า|นะจ้า|ครับ|ค่ะ|คะ|จ้า|จ้ะ))",
    r"(?:พี่แอด(?:มิน)?|น้องแอด(?:มิน)?|แอดมิน|แอด|แม่ค้า|พ่อค้า)(?:[!,\-.:]|\s*(?:ครับผม|นะครับ|นะคะ|นะค่ะ|นะค้า|นะจ้า|ครับ|ค่ะ|คะ|จ้า|จ้ะ))?",
    r"(?:รบกวน)?(?:ช่วย)?(?:จัด)?(?:ส่งที่นี่|ส่งที่นี้|ส่งตามนี้เลย|ส่งตามนี้|จัดส่งตามนี้|จัดส่งที่|จัดส่งให้|ส่งมาที่|ส่งไปที่|ส่งที่|ส่งให้|ส่งมา)(?:[!,\-.:]|\s*(?:ครับผม|นะครับ|นะคะ|นะค่ะ|นะค้า|นะจ้า|ครับ|ค่ะ|คะ|จ้า|จ้ะ|ด้วยนะคะ|ด้วยครับ|ด้วยนะ|ด้วย|เลยค่ะ|เลยครับ|เลยนะ|เลย|นะ))?",
    r"(?:โอนแล้ว|โอนเงินแล้ว)(?:[!,\-.:]|\s*(?:ครับผม|นะครับ|นะคะ|นะค่ะ|นะค้า|นะจ้า|ครับ|ค่ะ|คะ|จ้า|จ้ะ))?",
    r"(?:รบกวน)?(?:ช่วย)?จัดส่ง(?:[!,\-.:]|\s*(?:ครับผม|นะครับ|นะคะ|นะค่ะ|นะค้า|นะจ้า|ครับ|ค่ะ|คะ|จ้า|จ้ะ))?",
    r"รบกวน(?:[!,\-.:]|\s*(?:ครับผม|นะครับ|นะคะ|นะค่ะ|นะค้า|นะจ้า|ครับ|ค่ะ|คะ|จ้า|จ้ะ|ด้วยนะคะ|ด้วยครับ|ด้วยนะ|ด้วย))?",
    r"(?:ที่นี่|ที่นี้|ตามนี้เลย|ตามนี้)(?:[!,\-.:]|\s*(?:ครับผม|นะครับ|นะคะ|นะค่ะ|นะค้า|นะจ้า|ครับ|ค่ะ|คะ|จ้า|จ้ะ))?",
]
GREETING_LEAD_PATTERN = re.compile(
    r"^(?:" + "|".join(_GREETING_LEAD_PARTS) + r")\s*",
    re.IGNORECASE,
)

# ══════════════════════════════════════════════════════════════════════════════
# HONORIFICS
# ══════════════════════════════════════════════════════════════════════════════

_HONORIFIC_LIST: List[str] = sorted([
    # Standard & abbreviations
    "นางสาว", "น.ส.", "นส.", "นส", "ด.ช.", "ด.ญ.", "ดช", "ดญ", "นาง", "นาย",
    # Academic & professional
    "ดร.", "ดร", "อาจารย์", "ผศ.", "รศ.", "ศ.", "อ.", "ครู", "หมอ",
    "นพ.", "พญ.", "ทพ.", "ภก.", "ภญ.", "ทนาย",
    "คุณ", "พี่", "น้อง", "ลุง", "น้า",
    "ป้า", "ยาย", "ปู่", "อา",
    "เฮีย", "เจ๊", "ซ้อ", "เสี่ย", "แม่", "พ่อ", "หนู",
    # English-style
    "Miss", "Mrs.", "Mr.", "Ms.", "Khun",
    "K.", "k.", "K", "k", "P'", "p'", "N'", "n'",
    # Military & police (abbreviated forms)
    "พลฯ", "จ.ส.อ.", "จ.ส.อ", "ส.อ.", "ส.อ", "จ่า",
    "ร.ต.ต.", "ร.ต.", "ร.ท.", "ร.อ.",
    "พ.ต.ต.", "พ.ต.", "พ.ท.", "พ.อ.",
    "ด.ต.", "จ.ส.ต.", "ส.ต.อ.", "ส.ต.ท.", "ส.ต.ต.",
    "หมวด", "ผู้กอง", "สารวัตร", "ผู้การ",
    # Military & police (expanded forms — post-ABBREV_EXPAND)
    "จ่าสิบเอก", "สิบเอก", "ร้อยตำรวจตรี", "พลตำรวจตรี",
    "พันตำรวจโท", "พันตำรวจเอก", "ร้อยเอก",
], key=len, reverse=True)

HONORIFIC_SKIP_SET: FrozenSet[str] = frozenset(_HONORIFIC_LIST)

HONORIFIC_PATTERN = re.compile(
    r"(?:^|(?<=\s)|(?<=ของ))("
    + "|".join(re.escape(h) for h in _HONORIFIC_LIST)
    + r")\s*(?P<n>[^\s\d]{2,})"
)

# ══════════════════════════════════════════════════════════════════════════════
# NAME STOP WORDS
# ══════════════════════════════════════════════════════════════════════════════

NAME_STOP_WORDS: FrozenSet[str] = frozenset([
    "ร้าน", "บริษัท", "บ.", "หจก", "ห้างหุ้นส่วน", "วิสาหกิจ", "โรงพยาบาล",
    "โรงแรม", "โรงเรียน", "มหาวิทยาลัย", "สถาบัน",
    "ซอย", "ถนน", "ถ.", "ซ.", "ตรอก", "หมู่บ้าน", "หมู่", "ม.", "ตึก",
    "อาคาร", "ชั้น", "ห้อง", "บ้าน", "ค่าย", "คอนโด", "แฟลต",
    "ตำบล", "แขวง", "อำเภอ", "เขต", "จังหวัด", "เลขที่อยู่", "เลขที่",
    # Staff/admin noise tokens
    "แอดมิน", "admin", "แอด", "พี่แอด", "พี่แอดมิน", "น้องแอด", "น้องแอดมิน", "แม่ค้า", "พ่อค้า",
    # [FIX-SW1] Kilometer/road markers ("ช่างเอก ริมถนนสายเอเชีย กม 45" → stop at ริม, กม)
    "กม", "กม.", "กิโลเมตร", "ริม", "ขาเข้า", "ขาออก", "ฝั่ง", "ปาก",
    # Accommodation types
    "หอพัก", "หอ", "อพาร์ทเม้นท์", "อพาร์ตเมนต์",
    # P.O. Box tokens — "ตู้ ปณ. 45" must not bleed into receiver
    "ตู้", "ปณ.", "ปณจ.", "ปณ",
    # Product and fragile tokens that must not be parsed as person names
    "กล่อง", "กล่องนี้", "กล่องแก้ว", "แก้ว", "ขวดแก้ว", "ขวดน้ำหอม", "ระวังแตก", "เซรามิก",
    "กระจก", "เครื่องแก้ว", "แจกันแก้ว", "จานกระเบื้อง", "กระเบื้อง", "ของเปราะบาง",
    "ของแตกง่าย", "ระวังของแตก", "ของไม่แตก", "แตกง่าย",
    # Urgency & action noise tokens that must not bleed into receiver name
    "ด่วน", "ด่วนมาก", "ด่วนที่สุด", "ด่วนจี๋", "รีบ", "เร็ว", "เร็วที่สุด", "ส่งด่วน",
    "ช่วย", "ช่วยส่ง", "จัดส่ง", "รบกวน", "ฝาก", "ตามรอบ", "ปกติ",
])

# FIX [C-F3]: Explicit "ชื่อผู้รับ:" / "ชื่อเล่น" label that appears anywhere in message
RECEIVER_LABEL_RE = re.compile(
    r"(?:ชื่อผู้รับ|ลูกค้าชื่อ|ชื่อลูกค้า|ผู้รับคือ|ผู้รับ|ชื่อเล่น|ชื่อจริง|ชื่อ)\s*[:\-]?\s*([^\n\r:]{2,50}?)"
    r"(?=\s*\n|\s*$|\s*รหัส|\s*โทร|\s*เบอร์|\s*บ้านเลขที่|\s*เลขที่|\s*ไม่มี|\s*หมู่|\s+บ้าน\s*\d|\s+ส่ง|\s*ส่งที่|\s*จัดส่ง|\s*ที่อยู่|\s+ที่|\s*ที่[ก-๙]+|\s+\d)",
    re.IGNORECASE,
)

# FIX [C-F4]: "รหัสไปรษณีย์" followed by non-digit Thai complaint text
ZIPCODE_COMPLAINT_RE = re.compile(
    r"รหัสไปรษณีย์\s*(?=[^\d\s])[^\n\r]*"
)

# ══════════════════════════════════════════════════════════════════════════════
# SEMANTIC KEYWORD TAGS
# ══════════════════════════════════════════════════════════════════════════════

_COURIER_VERB = r"(?:(?:ขอ\s*)?(?:ส่ง|ใช้)(?:\s*(?:ทาง|ด้วย|แบบ|เป็น))?\s*)"

_KEYWORD_TAGS: List[Tuple[str, str]] = [
    # Urgent tags
    (r"ด่วน(?:ๆ|มากๆ|มาก|ที่สุด)?",                          "Urgent"),
    (r"(?:ให้)?เร็วที่สุด",                                   "Urgent"),
    (r"รีบส่ง|รีบ(?:หน่อย|ด้วย|ส่งให้หน่อย)",                 "Urgent"),
    (r"ส่ง(?:เร็ว|ไว)(?:ๆ|มาก)?|รบกวนส่งเร็ว",                  "Urgent"),
    (r"(?:ฝาก)?ส่งวันนี้(?:นะคะ|นะค่ะ|นะครับ|ค่ะ|ครับ)?",      "Urgent"),
    (r"(?:ขอให้|ฝาก)?(?:จัด)?ส่ง(?:ให้)?(?:ภายในวัน\w+|เร็วที่สุด|ด่วน(?:มาก)?)", "Urgent"),
    (r"ขอส่งก่อนเที่ยง\w*",                                   "Urgent"),
    (r"(?:ขอ)?ส่งก่อนบ่าย\w*",                                "Urgent"),
    (r"(?:ต้อง)?ใช้(?:ด่วน)?(?:ในงาน)?(?:ภายในวัน\w+|พรุ่งนี้|วัน\w+)?", "Urgent"),
    (r"ต้องการใช้พรุ่งนี้",                                    "Urgent"),
    (r"ขอให้ถึง(?:ก่อนวัน\w+|เร็วที่สุด|ภายใน\w+)",            "Urgent"),
    (r"ขอให้ถึงก่อน\w+",                                      "Urgent"),
    (r"ของขวัญต้องถึงภายใน\w+",                                "Urgent"),
    (r"รีบใช้พรุ่งนี้",                                        "Urgent"),
    (r"วันนี้ต้องใช้|ต้องใช้วันนี้",                           "Urgent"),

    # Fragile tags
    (r"ระวัง(?:หน่อย(?:นะ(?:ครับ|คะ))?)?ของแตก(?:ง่าย)?",   "Fragile"),
    (r"ระวัง(?:ของ)?แตก",                                     "Fragile"),
    (r"กล่องแก้ว|กล่องมีแก้ว|มีแก้ว",                         "Fragile"),
    (r"(?:ของ)?(?:มี)?(?:จาน|ชาม|แก้ว|ขวด|เซรามิก|เครื่องแก้ว|สิ่งของ|สินค้า)?\s*แตกง่าย", "Fragile"),
    (r"ของแตกง่าย|แตกง่าย",                                   "Fragile"),
    (r"ระวังแตก",                                              "Fragile"),
    (r"(?:ขอ)?(?:ห่อ)?(?:กันกระแทก|บับเบิล)",                 "Fragile"),
    (r"เซรามิก",                                               "Fragile"),
    (r"(?i)fragile",                                           "Fragile"),
    (r"เปราะบาง",                                              "Fragile"),
    (r"เครื่องแก้ว",                                           "Fragile"),
    (r"ขวดแก้ว",                                               "Fragile"),
    (r"แก้วไวน์|แก้วกาแฟ|แจกันแก้ว",                           "Fragile"),
    (r"จานกระเบื้อง|กระเบื้อง",                                "Fragile"),
    (r"กระจก",                                                 "Fragile"),
    (r"ขวดน้ำหอม",                                             "Fragile"),
    (r"(?:มี|บรรจุ|ใส่|เป็น)(?:แจกัน)?แก้ว(?:ไวน์|กาแฟ)?",     "Fragile"),
    (r"(?:มี|บรรจุ|ใส่|เป็น)ขวดแก้ว",                          "Fragile"),

    # Guard / fold / dry tags
    (r"(?:ฝาก(?:ไว้)?(?:ที่)?)?(?:ป้อมยาม|ป้อมหน้า|ป้อมประตู|รปภ\.?|security)",  "Drop_at_guard"),
    (r"(?:ห้าม|อย่า)พับ(?:\s*เด็ดขาด)?",                     "Do_not_fold"),
    (r"(?:ห้าม|อย่า)เปียก",                                   "Keep_dry"),
    (r"(?i)(?<!ไม่ต้อง\s)(?<!ไม่ต้อง)(?<!ไม่\s)(?<!ไม่)(?:(?:เก็บ|ชำระ|จ่าย)(?:เงิน)?ปลายทาง|\bcod\b)", "COD"),

    # Courier tags
    (r"(?i)(?:" + _COURIER_VERB + r")?(?:(?<![a-z])kerry(?![a-z])|เคอรี่)", "Courier_Kerry"),
    (r"(?i)(?:(?:" + _COURIER_VERB + r")?(?:(?<![a-z])flash\s*express(?![a-z])|แฟลช)|" + _COURIER_VERB + r"(?<![a-z])flash(?![a-z]))", "Courier_Flash"),
    (r"(?i)(?:" + _COURIER_VERB + r")?(?:(?<![a-z])j&t(?:\s*express)?(?![a-z])|เจแอนด์ที)", "Courier_JT"),
    (r"(?i)(?:" + _COURIER_VERB + r")?(?:(?<![a-z])ems(?![a-z])|อีเอ็มเอส)", "Courier_EMS"),
    (r"(?i)" + _COURIER_VERB + r"ไปรษณีย์(?:\s*(?:ไทย|ธรรมดา|ลงทะเบียน))?", "Courier_ThaiPost"),
]
TAG_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(pat), tag) for pat, tag in _KEYWORD_TAGS
]

_COURIER_PATS = [pat.replace("(?i)", "") for pat, tag in _KEYWORD_TAGS if tag.startswith("Courier_")]
COURIER_STRIP_RE = re.compile(
    r"(?i)(?:(?:" + "|".join(_COURIER_PATS) + r")(?:\s*(?:นะคะ|นะค่ะ|นะครับ|ค่ะ|คะ|ครับ|จ้า|ค้า|ด้วยนะ|ด้วย|นะ))*)"
)

# ══════════════════════════════════════════════════════════════════════════════
# PHONE & ZIPCODE PATTERNS
# ══════════════════════════════════════════════════════════════════════════════

PHONE_RE = re.compile(
    r"(?:(?<!\d)|(?<=(?<!\d)\d{5}))"
    r"("
    r"(?:\+66|66)[\s\-\./]?[6-9]\d[\s\-\./]?(?:\d{3}[\s\-\./]?\d{4}|\d{4}[\s\-\./]?\d{3})"
    r"|(?:\+66|66)[\s\-\./]?[6-9][\s\-\./]?\d{4}[\s\-\./]?\d{4}"
    r"|(?:\+66|66)[\s\-\./]?[6-9]\d{2}[\s\-\./]?\d{3}[\s\-\./]?\d{3}"
    r"|(?:\+66|66)[\s\-\./]?[6-9]\d{8}"
    r"|0[6-9]\d[\s\-\./]?(?:\d{3}[\s\-\./]?\d{4}|\d{4}[\s\-\./]?\d{3})"
    r"|0[6-9][\s\-\./]?\d{4}[\s\-\./]?\d{4}"
    r"|0[6-9]\d{2}[\s\-\./]?\d{3}[\s\-\./]?\d{3}"
    r"|0[6-9]\d{8}"
    r"|(?:\+66|66)[\s\-\./]?[2-5]\d[\s\-\./]?\d{3}[\s\-\./]?\d{3,4}(?!\d)"
    r"|0[2-5]\d[\s\-\./]?\d{3}[\s\-\./]?\d{3,4}(?!\d)"
    r"|0[2-5][\s\-\./]?\d{3,4}[\s\-\./]?\d{3,4}(?!\d)"
    r")"
)

ZIPCODE_RE = re.compile(r"(?<!\d)\d{5}(?!\d)")

# ══════════════════════════════════════════════════════════════════════════════
# ADDRESS DETAIL ANCHOR
# ══════════════════════════════════════════════════════════════════════════════

ADDRESS_DETAIL_RE = re.compile(
    r"(?:"
    r"(?:^|(?<![฀-๿A-Za-z]))(?:หมู่บ้าน|ซอย|ซ\.|ถนน|ถ\.|ตรอก|อาคาร|ตึก|คอนโด|หอพัก|แฟลต|อพาร์ทเม้นท์|อพาร์ตเมนต์|ห้อง|ชั้น|โครงการ|ตู้\s*ปณ\.?|ร้าน[ก-๙]{2,})[^\n]{2,120}"
    r"|"
    r"\d+(?:/\d+)?"
    r"(?:\s*(?:หมู่\s*\d+|ม\.\s*\d+))?"
    r"(?:\s*[^\n]{0,120})?"
    r")"
)

# ══════════════════════════════════════════════════════════════════════════════
# INTENT SHIELD  (Phase -1)
#
# FIX [FIX-C8]: Removed "นะคะ", "คะ", "ครับ", "นะครับ" from this set.
#   Rationale: these are polite Thai sentence-ending particles that appear in
#   virtually every real address message. With digit_density = 0 (addresses
#   containing only district / province, no house number) the old code would
#   silently reject them as "Not an Address".
#   Only HIGH-SIGNAL shopping keywords that cannot plausibly appear in a
#   delivery address are kept in this set.
#
# FIX [FIX-C9]: Added "ส่งฟรีไหม", "พร้อมส่ง", "โอนให้แล้ว" as additional
#   high-signal shopping-intent keywords.
# ══════════════════════════════════════════════════════════════════════════════

INTENT_NEG_KEYWORDS: FrozenSet[str] = frozenset([
    # Pricing enquiries
    "ราคา", "เท่าไหร่", "เท่าไร", "ราคาเท่า", "กี่บาท",
    # Size / stock enquiries
    "ไซส์", "ไซต์", "size",
    # Discount / free shipping enquiries
    "ลดได้", "ลดให้", "ส่งฟรี", "ค่าส่ง", "จัดส่งฟรี", "ส่งฟรีไหม",
    # Stock / product enquiries
    "มีสต็อก", "มีของ", "หมดแล้ว", "สินค้า", "พร้อมส่ง",
    # Order-placement phrases (NOT delivery addresses)
    "สั่งได้", "สั่งเลย",
    # Payment confirmations WITHOUT an accompanying address
    "โอนแล้ว", "ยอดโอน", "โอนให้แล้ว",
    # Conversational missing address references
    "ที่อยู่เดิม", "เบอร์เดิม", "ส่งที่เดิม", "เหมือนเดิม", "ตามเดิม", "ที่เดิม",
    # [FIX-C10]: Short acknowledgements — "ขอบคุณค่ะ" has no address content.
    # Safe: valid addresses that open with ขอบคุณ always carry a 5-digit zipcode
    # or phone number, so they bypass the shield via the ZIPCODE_RE/PHONE_RE check.
    "ขอบคุณ",
    # [FIX-C11]: Product-variant enquiries — "มีสีอื่นไหมครับ" etc.
    "มีสีอื่น", "สีอื่น",
    # [FIX-C12]: Temporal/operational enquiries — "เปิดกี่โมง", "ปิดกี่โมง" etc.
    # Safe: no delivery address ever contains "กี่โมง".
    "กี่โมง",
    # Tracking and delivery-status enquiries
    "เลขพัสดุ", "tracking", "ส่งถึงยัง", "ติดตาม",
    # NOTE: "นะคะ", "คะ", "ครับ", "นะครับ" intentionally REMOVED [FIX-C8]
])


# ══════════════════════════════════════════════════════════════════════════════
# FUZZY MATCHING THRESHOLDS
# ══════════════════════════════════════════════════════════════════════════════

FUZZY_THRESHOLD: int = 80
FUZZY_MAX_LEN_DIFF: int = 4
NER_FALLBACK_THRESHOLD: float = 0.60
