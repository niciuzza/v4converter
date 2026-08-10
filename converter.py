"""
JSON Converter: Old Section Format → New Component-Based Format
Usage:
    python converter.py <input.json> [output.json]
    If output.json is omitted, result is printed to stdout.
"""

import difflib
import functools
import json
import os
import re
import sys


# ---------------------------------------------------------------------------
# Backend version + changelog (single source of truth)
#
# This is the converter *engine* version — bump it when conversion behavior
# changes (new section support, mapping fixes, HTML rules), NOT for cosmetic
# changes to the browser tool (converter2v4.html). The browser tool reads
# these constants out of the loaded module to render its "what's new" popup,
# so the log stays tied to what the converter can actually do.
# ---------------------------------------------------------------------------

__version__ = "1.16"
LAST_UPDATED = "2026-08-10"

# Short summary of what the converter handles — shown in the browser popup.
# Plain strings; inline HTML (e.g. <code>) is allowed for rendering there.
CAPABILITIES = [
    "แปลงโค้ด JSON หน้าร้าน LNW Shop จาก <code>v3</code> เป็น <code>v4</code>",
    "ตรวจชนิดข้อมูลอัตโนมัติ: section เดี่ยว, ทั้งเว็บ (<code>site</code>), zone, หรือ global component",
    "รองรับครบ 17 content section + Header/Footer zone + Global component",
    "จัดระเบียบ HTML ในเนื้อหาอัตโนมัติ (ปิด tag เช่น <code>&lt;br&gt;</code>) และเตือนเมื่อพบ tag ที่ไม่ได้ปิด",
]

# Backend changelog, newest first. Add an entry + bump __version__ whenever
# conversion behavior changes.
CHANGELOG = [
    {"version": "1.16", "date": "2026-08-10", "items": [
        "FeatureSection: feature ที่มี <code>mediaType: \"video\"</code> อย่างน้อย 1 อัน ตั้ง <code>variant: \"full-image\"</code> แทน <code>\"fit-image\"</code> และไม่ใส่ <code>mediaRatio</code> เลยถ้าไม่มี <code>isCropImage</code> ระบุมา (เดิมใส่ <code>\"fit-image\"</code>/<code>mediaRatio: \"auto\"</code> เสมอไม่ว่าจะเป็น video หรือ image)",
    ]},
    {"version": "1.15", "date": "2026-08-10", "items": [
        "ProductSection: <code>layoutType</code>/<code>isUseSlick</code> ที่ v3 ไม่ได้ระบุมา ตอนนี้ infer จากข้อมูลจริง (มี <code>bannerImage</code>/<code>bannerImageMobile</code> → ถือเป็น <code>bannerImage</code>, มี <code>hasArrows</code>/<code>hasDots</code>/<code>productSlidesToShow</code> → ถือเป็น slick) — เดิม preset เก่าที่ไม่ส่ง field พวกนี้มา explicit จะถูกทิ้งเงียบ ๆ ทั้งที่มีข้อมูล banner/slick ครบ",
        "ProductSection: ไม่ใส่ <code>WidgetHeading</code> เปล่าอีกต่อไปเมื่อ title/description ว่างทั้งคู่",
        "ProductSection: <code>productNumber</code>/<code>productSlidesToShow</code>/<code>slidesToScroll</code>/<code>slideAutoplaySpeed</code>/<code>slideSpeed</code> แปลงเป็น int แล้ว (เดิม v3 บางครั้งเก็บเป็น string เช่น <code>\"6\"</code> แล้ว pass-through ตรง ๆ)",
        "ProductSection: layout <code>bannerImage</code> + slick ตั้ง <code>span</code> ให้คอลัมน์ banner/product แล้ว (<code>lg:4/xs:12</code> และ <code>lg:8/xs:12</code>) — เดิมปล่อยว่างไม่มี responsive sizing เลย",
    ]},
    {"version": "1.14", "date": "2026-08-05", "items": [
        "Headline/FeatureSection/ParagraphSection/TopicSection/SlideShowSection/ProductSection/ProductTab/BlogSection: อ่าน padding บน/ล่างจาก <code>className2</code> (utility class แบบ Bootstrap เช่น <code>pt-0 pb-3 pb-xl-5</code>) แล้วครบทุก section ที่มี field นี้ — เดิมไม่แปลงเลย ค่าจาก <code>sectionStyle.padding</code> ที่ตั้งจริงยังชนะเหมือนเดิม เติมเฉพาะจุดที่ไม่ได้ตั้ง",
        "Headline/FeatureSection/SlideShowSection: แก้ padding ที่เป็น <code>null</code> ใน <code>sectionStyle.padding</code> ไม่ให้ถูกตีความเป็น 0px อีกต่อไป (เดิมเข้าใจผิดว่า field มีอยู่ = ตั้งค่าจริง)",
        "Headline: layout <code>imageAlignBg</code> + 2 คอลัมน์ (ครึ่งนึงเป็นรูปพื้นหลังเต็ม) ย้าย padding ไปไว้ที่คอลัมน์เนื้อหาแทน section (section เป็น 0 ทั้งหมด) ไม่งั้นรูปจะไม่เต็มขอบ",
        "className2: แก้ให้ class ที่ไม่ระบุ breakpoint (เช่น <code>pt-0</code>) กำหนดค่าให้ครบ xs และ lg ตาม cascade จริงของ CSS แทนที่จะใส่แค่ xs ตัวเดียว (เดิมพลาดที่ค่า <code>pt-0</code> ไม่ครอบคลุมถึงจอใหญ่) — md ใส่เฉพาะตอนมี class เจาะจง <code>-md-</code> จริงเท่านั้น ไม่ synthesize ให้ เพราะ md ไม่ใช่ breakpoint default ใน v4",
        "FeatureSection: ไม่ใส่ <code>WidgetHeading</code> เปล่าอีกต่อไปเมื่อ v3 ไม่ได้ตั้ง title/description เลย (เดิมใส่มาเสมอแม้ไม่มีเนื้อหา)",
    ]},
    {"version": "1.13", "date": "2026-08-04", "items": [
        "ProductSection: <code>layoutType: \"bannerImage\"</code> ที่ไม่ใช่ slick (แบนเนอร์ซ้าย/ขวา + สินค้า) ตอนนี้ใส่ปุ่ม <code>button</code>/<code>buttonLink</code> ด้วยแล้ว — เดิมหายไปเงียบ ๆ",
    ]},
    {"version": "1.12", "date": "2026-07-13", "items": [
        "รองรับ <code>CustomHtmlSection</code> แล้ว (เดิมข้าม) — สร้าง section ที่มี <code>WidgetCustomHtml</code> ว่าง (<code>renderMode: inline</code>) + ตั้ง nickname จาก title",
        "เตือนทุกครั้งที่พบ Custom HTML ว่า <b>ต้องนำโค้ด HTML เดิมไปวางเองใน manage ของร้าน</b> (v4 เก็บ custom HTML แยกจากโครงหน้า — converter ไม่ฝัง HTML ให้)",
    ]},
    {"version": "1.11", "date": "2026-07-09", "items": [
        "FeatureSection: เมื่อ <code>isCropImage: false</code> จะตั้ง <code>mediaRatio: \"auto\"</code> (ให้รูปคงอัตราส่วนเดิม) แทนการปล่อยว่าง; <code>true</code> ยังครอปเป็น <code>1 / 1</code> เหมือนเดิม",
    ]},
    {"version": "1.10", "date": "2026-07-01", "items": [
        "ปิด quote ของ attribute ที่เปิดค้าง (เช่น <code>&lt;a href='http://x&gt;…</code>) — เติม quote ปิดก่อน <code>&gt;</code> ไม่ให้ browser กลืนเนื้อหาหลัง tag",
    ]},
    {"version": "1.9", "date": "2026-06-29", "items": [
        "tag ที่ซ้อนปิดผิดลำดับ (<code>&lt;b&gt;&lt;i&gt;x&lt;/b&gt;</code>) แก้อัตโนมัติแล้ว — ปิด tag ตัวในก่อน (<code>&lt;b&gt;&lt;i&gt;x&lt;/i&gt;&lt;/b&gt;</code>) แทนการเตือนเฉย ๆ",
    ]},
    {"version": "1.8", "date": "2026-06-29", "items": [
        "จัดระเบียบ HTML ละเอียดขึ้น: รวม void ที่มี close tag (<code>&lt;img&gt;&lt;/img&gt;</code> → <code>&lt;img&gt;</code>)",
        "ลบ close tag ที่ไม่มีคู่เปิด (เช่น <code>&lt;/span&gt;</code> ลอย ๆ)",
        "แก้ self-closed ของ tag ที่ไม่ใช่ void (<code>&lt;div/&gt;</code> → <code>&lt;div&gt;</code>)",
        "แปลง smart quote ใน tag เป็น quote ตรง, ตัด <br> หัว/ท้าย, ลบ tag ว่าง (<code>&lt;p&gt;&lt;/p&gt;</code>)",
        "ล้างขยะจากการวางจาก MS Word (<code>&lt;o:p&gt;</code>, MsoNormal, mso-*)",
        "เตือนเมื่อ nesting ซ้อนผิดลำดับ (<code>&lt;b&gt;&lt;i&gt;…&lt;/b&gt;&lt;/i&gt;</code>) แทนที่จะใส่ tag ปิดเกิน",
    ]},
    {"version": "1.7", "date": "2026-06-25", "items": [
        "เติม <code>:root</code> ให้ครบ: คำนวณเฉดสีแบรนด์/รอง/กลาง 5 ระดับจากสีที่ตั้งไว้",
        "จัดให้ <code>:root</code> อยู่บนสุดของ <code>style</code> เสมอ และเรียงชื่อสีตามตัวอักษร",
        "ค่าที่ตรงกับ v4-base อยู่แล้วจะไม่ใส่ซ้ำ — เก็บเฉพาะค่าที่ override จริง (สี status ใช้ค่า v4)",
        "เลือกได้ว่าจะสร้างเฉดสีอัตโนมัติหรือไม่ (toggle “สร้างเฉดสีอัตโนมัติ” ในหน้าเครื่องมือ)",
        "ไม่ใส่ฟอนต์ที่เป็นค่าว่าง (เช่น <code>typoHeadingFontFamily: []</code>) ใน global setting",
        "ดึง typography ฐานราย theme (ขนาด/น้ำหนัก/line-height) ตาม <code>currentTheme</code> เฉพาะค่าที่ต่างจาก base",
    ]},
    {"version": "1.6", "date": "2026-06-24", "items": [
        "เลือกได้ว่าจะรวมส่วนไหนในผลลัพธ์: เนื้อหา / สีธีม / ฟอนต์ธีม / ตั้งค่ารวม (จำค่าไว้ในเบราว์เซอร์)",
    ]},
    {"version": "1.5", "date": "2026-06-24", "items": [
        "แปลง theme config: <code>currentColors</code> → สีแบรนด์ใน <code>:root</code>, <code>currentFonts</code> → ฟอนต์",
        "ฟอนต์นอกระบบ (Google font) จะถูกตัดออกพร้อมแจ้งเตือน — เพิ่มเองใน v4",
    ]},
    {"version": "1.4", "date": "2026-06-24", "items": [
        "เลิกปิด <code>&lt;img&gt;</code> เป็น <code>&lt;img/&gt;</code> — ใช้รูปแบบ HTML5 ปกติ",
    ]},
    {"version": "1.3", "date": "2026-06-23", "items": [
        "รองรับ Global component (info / style / free_zone)",
        "จัดระเบียบ HTML อัตโนมัติ: ปิด void tag (<code>&lt;br&gt;</code>, <code>&lt;hr&gt;</code>) และเตือน tag ที่ไม่ได้ปิด",
    ]},
    {"version": "1.2", "date": "2026-06-15", "items": [
        "รองรับ Header section ครบ (sticky, mega menu, drawer, โหมดโปร่งใส)",
        "จัดการ system page (404, blog, promotion) + สงวน path ระบบของ v4",
    ]},
    {"version": "1.1", "date": "2026-06-08", "items": [
        "รองรับ Footer zone และ Header zone",
    ]},
    {"version": "1.0", "date": "2026-05-29", "items": [
        "ตัวแปลง v3 → v4 เวอร์ชันเสถียรแรก — รองรับ section และแปลงทั้งหน้า/ทั้งเว็บ",
    ]},
]

# ---------------------------------------------------------------------------
# htmlfix.html — standalone v4 HTML fixer. It shares the normalize_html engine
# but is a separate tool, so it carries its OWN version + changelog (kept apart
# from converter2v4's __version__/CHANGELOG above). htmlfix.html reads these.
# ---------------------------------------------------------------------------

HTMLFIX_VERSION = "1.3"
HTMLFIX_LAST_UPDATED = "2026-07-01"

HTMLFIX_CHANGELOG = [
    {"version": "1.3", "date": "2026-07-01", "items": [
        "ปิด quote ของ attribute ที่เปิดค้าง (เช่น <code>&lt;a href='http://x&gt;aaa&lt;/a&gt;</code>) — เติม quote ปิดก่อน <code>&gt;</code> แทนที่จะปล่อยให้ browser กลืน <code>&gt;aaa&lt;/a&gt;</code> เข้าไปในค่า",
    ]},
    {"version": "1.2", "date": "2026-06-29", "items": [
        "tag ซ้อนปิดผิดลำดับ แก้อัตโนมัติแล้ว (ปิดตัวในก่อน) — เลิกเตือนเฉย ๆ",
        "กล่องผลลัพธ์แก้มือได้ + ตรวจซ้ำสด ๆ ว่ายังมีจุดต้องแก้ไหม",
        "ค้นหาในกล่อง (⌕ / Ctrl-F, ▴▾ ก่อนหน้า/ถัดไป), ย่อระดับบนสุด (⊟) / ขยายทั้งหมด (⊞)",
        "แถบไฮไลต์จุดที่แก้ข้าง scrollbar — คลิกกระโดด + กางส่วนที่ย่อให้",
        "ปุ่มคัดลอก: ถ้าแก้มือจะ “ตรวจและคัดลอก” (รัน fix ซ้ำ + apply กลับกล่องก่อน), ขนาดปุ่มไม่เด้ง",
        "รายการที่แก้: ตัด JSON path ออก แสดงบรรทัด + รายละเอียดแทน",
    ]},
    {"version": "1.101", "date": "2026-06-29", "items": [
        "แก้บั๊ก: ไม่ตัด key ที่มีค่า <code>null</code> ออกอีกต่อไป — ผลลัพธ์คงโครงสร้าง JSON เดิมครบทุก key",
    ]},
    {"version": "1.1", "date": "2026-06-29", "items": [
        "รวม void ที่มี close tag (<code>&lt;img&gt;&lt;/img&gt;</code> → <code>&lt;img&gt;</code>, <code>&lt;br&gt;&lt;/br&gt;</code> → <code>&lt;br/&gt;</code>)",
        "ลบ close tag ที่ไม่มีคู่เปิด (เช่น <code>&lt;/span&gt;</code> ลอย ๆ)",
        "แก้ self-closed ของ tag ที่ไม่ใช่ void (<code>&lt;div/&gt;</code> → <code>&lt;div&gt;</code>)",
        "แปลง smart quote ใน tag เป็น quote ตรง, ตัด <br> หัว/ท้าย, ลบ tag ว่าง (<code>&lt;p&gt;&lt;/p&gt;</code>)",
        "ล้างขยะจากการวางจาก MS Word (<code>&lt;o:p&gt;</code>, MsoNormal, mso-*)",
        "เตือนเมื่อ nesting ซ้อนผิดลำดับ แทนที่จะใส่ tag ปิดเกิน",
    ]},
    {"version": "1.0", "date": "2026-06-24", "items": [
        "เครื่องมือแก้ HTML ใน v4 JSON เวอร์ชันแรก — แยกออกจาก converter2v4",
        "ปิด void tag อัตโนมัติ (<code>&lt;br&gt;</code>, <code>&lt;hr&gt;</code>) + เตือน tag ที่ไม่ได้ปิด",
    ]},
]


# ---------------------------------------------------------------------------
# HTML normalization (auto-fix void tags + detect unclosed tags)
#
# Some v3 widget content fields hold HTML written by hand. v4 renders this as
# XHTML-style markup, so non-self-closing void tags (`<br>`, `<hr>`, …) and
# unclosed regular tags break rendering. This pass walks the v3 input
# recursively, auto-fixes void tags, and reports unclosed/mismatched tags as
# warnings.
#
# `<img>` is left as-is — HTML5 does not require self-closing void syntax for
# img, and most v4 rich-text renderers accept plain `<img src="...">`.
# ---------------------------------------------------------------------------

_VOID_TAGS = {"br", "hr", "img", "input", "area", "base", "col", "embed",
              "link", "meta", "param", "source", "track", "wbr"}

# Void tags that get the XHTML self-close fix (`<br>` → `<br/>`).
# `img` is intentionally excluded — see note above.
_FIXABLE_VOID_TAGS = _VOID_TAGS - {"img"}

# Open tags like `<br>`, `<br />`, case-insensitive. (img excluded)
_VOID_OPEN_RE = re.compile(
    r"<(" + "|".join(_FIXABLE_VOID_TAGS) + r")(\b[^>]*?)\s*(/?)>",
    re.IGNORECASE,
)
# Invalid closing tag for a fixable void element, e.g. `</br>`, `</hr>`.
_VOID_CLOSE_RE = re.compile(
    r"</\s*(" + "|".join(_FIXABLE_VOID_TAGS) + r")\s*>",
    re.IGNORECASE,
)
# Generic opening/closing tag for unclosed-tag detection.
_TAG_RE = re.compile(r"<(/?)([A-Za-z][\w-]*)(\b[^>]*?)(/?)>")
# Newline + surrounding spaces between two HTML tags — safely removable.
_INTER_TAG_NEWLINE_RE = re.compile(r">[ \t]*\n+[ \t]*<")
# Embedded <style>...</style> / <script>...</script> blocks (warn only).
_STYLE_SCRIPT_RE = re.compile(r"<(style|script)\b", re.IGNORECASE)

# Smart/curly quotes → straight (applied INSIDE tags only — curly quotes in
# visible prose are legitimate and must be left alone).
_SMART_QUOTE_MAP = {"“": '"', "”": '"', "‘": "'", "’": "'"}
_TAG_SPAN_RE = re.compile(r"<[^>]*>")

# A void element written with an explicit close tag: `<img ...></img>`,
# `<br></br>`. Collapsed to a single void element so the open/close void rules
# below don't double it (img stays non-self-closed per the convention above).
_VOID_PAIR_RE = re.compile(
    r"<(" + "|".join(_VOID_TAGS) + r")(\b[^>]*?)\s*/?>\s*</\s*\1\s*>",
    re.IGNORECASE,
)

# A non-void element self-closed XHTML-style: `<div/>`, `<span/>`. Browsers
# treat these as an *open* tag, so we strip the slash and let the nesting pass
# append the close.
_SELF_CLOSE_RE = re.compile(r"<([A-Za-z][\w-]*)(\b[^>]*?)\s*/>")

# Empty text elements safe to drop (open immediately followed by its close with
# only whitespace between). Restricted to a safelist so structural tags like
# <td>/<li>/<tr> are never collapsed. `&nbsp;` counts as content (kept).
_EMPTY_TAG_SAFELIST = ["p", "div", "span", "strong", "em", "b", "i", "u",
                       "s", "small", "blockquote",
                       "h1", "h2", "h3", "h4", "h5", "h6"]
_EMPTY_TAG_RE = re.compile(
    r"<(" + "|".join(_EMPTY_TAG_SAFELIST) + r")(\b[^>]*?)>\s*</\s*\1\s*>",
    re.IGNORECASE,
)

# Leading / trailing <br> (and surrounding whitespace) at a field boundary.
_EDGE_BR_LEAD_RE = re.compile(r"^(?:\s*<br\s*/?>\s*)+", re.IGNORECASE)
_EDGE_BR_TRAIL_RE = re.compile(r"(?:\s*<br\s*/?>\s*)+$", re.IGNORECASE)

# MS Word paste artifacts.
_WORD_CONDITIONAL_RE = re.compile(
    r"<!--\[if[^\]]*\]>.*?<!\[endif\]-->", re.IGNORECASE | re.DOTALL)
_WORD_CONDITIONAL_STRAY_RE = re.compile(r"<!\[(?:end)?if[^\]]*\]>", re.IGNORECASE)
_WORD_OFFICE_TAG_RE = re.compile(r"</?o:[a-z0-9]+\b[^>]*>", re.IGNORECASE)
_WORD_MSO_STYLE_DECL_RE = re.compile(r"\s*mso-[^:;\"']+:[^;\"']*;?", re.IGNORECASE)
_WORD_MSO_CLASS_RE = re.compile(r"\bMso[A-Za-z0-9]+\b")
# A class="" / style="" / style="  " attribute left empty after stripping.
_EMPTY_ATTR_RE = re.compile(r"""\s+(?:class|style)\s*=\s*(["'])\s*\1""")

# Paths (or path prefixes) whose values are NOT carried over to v4 — we skip
# HTML warnings for them since fixing or warning has no effect on the output.
_DROPPED_PATH_PATTERNS = [
    re.compile(r"^\$\.footer\.FooterSection\.addressText$"),
    re.compile(r"^\$\.components\.MainView(\.|$)"),
    re.compile(r"^\$\.components\.VerifyBadgeWidget(\.|$)"),
    re.compile(r"^\$\.components\.CartMini(\.|$)"),
    re.compile(r"^\$\.components\.ContactWidget\.iconChatButtonStyle\.hoverStyle(\.|$)"),
    re.compile(r"^\$\.components\.ContactWidget\.iconCloseButtonStyle(\.|$)"),
    re.compile(r"^\$\.components\.ContactWidget\.contactMobileDisable$"),
    re.compile(r"^\$\.components\.ContactWidget\.contactEmailDisable$"),
]


def _is_dropped_path(path: str) -> bool:
    """True if `path` (or any ancestor) is dropped by the v3→v4 converter."""
    return any(p.match(path) for p in _DROPPED_PATH_PATTERNS)


def _fix_void_tags(s: str) -> tuple:
    """Return (fixed_string, list_of_fixed_tag_names).
    Auto-closes fixable void open tags (`<br>` → `<br/>`) and rewrites
    invalid closing void tags (`</br>` → `<br/>`). `img` is not touched.
    """
    fixed = []
    def repl_open(m):
        tag   = m.group(1).lower()
        attrs = m.group(2) or ""
        slash = m.group(3)
        if slash == "/":
            return m.group(0)  # already self-closing
        fixed.append(tag)
        return f"<{tag}{attrs}/>"
    out = _VOID_OPEN_RE.sub(repl_open, s)

    def repl_close(m):
        tag = m.group(1).lower()
        fixed.append(tag)
        return f"<{tag}/>"
    out = _VOID_CLOSE_RE.sub(repl_close, out)
    return out, fixed


def _strip_inter_tag_newlines(s: str):
    """Remove `\\n` (and surrounding spaces) that sit between two tags.
    Returns (new_string, count_removed).
    """
    count = 0
    def repl(_m):
        nonlocal count
        count += 1
        return "><"
    out = _INTER_TAG_NEWLINE_RE.sub(repl, s)
    return out, count


def _trim_edge_newlines(s: str):
    """Strip leading/trailing whitespace that includes a newline.
    Returns (new_string, did_trim).
    """
    if not s:
        return s, False
    stripped = s.strip()
    # Only flag as a fix if we actually removed newlines (not just spaces),
    # so plain " hello " doesn't get reported.
    if stripped == s:
        return s, False
    had_newline = ("\n" in s[:len(s) - len(s.lstrip())]
                   or "\n" in s[len(s.rstrip()):])
    return stripped, had_newline


def _fix_smart_quotes_in_tags(s: str):
    """Replace curly quotes (“ ” ‘ ’) with straight quotes INSIDE tags only.
    Returns (new_string, count_replaced). Curly quotes in visible text are
    intentionally left untouched.
    """
    count = 0
    def repl(m):
        nonlocal count
        tag = m.group(0)
        for ch, straight in _SMART_QUOTE_MAP.items():
            if ch in tag:
                count += tag.count(ch)
                tag = tag.replace(ch, straight)
        return tag
    out = _TAG_SPAN_RE.sub(repl, s)
    return out, count


# An attribute value opened with a quote but never closed before the tag's '>'
# (e.g. <a href='http://x>text</a>). A browser then swallows everything after the
# '>' into the value, so the link text / following markup disappears. Anchored on
# a tag start so it won't touch quotes/`>` in visible text; the value run excludes
# quotes and angle brackets, so a properly-closed attribute never matches.
_UNCLOSED_ATTR_RE = re.compile(r"""(<[a-zA-Z][a-zA-Z0-9]*[^<>]*?=\s*)(['"])([^'"<>]*)>""")


def _fix_unclosed_attr_quotes(s: str):
    """Close an attribute value opened with a quote but not closed before the tag's
    '>', inserting the matching quote just before the '>'. Returns (new, count)."""
    count = 0
    def repl(m):
        nonlocal count
        count += 1
        q = m.group(2)
        return f"{m.group(1)}{q}{m.group(3)}{q}>"
    out = _UNCLOSED_ATTR_RE.sub(repl, s)
    return out, count


def _collapse_void_pairs(s: str):
    """Collapse a void element written with a close tag — `<img ...></img>`,
    `<br></br>` — into a single void element. Returns (new_string, tags).
    img stays non-self-closed (`<img ...>`); others self-close (`<br/>`).
    """
    collapsed = []
    def repl(m):
        tag   = m.group(1).lower()
        attrs = m.group(2) or ""
        collapsed.append(tag)
        if tag == "img":
            return f"<{tag}{attrs}>"
        return f"<{tag}{attrs}/>"
    out = _VOID_PAIR_RE.sub(repl, s)
    return out, collapsed


def _expand_self_closed_nonvoid(s: str):
    """Strip the slash from XHTML-style self-closed NON-void tags (`<div/>` →
    `<div>`), matching browser parsing. Void tags are left as-is. Returns
    (new_string, tags).
    """
    expanded = []
    def repl(m):
        tag   = m.group(1).lower()
        attrs = m.group(2) or ""
        if tag in _VOID_TAGS:
            return m.group(0)
        expanded.append(tag)
        return f"<{tag}{attrs}>"
    out = _SELF_CLOSE_RE.sub(repl, s)
    return out, expanded


def _remove_empty_tags(s: str):
    """Remove empty text tags (`<p></p>`) from the safelist, iterating so nested
    empties collapse. `&nbsp;`-only is kept (counts as content). Returns
    (new_string, tags).
    """
    removed = []
    out = s
    while True:
        m = _EMPTY_TAG_RE.search(out)
        if not m:
            break
        removed.append(m.group(1).lower())
        out = out[:m.start()] + out[m.end():]
    return out, removed


def _strip_edge_breaks(s: str):
    """Remove leading/trailing `<br>`/`<br/>` (and surrounding whitespace) at a
    field boundary. Returns (new_string, did_strip).
    """
    out = _EDGE_BR_LEAD_RE.sub("", s)
    out = _EDGE_BR_TRAIL_RE.sub("", out)
    return out, (out != s)


def _strip_word_artifacts(s: str):
    """Remove MS Word paste cruft. Returns (new_string, list_of_msgs)."""
    msgs = []
    out = s
    out, n = _WORD_CONDITIONAL_RE.subn("", out)
    if n:
        msgs.append(f"Removed {n} Word conditional comment(s)")
    out, n = _WORD_CONDITIONAL_STRAY_RE.subn("", out)
    if n:
        msgs.append(f"Removed {n} stray Word conditional marker(s)")
    out, n = _WORD_OFFICE_TAG_RE.subn("", out)
    if n:
        msgs.append(f"Removed {n} Office namespace tag(s)")
    out, n = _WORD_MSO_STYLE_DECL_RE.subn("", out)
    if n:
        msgs.append(f"Removed {n} mso-* style declaration(s)")
    out, n = _WORD_MSO_CLASS_RE.subn("", out)
    if n:
        msgs.append(f"Removed {n} Mso* class(es)")
    # Drop class=""/style="" attributes left empty by the strips above.
    out = _EMPTY_ATTR_RE.sub("", out)
    return out, msgs


def _resolve_nesting(s: str):
    """Walk non-void tags and fix structural problems. Returns
    (new_string, fixed_msgs, warn_msgs):
      - orphan close tags (no matching open anywhere) are REMOVED from the string
      - crossed nesting (`<b><i>x</b>` or `<b><i>x</b></i>`) is auto-fixed by
        closing the still-open inner tags BEFORE the out-of-order close — i.e.
        `<b><i>x</b>` → `<b><i>x</i></b>` — matching how browsers and HTML
        sanitizers normalize it (close innermost first). A later redundant close
        for an already-closed inner tag then drops out as an orphan.
      - genuinely-unclosed tags get their close appended at the end
    `warn_msgs` is kept in the return signature for the caller but nesting no
    longer emits warnings (everything resolvable is now auto-fixed).
    """
    fixed: list = []
    warns: list = []
    stack: list = []
    parts: list = []  # rebuilt string (insert inner closes, drop orphans)
    last = 0
    for m in _TAG_RE.finditer(s):
        is_close   = m.group(1) == "/"
        tag        = m.group(2).lower()
        self_close = m.group(4) == "/"
        if tag in _VOID_TAGS or self_close:
            continue
        if not is_close:
            stack.append(tag)
            continue
        # closing tag
        if stack and stack[-1] == tag:
            stack.pop()
        elif tag in stack:
            # crossed nesting — auto-close the inner tags opened after `tag`,
            # innermost first, right before this close tag.
            idx = len(stack) - 1
            while idx >= 0 and stack[idx] != tag:
                idx -= 1
            inner = stack[idx + 1:]                 # tags above `tag`, outer→inner
            parts.append(s[last:m.start()])
            parts.append("".join(f"</{t}>" for t in reversed(inner)))
            last = m.start()                        # keep the original </tag>
            del stack[idx:]                         # pop inner tags + tag
            for t in reversed(inner):
                fixed.append(f"Auto-closed <{t}> before </{tag}>")
        else:
            # orphan close — remove it from the string
            parts.append(s[last:m.start()])
            last = m.end()
            fixed.append(f"Removed orphan </{tag}>")
    parts.append(s[last:])
    out = "".join(parts)
    if stack:
        out += "".join(f"</{t}>" for t in reversed(stack))
        for t in reversed(stack):
            fixed.append(f"Auto-appended </{t}> at end")
    return out, fixed, warns


def normalize_html(data, path: str = "$"):
    """Walk v3 input recursively. Apply HTML hygiene to string values that
    look like HTML (contain `<` and `>`):
      - strip MS Word paste artifacts (<o:p>, MsoNormal, conditional comments, mso-*)
      - straighten curly quotes inside tags (“ → ")
      - close an attribute value opened with a quote but not closed before '>'
        (`<a href='http://x>` → `<a href='http://x'>`)
      - trim leading/trailing whitespace that includes a newline
      - strip `\\n` (and surrounding spaces) between two tags
      - collapse void-with-close pairs: `<img></img>` → `<img>`, `<br></br>` → `<br/>`
      - strip leading/trailing `<br>`
      - auto-close void tags (except img): `<br>` → `<br/>`; fix `</br>` → `<br/>`
      - expand self-closed non-void tags: `<div/>` → `<div>`
      - remove empty text tags: `<p></p>`
      - remove orphan close tags; warn on crossed nesting
      - auto-close genuinely-unclosed non-void tags
      - warn on embedded <style>/<script>
    Returns (new_data, warnings). Does not mutate the input.
    Warning shape: {path, kind: "fixed"|"warn", msg}.
    """
    warnings: list = []
    new_data = _walk_html(data, path, warnings)
    return new_data, warnings


def _walk_html(v, path: str, warnings: list):
    if isinstance(v, dict):
        return {k: _walk_html(val, f"{path}.{k}", warnings) for k, val in v.items()}
    if isinstance(v, list):
        return [_walk_html(val, f"{path}[{i}]", warnings) for i, val in enumerate(v)]
    # Skip paths that are dropped by the v3→v4 converter (no effect on output).
    if _is_dropped_path(path):
        return v
    if isinstance(v, str) and "<" in v and ">" in v:
        out = v

        def fix(msg):
            warnings.append({"path": path, "kind": "fixed", "msg": msg})

        # 1. Strip MS Word paste artifacts.
        out, word_msgs = _strip_word_artifacts(out)
        for msg in word_msgs:
            fix(msg)

        # 2. Straighten curly quotes inside tags.
        out, n_sq = _fix_smart_quotes_in_tags(out)
        if n_sq:
            fix(f"Straightened {n_sq} curly quote(s) in tag(s)")

        # 2b. Close attribute values opened with a quote but not closed before '>'.
        out, n_uq = _fix_unclosed_attr_quotes(out)
        if n_uq:
            fix(f"Closed {n_uq} unclosed attribute quote(s) in tag(s)")

        # 3. Trim leading/trailing newlines.
        out, did_edge_trim = _trim_edge_newlines(out)
        if did_edge_trim:
            fix("Trimmed leading/trailing newline")

        # 4. Strip \n between tags.
        out, n_inter = _strip_inter_tag_newlines(out)
        if n_inter:
            fix(f"Removed {n_inter} newline(s) between tags")

        # 5. Collapse void elements written with a close tag (<img></img>).
        out, collapsed = _collapse_void_pairs(out)
        for tag in collapsed:
            fix(f"Collapsed <{tag}></{tag}> → single <{tag}>")

        # 6. Strip leading/trailing <br> (before void-fix, so a bare <br> at the
        #    edge is removed once, not auto-closed then removed).
        out, did_edge_br = _strip_edge_breaks(out)
        if did_edge_br:
            fix("Removed leading/trailing <br>")

        # 7. Auto-fix void open + invalid close tags.
        out, fixed_tags = _fix_void_tags(out)
        for tag in fixed_tags:
            fix(f"Auto-closed <{tag}> → <{tag}/>")

        # 8. Expand self-closed non-void tags (<div/> → <div>).
        out, expanded = _expand_self_closed_nonvoid(out)
        for tag in expanded:
            fix(f"Expanded self-closed <{tag}/> → <{tag}>")

        # 9. Remove empty text tags (<p></p>).
        out, emptied = _remove_empty_tags(out)
        for tag in emptied:
            fix(f"Removed empty <{tag}></{tag}>")

        # 10. Warn on <style>/<script>.
        for m in _STYLE_SCRIPT_RE.finditer(out):
            warnings.append({"path": path, "kind": "warn",
                             "msg": f"<{m.group(1).lower()}> embedded in content"})

        # 11. Resolve nesting: remove orphan closes, warn on crossed nesting,
        #     auto-close genuinely-unclosed tags.
        out, nest_fixed, nest_warns = _resolve_nesting(out)
        for msg in nest_fixed:
            fix(msg)
        for msg in nest_warns:
            warnings.append({"path": path, "kind": "warn", "msg": msg})
        return out
    return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_size(value) -> dict:
    """Convert '120px' → {value:120, unit:'px'}, '5vw' → {value:5, unit:'vw'}, None → 0px."""
    if value is None:
        return {"value": 0, "unit": "px"}
    s = str(value).strip()
    for unit in ("px", "vw", "vh", "%", "rem", "em"):
        if s.endswith(unit):
            try:
                num = float(s[: -len(unit)])
                return {"value": int(num) if num == int(num) else num, "unit": unit}
            except ValueError:
                pass
    try:
        return {"value": int(float(s)), "unit": "px"}
    except ValueError:
        return {"value": 0, "unit": "px"}


# v3's own Bootstrap-like section-padding utility classes, found in `className`/
# `className2` (e.g. "pt-0 pb-3 pb-xl-5"). Scale/breakpoints read from
# `v3/Global.css` (user-supplied, 2026-08-05): `.pt-N .container { padding-top:
# Nrem !important; }` for N 0-10, identical scale repeated verbatim under each
# breakpoint's media query (no root font-size override found -> 1rem = 16px).
# Breakpoints: unprefixed/`sm` -> xs, `md` -> min-width:750px, `xl` ->
# min-width:1200px -> lg -- same rename convention used everywhere else in this
# converter. Only top/bottom exist in this utility system (no margin, no
# left/right) -- `t`/`b`/`y` are the only sides ever seen across all 32 demos.
_CLASSNAME2_PADDING_RE = re.compile(r"^p([tby])(?:-(sm|md|xl))?-(\d+)$")
_CLASSNAME2_BP = {None: "xs", "sm": "xs", "md": "md", "xl": "lg"}


def parse_classname2_padding(class2) -> tuple:
    """Parse a v3 `className2`-style utility string into (paddingTop, paddingBottom)
    breakpoint dicts. These are real CSS min-width classes (mobile-first cascade: an
    unprefixed class has no media query at all, so it applies at every width; `-md-`
    (>=750px) also applies at `lg` unless an `-xl-` token overrides it there), unlike
    sectionStyle.padding elsewhere in this file (a discrete per-breakpoint v3 field,
    no cascade to replicate -- only set breakpoints are written there).

    `xs` and `lg` are v4's real cascading breakpoints, so both are resolved explicitly
    -- `lg` takes the most specific token available (xl > md > unprefixed) even when
    that token isn't itself an `-xl-` one (confirmed by the user, 2026-08-06: a `pt-0`
    with no breakpoint infix must apply at every width, not just `xs`). `md` is NOT a
    default/cascading breakpoint in v4 (confirmed by the user, 2026-08-06) -- it is
    only ever written when className2 has a LITERAL `-md-` token for that side; it is
    never synthesized from a cascade the way `lg` is.

    Non-padding/unrecognized tokens (custom CSS hooks like "about_section") are
    ignored."""
    steps = {"t": {}, "b": {}}
    for tok in (class2 or "").split():
        m = _CLASSNAME2_PADDING_RE.match(tok)
        if not m:
            continue
        side, bp_raw, step = m.group(1), m.group(2), int(m.group(3))
        bp = _CLASSNAME2_BP[bp_raw]
        sides = ("t", "b") if side == "y" else (side,)
        for s in sides:
            steps[s][bp] = step

    pt, pb = {}, {}
    for s, out in (("t", pt), ("b", pb)):
        bp_steps = steps[s]
        if not bp_steps:
            continue
        if "xs" in bp_steps:
            out["xs"] = {"value": bp_steps["xs"] * 16, "unit": "px"}
        if "md" in bp_steps:
            out["md"] = {"value": bp_steps["md"] * 16, "unit": "px"}
        resolved = None
        for bp in ("xs", "md", "lg"):
            if bp in bp_steps:
                resolved = bp_steps[bp]
        if resolved is not None:
            out["lg"] = {"value": resolved * 16, "unit": "px"}
    return pt, pb


def merge_classname2_padding(pt: dict, pb: dict, class2) -> tuple:
    """Layer `className2`'s utility-class padding UNDER explicit `sectionStyle.padding`
    (`pt`/`pb`, already breakpoint-keyed) -- v3 renders an explicit padding value as
    inline style, which wins over the `!important` utility class at that exact
    breakpoint+side (confirmed by the user, 2026-08-05); className2 only fills in
    breakpoints/sides the explicit padding leaves unset."""
    c2_pt, c2_pb = parse_classname2_padding(class2)
    return {**c2_pt, **pt}, {**c2_pb, **pb}


def convert_bg_position(position_str: str) -> str:
    """
    Convert CSS background-position from old 'y x' to new 'x y' format.
    Only swaps when the first word is a vertical keyword (top/bottom).
    'bottom center' → 'center bottom'
    'top center'    → 'center top'
    'left center'   → 'left center'  (already x-first, no swap needed)
    'center center' → 'center'
    'center'        → 'center'
    """
    if not position_str:
        return "center"
    parts = position_str.strip().split()
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        if parts[0] == parts[1] == "center":
            return "center"
        if parts[0] in ("top", "bottom"):
            return f"{parts[1]} {parts[0]}"
        return position_str
    return position_str


def convert_text_align(content_style: dict) -> dict:
    """
    Normalize two old forms of text alignment into new breakpoint format.

    Form 1 — global string:
        contentStyle.textAlign: "center"
        → { xs: "center", lg: "center" }

    Form 2 — breakpoint object:
        contentStyle.align: { sm: "center", xl: "left", md: "center" }
        → { xs: "center", lg: "left", md: "center" }

    Returns {} when no alignment is set — caller decides whether to omit.
    Breakpoint rename: sm → xs,  xl → lg,  md → md
    """
    if not content_style:
        return {}
    global_align = content_style.get("textAlign")
    if global_align:
        return {"xs": global_align, "lg": global_align}
    align_obj = content_style.get("align", {}) or {}
    bp_map = {"sm": "xs", "xl": "lg", "md": "md"}
    result = {}
    for old_bp, new_bp in bp_map.items():
        if old_bp in align_obj:
            result[new_bp] = align_obj[old_bp]
    return result


def make_node(node_type: str, kind, nickname, info: dict, children=None) -> dict:
    """Build a standard new-format node. id and ukey are auto-generated by the target system."""
    node = {
        "type": node_type,
        "kind": kind,
        "nickname": nickname,
        "hide": False,
        "info": info,
        "style": {},
        "css": None,
        "_LANG_": {},
    }
    if children is not None:
        node["children"] = children
    return node


# ---------------------------------------------------------------------------
# Widget builders
# ---------------------------------------------------------------------------

def build_widget_brand_info(props: dict) -> dict:
    """
    WidgetBrandInfo — from props.logo + props.logoStyle.
    isShowTitle and isShowDescription are always false.
    textAlign and mediaWidth are only set when the corresponding logoStyle values exist.
    """
    logo_style = props.get("logoStyle") or {}
    align      = logo_style.get("align") or {}
    size       = logo_style.get("size") or {}

    info = {
        "isShowTitle": False,
        "isShowDescription": False,
    }

    # Only add textAlign when alignment values are explicitly set
    text_align = {}
    if "sm" in align:
        text_align["xs"] = align["sm"]
    if "xl" in align:
        text_align["lg"] = align["xl"]
    if text_align:
        info["textAlign"] = text_align

    # Only add mediaWidth when size is explicitly set
    sm_width = (size.get("sm") or {}).get("width")
    if sm_width:
        info["mediaWidth"] = {"xs": parse_size(sm_width)}

    return make_node("widget", "WidgetBrandInfo", None, info)


def build_widget_heading(props: dict) -> dict:
    """
    WidgetHeading — title + description always embedded here.
    Only outputs alignment breakpoints that are explicitly set.
    isTitleHtml / isDescriptionHtml are dropped (not used in new format).
    """
    title_style = props.get("titleStyle") or {}
    desc_style  = props.get("descriptionStyle") or {}
    title_align = title_style.get("align") or {}

    # Only output breakpoints that are explicitly set
    alignment = {}
    if "sm" in title_align:
        alignment["xs"] = title_align["sm"]
    if "xl" in title_align:
        alignment["lg"] = title_align["xl"]

    title_obj = {"text": props.get("title", "")}
    if props.get("isTitleH1"):
        title_obj["as"] = "h1"
    title_color = title_style.get("fontColor")
    if title_color:
        title_obj["color"] = title_color.lower()

    info = {"title": title_obj}
    if alignment:
        info["alignment"] = alignment

    description = props.get("description")
    if description:
        desc_obj = {"text": description}
        desc_color = desc_style.get("fontColor")
        if desc_color:
            desc_obj["color"] = desc_color.lower()
        info["description"] = desc_obj

    return make_node("widget", "WidgetHeading", None, info)


def _parse_html_paragraphs(html: str) -> list:
    """Strip HTML from a description string and return a list of plain-text paragraphs.
    Splits on block-level tags (<br>, </p>, </div>), strips remaining tags, filters empties."""
    text = re.sub(r'<(?:br\s*/?|/p|/div)[^>]*>', '\n', html, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    return [p.strip() for p in text.split('\n') if p.strip()]


def build_widget_bullet_list(block: dict) -> dict:
    """WidgetBulletList — from contentBlocks with contentType: 'bullets'.
    layout is always 'list'. fontColor applied to every bullet item."""
    content_style = block.get("contentStyle") or {}
    font_color    = content_style.get("fontColor", "")
    font_color    = font_color.lower() if font_color else None

    bullet_lists = []
    for item in block.get("contentBullets", []):
        desc = {"text": item}
        if font_color:
            desc["color"] = font_color
        bullet_lists.append({"description": desc})

    return make_node("widget", "WidgetBulletList", None, {
        "bulletLists": bullet_lists,
        "layout": "list",
    })


def build_widget_media_for_imagealignbg_col(props: dict) -> dict:
    """WidgetMedia for the imageAlignBg image column — full version with mediaType, mediaWidth, widgetAlignSelf."""
    image_style = props.get("imageStyle") or {}
    align       = image_style.get("align") or {}
    size        = image_style.get("size") or {}

    image_obj  = {"src": props.get("image", "")}
    mobile_src = props.get("imageMobile")
    if mobile_src:
        image_obj["mobileSrc"] = mobile_src

    info = {"mediaType": "image", "image": image_obj}

    media_width = {}
    sm_w = (size.get("sm") or {}).get("width")
    xl_w = (size.get("xl") or {}).get("width")
    if sm_w:
        media_width["xs"] = parse_size(sm_w)
    if xl_w:
        media_width["lg"] = parse_size(xl_w)
    if media_width:
        info["mediaWidth"] = media_width

    widget_align = {}
    if "sm" in align:
        widget_align["xs"] = align["sm"]
    if "xl" in align:
        widget_align["lg"] = align["xl"]
    if widget_align:
        info["widgetAlignSelf"] = widget_align

    return make_node("widget", "WidgetMedia", None, info)


def build_widget_media_for_simple_col(props: dict) -> dict:
    """WidgetMedia for the simple 2-col image column — just src and optional mobileSrc."""
    image_obj  = {"src": props.get("image", "")}
    mobile_src = props.get("imageMobile")
    if mobile_src:
        image_obj["mobileSrc"] = mobile_src
    return make_node("widget", "WidgetMedia", None, {"image": image_obj})


def build_widget_button(props: dict):
    """
    Button widget selection:
      button is null/empty               → None (no widget)
      buttonType: 'join'                 → WidgetJoin (buttonStyle ignored)
      buttonType: 'register'|'login'|None → WidgetButtonGroup
    buttonTarget maps to buttons[0].target when present.
    """
    button = props.get("button")
    if not button:
        return None

    if props.get("buttonType") == "join":
        return make_node("widget", "WidgetJoin", None, {})

    button_style = props.get("buttonStyle") or {}
    align        = button_style.get("align") or {}

    btn_obj = {
        "title": button,
        "variant": "primary",
        "to": props.get("buttonLink", "/"),
    }
    target = props.get("buttonTarget")
    if target:
        btn_obj["target"] = target

    info = {
        "buttons": [btn_obj],
        "widgetAlignSelf": {"xs": align.get("sm", "left")},
    }
    return make_node("widget", "WidgetButtonGroup", None, info)


# ---------------------------------------------------------------------------
# Shared widget list builder
# ---------------------------------------------------------------------------

def build_content_widgets(props: dict) -> list:
    """Build the ordered widget list for any content column.

    Consecutive paragraph/image contentBlocks collapse into one WidgetTextStack.
    Bullet blocks flush the current group and emit as WidgetBulletList (Option B).
    When isDescriptionHtml has 2+ paragraphs, they prepend the first TextStack group
    and the heading description is suppressed.
    """
    widgets = []

    # Resolve description: HTML with 2+ paragraphs goes to TextStack; 1 paragraph → plain text heading
    prepend_items = []
    heading_props = props
    if props.get("isDescriptionHtml"):
        raw_desc = props.get("description") or ""
        html_paras = _parse_html_paragraphs(raw_desc)
        if len(html_paras) >= 2:
            prepend_items = [{"itemType": "text", "text": {"text": p}} for p in html_paras]
            heading_props = {**props, "description": None}
        elif len(html_paras) == 1:
            heading_props = {**props, "description": html_paras[0]}
        else:
            heading_props = {**props, "description": None}

    if props.get("logo"):
        widgets.append(build_widget_brand_info(props))
    if props.get("title"):
        widgets.append(build_widget_heading(heading_props))

    buffer = []
    first_group = [True]

    def flush():
        extra = list(prepend_items) if first_group[0] else []
        first_group[0] = False
        prepend_items.clear()
        if not buffer and not extra:
            return

        items = list(extra)
        alignment = {}
        for block in buffer:
            ct = block.get("contentType")
            if ct == "paragraph":
                text_obj = {"text": block.get("contentParagraph", "")}
                cs = block.get("contentStyle") or {}
                color = cs.get("fontColor")
                if color:
                    text_obj["color"] = color.lower()
                items.append({"itemType": "text", "text": text_obj})
                if not alignment:
                    alignment = convert_text_align(cs)
            elif ct == "image":
                ci = block.get("contentImage") or {}
                img = {"src": ci.get("image", "")}
                alt = ci.get("imageAlt")
                if alt:
                    img["alt"] = alt
                items.append({"itemType": "image", "image": img})
        buffer.clear()

        info = {"items": items}
        if alignment:
            info["alignment"] = alignment
        widgets.append(make_node("widget", "WidgetTextStack", None, info))

    for block in props.get("contentBlocks") or []:
        ct = block.get("contentType")
        if ct in ("paragraph", "image"):
            buffer.append(block)
        elif ct == "bullets":
            flush()
            widgets.append(build_widget_bullet_list(block))

    flush()

    btn = build_widget_button(props)
    if btn:
        widgets.append(btn)

    return widgets


# ---------------------------------------------------------------------------
# Column builders
# ---------------------------------------------------------------------------

# --- imageAlignBg layout columns ---

def build_content_col_imagealignbg(props: dict, image_align: str) -> dict:
    """Content col for imageAlignBg layout: span + optional mobile order."""
    col_info = {"span": {"xs": 12, "lg": 6}}
    if image_align != "imageRight":
        col_info["order"] = {"xs": 2}
    return make_node("col", None, None, col_info, build_content_widgets(props))


def build_image_col_imagealignbg(props: dict, image_align: str) -> dict:
    """Image col for imageAlignBg layout: bg from imageAlignConfig + optional mobile order."""
    image_align_config = props.get("imageAlignConfig") or {}

    col_info = {
        "span": {"xs": 12, "lg": 6},
        "bgColor": image_align_config.get("color", ""),
        "bgType": "image",
        "bgImage": {"src": props.get("backgroundImage", "")},
    }
    # Only write bg display props when explicitly set in imageAlignConfig
    if image_align_config.get("position"):
        pos = convert_bg_position(image_align_config["position"])
        col_info["bgPosition"] = {"xs": pos, "lg": pos}
    if image_align_config.get("size"):
        col_info["bgSize"] = {"xs": image_align_config["size"], "lg": image_align_config["size"]}
    if image_align_config.get("position") or image_align_config.get("size"):
        col_info["bgRepeat"] = "no-repeat"

    if image_align != "imageRight":
        col_info["order"] = {"xs": 1}

    widgets = []
    if props.get("image"):
        widgets.append(build_widget_media_for_imagealignbg_col(props))
    return make_node("col", None, None, col_info, widgets)


# --- Simple 2-col layout columns (column:2 + imageAlign, no bgMediaType) ---

def build_content_col_simple(props: dict) -> dict:
    """Content col for simple 2-col layout: only span, no extra padding."""
    col_info = {"span": {"xs": 12, "lg": 6}}
    return make_node("col", None, None, col_info, build_content_widgets(props))


def build_image_col_simple(props: dict) -> dict:
    """Image col for simple 2-col layout: empty info, simple WidgetMedia."""
    widgets = []
    if props.get("image"):
        widgets.append(build_widget_media_for_simple_col(props))
    return make_node("col", None, None, {}, widgets)


# --- Single col layout ---

def build_single_col(props: dict) -> dict:
    """Single full-width content column."""
    return make_node("col", None, None, {}, build_content_widgets(props))


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------

def build_row(props: dict) -> dict:
    num_columns   = props.get("column", 1)
    bg_media_type = props.get("bgMediaType") or "none"
    image_align   = props.get("imageAlign") or ""   # treat "" as falsy

    is_image_align_bg = bg_media_type == "imageAlignBg"
    is_two_col        = num_columns == 2

    if is_image_align_bg:
        # backgroundImage as col bg; imageAlign tells which side
        content_col = build_content_col_imagealignbg(props, image_align)
        image_col   = build_image_col_imagealignbg(props, image_align)
        cols = [content_col, image_col] if image_align == "imageRight" else [image_col, content_col]

    elif is_two_col:
        # Simple 2-col: props.image in a plain col
        # imageAlign: "imageRight" → content left, image right
        # imageAlign: "" / null   → image left, content right
        content_col = build_content_col_simple(props)
        image_col   = build_image_col_simple(props)
        cols = [content_col, image_col] if image_align == "imageRight" else [image_col, content_col]

    else:
        cols = [build_single_col(props)]

    return make_node("row", None, None, {}, cols)


# ---------------------------------------------------------------------------
# Section builder: ParagraphSection → TextStack
# ---------------------------------------------------------------------------

def build_paragraph_section(props: dict) -> dict:
    section_style = props.get("sectionStyle") or {}
    padding       = section_style.get("padding") or {}
    sm_pad        = padding.get("sm") or {}
    xl_pad        = padding.get("xl") or {}

    section_info = {}

    # --- Background ---
    bg_color = section_style.get("bgColor")
    if bg_color:
        section_info["bgColor"] = bg_color.lower()

    bg_image = section_style.get("bgImage")
    if bg_image:
        section_info["bgImage"]  = {"src": bg_image}
        section_info["bgType"]   = "image"
        # Only include position/size/repeat when bgImage exists
        bg_position = section_style.get("bgPosition")
        if bg_position:
            pos = convert_bg_position(bg_position)
            section_info["bgPosition"] = {"lg": pos, "xs": pos}
        bg_repeat = section_style.get("bgRepeat")
        if bg_repeat:
            section_info["bgRepeat"] = bg_repeat
        bg_size = section_style.get("bgSize")
        if bg_size:
            section_info["bgSize"] = {"lg": bg_size, "xs": bg_size}

    # --- Fullwidth ---
    if props.get("isFullScreen"):
        section_info["isFullwidth"] = True

    # --- Padding (always from sectionStyle.padding, no special-casing) ---
    # Null values are skipped entirely — only set breakpoints that have a real value.
    pt, pb = {}, {}
    if sm_pad.get("top")    is not None: pt["xs"] = parse_size(sm_pad["top"])
    if xl_pad.get("top")    is not None: pt["lg"] = parse_size(xl_pad["top"])
    if sm_pad.get("bottom") is not None: pb["xs"] = parse_size(sm_pad["bottom"])
    if xl_pad.get("bottom") is not None: pb["lg"] = parse_size(xl_pad["bottom"])
    pt, pb = merge_classname2_padding(pt, pb, props.get("className2"))
    if pt: section_info["paddingTop"]    = pt
    if pb: section_info["paddingBottom"] = pb

    return make_node(
        "section", "TextStack",
        props.get("presetName", ""),
        section_info,
        [build_row(props)]
    )


# ---------------------------------------------------------------------------
# Section builder: Headline → Standard
# ---------------------------------------------------------------------------

def _headline_brand_info(props: dict) -> dict:
    logo_style = props.get("logoStyle") or {}
    if isinstance(logo_style, list):
        logo_style = {}

    align = logo_style.get("align") or {}
    size  = logo_style.get("size") or {}
    xl_size = (size.get("xl") or {})

    info = {"isShowTitle": False, "isShowDescription": False}

    xl_h = xl_size.get("height")
    if xl_h:
        info["mediaHeight"] = {"lg": parse_size(xl_h)}

    xl_w = xl_size.get("width")
    if xl_w:
        info["mediaWidth"] = {"lg": parse_size(xl_w)}

    if "xl" in align:
        info["textAlign"] = {"lg": align["xl"]}

    return make_node("widget", "WidgetBrandInfo", None, info)


def _headline_heading(props: dict) -> dict:
    title_style = props.get("titleStyle") or {}
    desc_style  = props.get("descriptionStyle") or {}

    title_obj = {"text": props.get("title", "")}
    title_color = title_style.get("fontColor")
    if title_color:
        title_obj["color"] = title_color.lower()

    info = {"title": title_obj}

    desc = props.get("description")
    if desc:
        desc_obj = {"text": desc}
        desc_color = desc_style.get("fontColor")
        if desc_color:
            desc_obj["color"] = desc_color.lower()
        info["description"] = desc_obj

    # titleAs from isTitleH2 — stored as top-level field, not inside title
    if props.get("isTitleH2"):
        info["titleAs"] = "h2"

    title_align = title_style.get("align") or {}
    alignment = {}
    if "sm" in title_align:
        alignment["xs"] = title_align["sm"]
    if "xl" in title_align:
        alignment["lg"] = title_align["xl"]
    if not alignment and props.get("bgMediaType") == "imageBg" and props.get("isBgParallax"):
        # "Dark Parallax Background"-style preset (isBgParallax:true) always renders
        # centered text -- confirmed on TWO themes (x_elite, x_mixednuts) with zero
        # CSS grounding in either theme's own stylesheet, so this is a v3-CMS preset
        # default, not a theme quirk -- safe to generalize here rather than treat as
        # a per-theme demo-only force. Only applies when titleStyle.align isn't
        # already explicitly set (2026-08-06).
        alignment = {"xs": "center", "lg": "center"}
    if alignment:
        info["alignment"] = alignment

    return make_node("widget", "WidgetHeading", None, info)


def _headline_media_image(props: dict) -> dict:
    image_style = props.get("imageStyle") or {}
    align = image_style.get("align") or {}
    size  = image_style.get("size") or {}

    image_obj = {"src": props.get("image", "")}
    if props.get("imageMobile"):
        image_obj["mobileSrc"] = props["imageMobile"]
    if props.get("imageAlt"):
        image_obj["alt"] = props["imageAlt"]

    info = {"mediaType": "image", "image": image_obj}

    media_width = {}
    for bp_old, bp_new in (("xl", "lg"), ("md", "md")):
        w = (size.get(bp_old) or {}).get("width")
        if w:
            media_width[bp_new] = parse_size(w)
    if media_width:
        info["mediaWidth"] = media_width

    media_height = {}
    xl_h = (size.get("xl") or {}).get("height")
    if xl_h:
        media_height["lg"] = parse_size(xl_h)
    if media_height:
        info["mediaHeight"] = media_height

    widget_align = {}
    for bp_old, bp_new in (("xl", "lg"), ("md", "md")):
        if bp_old in align:
            widget_align[bp_new] = align[bp_old]
    if widget_align:
        info["widgetAlignSelf"] = widget_align

    if props.get("isImageParallax"):
        info["effects"] = [{
            "duration":  {"value": 0.5, "unit": "s"},
            "delay":     {"value": 0,   "unit": "s"},
            "delayStep": {"value": 0.1, "unit": "s"},
            "trigger":   "parallax",
        }]

    return make_node("widget", "WidgetMedia", None, info)


def _headline_media_video(props: dict) -> dict:
    return make_node("widget", "WidgetMedia", None, {
        "mediaType": "video",
        "video": {"src": props.get("video", "")},
    })


def _headline_button(props: dict):
    button = props.get("button")
    if not button:
        return None

    button_style = props.get("buttonStyle") or {}
    align        = button_style.get("align") or {}
    hover        = button_style.get("hoverStyle") or {}

    btn_obj = {"title": button}
    if props.get("buttonLink"):
        btn_obj["to"] = props["buttonLink"]
    if props.get("buttonTarget"):
        btn_obj["target"] = props["buttonTarget"]

    # Button style colors
    if button_style.get("bgColor"):
        btn_obj["buttonFillColor"] = button_style["bgColor"].lower()
    if button_style.get("fontColor"):
        btn_obj["buttonTextColor"] = button_style["fontColor"].lower()
    if hover.get("bgColor"):
        btn_obj["buttonHoverFillColor"] = hover["bgColor"].lower()
    if hover.get("fontColor"):
        btn_obj["buttonHoverTextColor"] = hover["fontColor"].lower()

    info = {"buttons": [btn_obj]}

    widget_align = {}
    if "sm" in align:
        widget_align["xs"] = align["sm"]
    if "xl" in align:
        widget_align["lg"] = align["xl"]
    if widget_align:
        info["widgetAlignSelf"] = widget_align

    return make_node("widget", "WidgetButtonGroup", None, info)


def _headline_content_widgets(props: dict, include_media: bool = True) -> list:
    widgets = []

    if props.get("logo"):
        widgets.append(_headline_brand_info(props))

    widgets.append(_headline_heading(props))

    if include_media:
        media_type = props.get("mediaType", "none")
        if media_type == "image" and props.get("image"):
            widgets.append(_headline_media_image(props))
        elif media_type == "video" and props.get("video"):
            widgets.append(_headline_media_video(props))

    btn = _headline_button(props)
    if btn:
        widgets.append(btn)

    return widgets


def build_headline_section(props: dict) -> dict:
    section_style = props.get("sectionStyle") or {}
    bg_media_type = props.get("bgMediaType") or "none"
    image_align   = props.get("imageAlign") or ""
    column        = props.get("column", 1)

    section_info = {}

    # isFullwidth — only when isFullScreen is explicitly present
    is_full_screen = props.get("isFullScreen")
    if is_full_screen is not None:
        section_info["isFullwidth"] = bool(is_full_screen)

    # Background
    if bg_media_type == "videoBg":
        section_info["bgType"]  = "video"
        section_info["bgVideo"] = {
            "src":    props.get("backgroundVideo", ""),
            "poster": props.get("backgroundVideoPoster", ""),
        }
    elif bg_media_type == "imageBg":
        bg_image = props.get("backgroundImage", "")
        if bg_image:
            section_info["bgType"]  = "image"
            section_info["bgImage"] = {"src": bg_image}
    elif bg_media_type in ("none", "imageAlignBg"):
        # For "none": section bg comes entirely from sectionStyle.bgImage.
        # For "imageAlignBg": the main half-bg lives on the col, but sectionStyle.bgImage
        # (if present) adds an additional section-level background image.
        bg_image = section_style.get("bgImage")
        if bg_image:
            section_info["bgType"]  = "image"
            section_info["bgImage"] = {"src": bg_image}
            if section_style.get("bgSize"):
                sz = section_style["bgSize"]
                section_info["bgSize"] = {"xs": sz, "lg": sz}
            if section_style.get("bgPosition"):
                pos = convert_bg_position(section_style["bgPosition"])
                section_info["bgPosition"] = {"xs": pos, "lg": pos}
            if section_style.get("bgRepeat"):
                section_info["bgRepeat"] = section_style["bgRepeat"]
            if section_style.get("bgAttachment"):
                section_info["bgAttachment"] = section_style["bgAttachment"]

    # bgColor from sectionStyle
    bg_color = section_style.get("bgColor")
    if bg_color:
        section_info["bgColor"] = bg_color.lower()

    # Overlay
    if props.get("isBgOverlay"):
        section_info["isOverlay"] = True

    # Padding — includes md breakpoint. Explicit sectionStyle values only count when
    # actually set (null means "not configured", not "explicit 0" — a v3 field can be
    # present-but-null; fixed 2026-08-05, was previously checking key-presence instead
    # of the value itself). className2's utility-class padding (e.g. "pb-xl-5") fills
    # in whatever explicit padding leaves unset — see merge_classname2_padding().
    padding = section_style.get("padding") or {}
    sm_pad  = padding.get("sm") or {}
    xl_pad  = padding.get("xl") or {}
    md_pad  = padding.get("md") or {}
    pt, pb  = {}, {}
    for src, bp in ((sm_pad, "xs"), (xl_pad, "lg"), (md_pad, "md")):
        if src.get("top")    is not None: pt[bp] = parse_size(src["top"])
        if src.get("bottom") is not None: pb[bp] = parse_size(src["bottom"])
    pt, pb = merge_classname2_padding(pt, pb, props.get("className2"))

    # --- Build columns ---
    if bg_media_type == "imageAlignBg" and column == 2:
        # This layout puts a full-bleed background image in one column and content in
        # the other, side by side — section-level padding would inset BOTH columns,
        # breaking the image's full-bleed edge. So whenever there IS a computed padding
        # (from sectionStyle.padding and/or className2), it goes on the content column
        # instead, and the section itself is forced to 0 at xs/lg (confirmed by the user
        # testing this directly in v3, 2026-08-06 — this layout only, not a general
        # section->col padding move). `md` is deliberately NOT included — it's not a
        # default/cascading breakpoint in v4 (confirmed by the user, 2026-08-06), only
        # ever written when a real md-specific value exists, which a synthetic reset-
        # to-0 never is. When there's no padding signal at all, section_info is left
        # untouched, same as every other layout (template default applies) — forcing
        # an explicit 0 unconditionally would be a real behavior change from "omitted"
        # whenever the template default isn't already 0.
        if pt or pb:
            section_info["paddingTop"]    = {"xs": {"value": 0, "unit": "px"},
                                              "lg": {"value": 0, "unit": "px"}}
            section_info["paddingBottom"] = {"xs": {"value": 0, "unit": "px"},
                                              "lg": {"value": 0, "unit": "px"}}
        image_align_config = props.get("imageAlignConfig") or {}

        image_col_info = {
            "bgType":  "image",
            "bgImage": {"src": props.get("backgroundImage", "")},
        }
        col_color = image_align_config.get("color", "")
        if col_color:
            image_col_info["bgColor"] = col_color.lower()
        if image_align_config.get("position"):
            lg_pos = convert_bg_position(image_align_config["position"])
            image_col_info["bgPosition"] = {"xs": "center", "lg": lg_pos}
        if image_align_config.get("size"):
            sz = image_align_config["size"]
            image_col_info["bgSize"] = {"xs": sz, "lg": sz}

        media_type = props.get("mediaType", "none")
        image_col_children = []
        if media_type == "image" and props.get("image"):
            image_col_children.append(_headline_media_image(props))

        if image_align == "imageRight":
            # Content col DOM-first (appears left on desktop), image col DOM-second (right)
            # Mobile: image order:1 (appears first), content order:2
            image_col_info["order"]  = {"xs": "1"}
            content_col_info         = {"order": {"xs": "2"}}
            if pt: content_col_info["paddingTop"]    = pt
            if pb: content_col_info["paddingBottom"] = pb
            cols = [
                make_node("col", None, None, content_col_info, _headline_content_widgets(props, include_media=False)),
                make_node("col", None, None, image_col_info,   image_col_children),
            ]
        else:
            # Image col DOM-first (appears left), content col DOM-second (right)
            image_col_info["order"] = {"xs": "1"}
            content_col_info        = {"order": {"xs": "2"}}
            if pt: content_col_info["paddingTop"]    = pt
            if pb: content_col_info["paddingBottom"] = pb
            cols = [
                make_node("col", None, None, image_col_info,   image_col_children),
                make_node("col", None, None, content_col_info, _headline_content_widgets(props, include_media=False)),
            ]

    elif column == 2:
        if pt: section_info["paddingTop"]    = pt
        if pb: section_info["paddingBottom"] = pb
        # Regular 2-col: media col + content col
        media_type = props.get("mediaType", "none")
        media_widgets = []
        if media_type == "image" and props.get("image"):
            media_widgets.append(_headline_media_image(props))
        elif media_type == "video" and props.get("video"):
            media_widgets.append(_headline_media_video(props))

        if image_align == "imageRight":
            # Content DOM-first, media DOM-second; mobile: media order:1, content order:2
            cols = [
                make_node("col", None, None, {"order": {"xs": "2"}}, _headline_content_widgets(props, include_media=False)),
                make_node("col", None, None, {"order": {"xs": "1"}}, media_widgets),
            ]
        else:
            # Media DOM-first, content DOM-second; no mobile order
            cols = [
                make_node("col", None, None, {}, media_widgets),
                make_node("col", None, None, {}, _headline_content_widgets(props, include_media=False)),
            ]

    else:
        # Single col — all widgets including media
        if pt: section_info["paddingTop"]    = pt
        if pb: section_info["paddingBottom"] = pb
        cols = [make_node("col", None, None, {}, _headline_content_widgets(props, include_media=True))]

    row = make_node("row", None, None, {}, cols)
    return make_node("section", "Standard", props.get("presetName", ""), section_info, [row])


# ---------------------------------------------------------------------------
# Section builder: SlideShowSection → Slider
# ---------------------------------------------------------------------------

def _slideshow_heading(props: dict) -> dict:
    """WidgetHeading for SlideShowSection — section-level title/description."""
    title_style = props.get("titleStyle") or {}
    desc_style  = props.get("descriptionStyle") or {}

    title_obj = {"text": props.get("title", "")}
    title_color = title_style.get("fontColor")
    if title_color:
        title_obj["color"] = title_color.lower()

    info = {"title": title_obj}

    if props.get("isTitleH1"):
        info["titleAs"] = "h1"

    desc = props.get("description")
    if desc:
        desc_obj = {"text": desc}
        desc_color = desc_style.get("fontColor")
        if desc_color:
            desc_obj["color"] = desc_color.lower()
        info["description"] = desc_obj

    title_align = title_style.get("align") or {}
    alignment = {}
    for old_bp, new_bp in (("sm", "xs"), ("xl", "lg"), ("md", "md")):
        if old_bp in title_align:
            alignment[new_bp] = title_align[old_bp]
    if alignment:
        info["alignment"] = alignment

    return make_node("widget", "WidgetHeading", None, info)


def _slideshow_bullet_list(props: dict) -> dict:
    """WidgetBulletList for SlideShowSection — from props.bulletPoints."""
    bullet_lists = [
        {"description": {"text": item}}
        for item in (props.get("bulletPoints") or [])
    ]
    info = {"bulletLists": bullet_lists}
    if props.get("hasBulletAnimation"):
        info["effects"] = [{
            "trigger":   "inview",
            "animation": "slideInFromRight",
            "target":    "child",
        }]
    return make_node("widget", "WidgetBulletList", None, info)


def _slideshow_outer_button(props: dict):
    """WidgetButtonGroup for the section-level button (outside the slider)."""
    button = props.get("button")
    if not button:
        return None

    button_style = props.get("buttonStyle") or {}
    hover        = button_style.get("hoverStyle") or {}
    align        = button_style.get("align") or {}

    btn_obj = {"title": button}
    link = props.get("buttonLink")
    if link:
        btn_obj["to"] = link
    target = props.get("buttonTarget")
    if target:
        btn_obj["target"] = target

    if button_style.get("bgColor"):
        btn_obj["buttonFillColor"] = button_style["bgColor"].lower()
    if button_style.get("fontColor"):
        btn_obj["buttonTextColor"] = button_style["fontColor"].lower()
    if hover.get("bgColor"):
        btn_obj["buttonHoverFillColor"] = hover["bgColor"].lower()
    if hover.get("fontColor"):
        btn_obj["buttonHoverTextColor"] = hover["fontColor"].lower()

    info = {"buttons": [btn_obj]}

    widget_align = {}
    for old_bp, new_bp in (("sm", "xs"), ("xl", "lg"), ("md", "md")):
        if old_bp in align:
            widget_align[new_bp] = align[old_bp]
    if widget_align:
        info["widgetAlignSelf"] = widget_align

    return make_node("widget", "WidgetButtonGroup", None, info)


def _slideshow_widget(props: dict) -> dict:
    """WidgetSlider — the main slider widget."""
    is_show_content = props.get("isShowSlideContent", True)
    has_dots        = props.get("hasDots", False)
    has_arrows      = props.get("hasArrows", True)
    has_fade        = props.get("hasFadeAnimate", False)
    has_overlay     = props.get("hasOverlay", False)
    slides_to_show  = props.get("slidesToShow")
    slides_to_scroll = props.get("slidesToScroll")
    column          = props.get("column", 1)
    slide_content_style = props.get("slideContentStyle") or {}

    # textPosition absent = default "middle" (bg-image); "" = full-image
    if "textPosition" not in props:
        text_position = "middle"
    else:
        text_position = props.get("textPosition") or ""

    # Determine variant
    variant = "full-image" if (is_show_content and text_position == "") else "bg-image"

    # Build slide items
    sliders = []
    for slide in (props.get("slideObjects") or []):
        image_obj = {"src": slide.get("image", "")}
        mobile_src = slide.get("imageMobile")
        if mobile_src:
            image_obj["mobileSrc"] = mobile_src
        alt = slide.get("title")
        if alt:
            image_obj["alt"] = alt

        item = {"image": image_obj, "mediaType": "image"}

        link = slide.get("link")
        if link:
            item["to"] = link

        if is_show_content:
            title_text = slide.get("title")
            if title_text:
                title_obj = {"text": title_text}
                title_color = (slide_content_style.get("title") or {}).get("fontColor")
                if title_color:
                    title_obj["color"] = title_color.lower()
                item["title"] = title_obj

            desc_text = slide.get("desc")
            if desc_text:
                desc_obj = {"text": desc_text}
                desc_color = (slide_content_style.get("description") or {}).get("fontColor")
                if desc_color:
                    desc_obj["color"] = desc_color.lower()
                item["description"] = desc_obj

        # Per-slide button
        btn_text = slide.get("button")
        if btn_text:
            btn_style = slide_content_style.get("button") or {}
            btn_hover = btn_style.get("hoverStyle") or {}
            btn_obj = {"title": btn_text}
            btn_link = slide.get("buttonLink")
            if btn_link:
                btn_obj["to"] = btn_link
            btn_target = slide.get("buttonTarget")
            if btn_target:
                btn_obj["target"] = btn_target
            if btn_style.get("bgColor"):
                btn_obj["buttonFillColor"] = btn_style["bgColor"].lower()
            if btn_style.get("fontColor"):
                btn_obj["buttonTextColor"] = btn_style["fontColor"].lower()
            if btn_hover.get("bgColor"):
                btn_obj["buttonHoverFillColor"] = btn_hover["bgColor"].lower()
            if btn_hover.get("fontColor"):
                btn_obj["buttonHoverTextColor"] = btn_hover["fontColor"].lower()
            item["buttons"] = [btn_obj]

        target = slide.get("target")
        if target:
            item["target"] = target

        if has_overlay:
            item["isOverlay"] = True

        sliders.append(item)

    # slideConfig
    config = {}

    if slides_to_show is not None:
        config["slidesPerView"] = slides_to_show
    elif column == 2:
        config["slidesPerView"] = 1

    config["hasPagination"] = has_dots
    if has_dots:
        config["paginationType"] = "bullets"

    arrows_pos = props.get("arrowsPosition") or ""
    if arrows_pos == "arrowsBottomInside":
        config["arrowsPosition"] = "bottom"
    elif not has_arrows:
        config["hasArrows"] = False
    else:
        config["hasArrows"] = True

    if not has_arrows and not has_dots:
        config["isAutoplay"] = True

    if has_fade:
        config["effect"] = "fade"

    slide_speed = props.get("slideSpeed")
    if slide_speed is not None:
        config["speed"] = slide_speed
    autoplay_speed = props.get("slideAutoplaySpeed")
    if autoplay_speed is not None:
        config["autoplaySpeed"] = autoplay_speed

    if slides_to_scroll is not None:
        config["slidesPerGroup"] = slides_to_scroll
    elif slides_to_show is not None and slides_to_show > 1:
        config["slidesPerGroup"] = slides_to_show // 2
    elif column == 2:
        config["slidesPerGroup"] = 1

    if props.get("textPosition") == "middle":
        config["isCenter"] = True

    info = {
        "sliders": sliders,
        "variant": variant,
        "isShowContent": is_show_content,
        "slideConfig": config,
    }

    if props.get("isCropAllImages"):
        if variant == "full-image":
            info["mediaRatio"] = "1 / 1"
        else:
            info["cardRatio"] = {"xs": "1 / 1", "lg": "1 / 1"}

    return make_node("widget", "WidgetSlider", None, info)


def build_slideshow_section(props: dict) -> dict:
    section_style = props.get("sectionStyle") or {}
    padding       = section_style.get("padding") or {}
    sm_pad        = padding.get("sm") or {}
    xl_pad        = padding.get("xl") or {}
    md_pad        = padding.get("md") or {}
    column        = props.get("column", 1)
    slide_align   = props.get("slideAlign") or ""

    section_info = {}

    is_full_screen = props.get("isFullScreen")
    if is_full_screen is not None:
        section_info["isFullwidth"] = bool(is_full_screen)

    bg_color = section_style.get("bgColor")
    if bg_color:
        section_info["bgColor"] = bg_color.lower()

    bg_image = section_style.get("bgImage")
    if bg_image:
        section_info["bgType"]  = "image"
        section_info["bgImage"] = {"src": bg_image}
        bg_position = section_style.get("bgPosition")
        if bg_position:
            pos = convert_bg_position(bg_position)
            section_info["bgPosition"] = {"xs": pos, "lg": pos}
        bg_repeat = section_style.get("bgRepeat")
        if bg_repeat:
            section_info["bgRepeat"] = bg_repeat

    pt, pb = {}, {}
    for src, bp in ((sm_pad, "xs"), (xl_pad, "lg"), (md_pad, "md")):
        if src.get("top")    is not None: pt[bp] = parse_size(src["top"])
        if src.get("bottom") is not None: pb[bp] = parse_size(src["bottom"])
    pt, pb = merge_classname2_padding(pt, pb, props.get("className2"))
    if pt: section_info["paddingTop"]    = pt
    if pb: section_info["paddingBottom"] = pb

    has_heading = bool(props.get("title") or props.get("description"))
    has_bullets = bool(props.get("bulletPoints"))
    has_button  = bool(props.get("button"))

    slider_widget  = _slideshow_widget(props)
    heading_widget = _slideshow_heading(props) if has_heading else None
    bullet_widget  = _slideshow_bullet_list(props) if has_bullets else None
    button_widget  = _slideshow_outer_button(props) if has_button else None

    if column == 2:
        slider_col = make_node("col", None, None, {}, [slider_widget])
        content_widgets = []
        if heading_widget: content_widgets.append(heading_widget)
        if bullet_widget:  content_widgets.append(bullet_widget)
        if button_widget:  content_widgets.append(button_widget)
        content_col = make_node("col", None, None, {}, content_widgets)
        cols = [slider_col, content_col] if slide_align == "slideLeft" else [content_col, slider_col]
    else:
        single_widgets = []
        if heading_widget: single_widgets.append(heading_widget)
        single_widgets.append(slider_widget)
        if button_widget:  single_widgets.append(button_widget)
        cols = [make_node("col", None, None, {}, single_widgets)]

    row = make_node("row", None, None, {}, cols)
    return make_node("section", "Slider", props.get("presetName", ""), section_info, [row])


_CHANNEL_TABLE = {
    "facebook":  ("#2d65f6", "facebook"),
    "line":      ("#00b34f", "line"),
    "lazada":    ("#0b0f82", "lazada"),
    "shopee":    ("#e05c35", "shopee"),
    "instagram": ("#dd2a7b", "instagram"),
    "tiktok":    ("#000000", "tiktok"),
    "youtube":   ("#FF0000", "youtube"),
    "twitter":   ("#000000", "twitter"),
    "custom":    ("#666666", "globe"),
    "email":     ("#666666", "mail"),
    "phone":     ("#03a9f4", "phone"),
}


def _feat_item(obj: dict, feat_style: dict) -> dict:
    media_type = obj.get("mediaType", "image")

    if media_type == "none":
        channel = obj.get("buychannel", "custom")
        bg_color, icon_name = _CHANNEL_TABLE.get(channel, ("#666666", "globe"))
        item = {
            "bgColor":   bg_color,
            "title":     {"text": obj.get("title", "")},
            "icon":      {"name": icon_name, "color": "var(--color-white)"},
            "mediaType": "icon",
        }
        if obj.get("link"):
            item["to"] = obj["link"]
        if obj.get("target"):
            item["target"] = obj["target"]
        return item

    if media_type == "video":
        item = {}
        if obj.get("title"):
            item["title"] = {"text": obj["title"]}
        if obj.get("desc"):
            item["description"] = {"text": obj["desc"]}
        item["mediaType"] = "video"
        if obj.get("video"):
            item["video"] = {"src": obj["video"]}
            item["isShowMedia"] = True
        return item

    # image
    img_obj = {}
    src = obj.get("image") or ""
    if src:
        img_obj["src"] = src
    mobile = obj.get("imageMobile") or ""
    if mobile:
        img_obj["mobileSrc"] = mobile
    if obj.get("title"):
        img_obj["alt"] = obj["title"]

    item = {"mediaType": "image"}
    if img_obj.get("src"):
        item["isShowMedia"] = True
        item["image"] = img_obj

    if obj.get("title"):
        t_style  = feat_style.get("title") or {}
        t_obj    = {"text": obj["title"]}
        if t_style.get("fontColor"):
            t_obj["color"] = t_style["fontColor"].lower()
        item["title"] = t_obj

    if obj.get("desc"):
        d_style = feat_style.get("description") or {}
        d_obj   = {"text": obj["desc"]}
        if d_style.get("fontColor"):
            d_obj["color"] = d_style["fontColor"].lower()
        item["description"] = d_obj

    if obj.get("featureButton"):
        btn_style = feat_style.get("button") or {}
        hover     = btn_style.get("hoverStyle") or {}
        btn = {"title": obj["featureButton"]}
        if obj.get("link"):
            btn["to"] = obj["link"]
        if obj.get("target"):
            btn["target"] = obj["target"]
        if btn_style.get("bgColor"):
            btn["buttonFillColor"] = btn_style["bgColor"].lower()
        if btn_style.get("fontColor"):
            btn["buttonTextColor"] = btn_style["fontColor"].lower()
        if hover.get("bgColor"):
            btn["buttonHoverFillColor"] = hover["bgColor"].lower()
        if hover.get("fontColor"):
            btn["buttonHoverTextColor"] = hover["fontColor"].lower()
        item["buttons"] = [btn]
    elif obj.get("link"):
        item["to"] = obj["link"]
        if obj.get("target"):
            item["target"] = obj["target"]

    return item


def _feat_list_widget(props: dict) -> dict:
    feat_style   = props.get("featureStyle") or {}
    feat_objects = props.get("featureObjects") or []
    class_tokens = set((props.get("className") or "").split())
    is_buy_ch    = bool(props.get("buyChannel"))

    features = [_feat_item(obj, feat_style) for obj in feat_objects]

    lg_cols = str(props.get("featureNumberInRow", 1))
    xs_cols = str(props.get("featureNumberMobileInRow", 1))

    has_video = any(obj.get("mediaType") == "video" for obj in feat_objects)
    has_crop  = any(obj.get("isCropImage") for obj in feat_objects)

    info = {
        "variant":        "full-image" if has_video else "fit-image",
        "features":       features,
        "layoutGridCols": {"lg": lg_cols, "xs": xs_cols},
    }

    # isCropImage on any feature crops to square (1/1); otherwise (non-video) the
    # image keeps its natural ratio — emit "auto" explicitly so it doesn't inherit
    # a template default. Video features have no crop concept of their own, so when
    # nothing sets isCropImage, mediaRatio is simply omitted rather than defaulted.
    if has_crop:
        info["mediaRatio"] = "1 / 1"
    elif not has_video:
        info["mediaRatio"] = "auto"

    if is_buy_ch:
        info["cardDirection"]      = "row"
        info["cardInfoDistribute"] = "center"
        info["cardInfoAlignment"]  = "left"
        info["colorScheme"]        = "color-scheme-inverse"
        info["effectHover"]        = {"item": "grow"}
    elif "f_titlecolumn_section" in class_tokens:
        text_align = (feat_style.get("title") or {}).get("textAlign")
        if text_align:
            info["cardInfoAlignment"] = text_align
        info["cardDirection"]      = {"lg": "row"}
        info["cardInfoDistribute"] = "center"
    elif "f_iconcontact_section" in class_tokens:
        info["cardInfoAlignment"] = "center"

    return make_node("widget", "WidgetFeatureList", None, info)


def _feat_heading_widget(props: dict):
    title_style = props.get("titleStyle") or {}
    desc_style  = props.get("descriptionStyle") or {}
    title_text  = props.get("title") or ""
    desc_text   = props.get("description") or ""

    if not title_text and not desc_text:
        return None

    info = {}

    if title_text:
        t_obj = {"text": title_text}
        if title_style.get("fontColor"):
            t_obj["color"] = title_style["fontColor"].lower()
        info["title"] = t_obj

    if desc_text:
        d_obj = {"text": desc_text}
        if desc_style.get("fontColor"):
            d_obj["color"] = desc_style["fontColor"].lower()
        info["description"] = d_obj

    title_align = title_style.get("align") or {}
    alignment = {}
    for old_bp, new_bp in (("sm", "xs"), ("xl", "lg"), ("md", "md")):
        if old_bp in title_align:
            alignment[new_bp] = title_align[old_bp]
    if "xs" in alignment and "lg" not in alignment:
        alignment["lg"] = alignment["xs"]
    if alignment:
        info["alignment"] = alignment

    if props.get("isTitleH1"):
        info["titleAs"] = "h1"

    return make_node("widget", "WidgetHeading", None, info)


def _feat_button_widget(props: dict):
    button_text = props.get("button") or ""
    if not button_text:
        return None

    button_style = props.get("buttonStyle") or {}
    hover        = button_style.get("hoverStyle") or {}
    align        = button_style.get("align") or {}

    btn = {"title": button_text}
    if props.get("buttonLink"):
        btn["to"] = props["buttonLink"]
    if props.get("buttonTarget"):
        btn["target"] = props["buttonTarget"]
    if button_style.get("bgColor"):
        btn["buttonFillColor"] = button_style["bgColor"].lower()
    if button_style.get("fontColor"):
        btn["buttonTextColor"] = button_style["fontColor"].lower()
    if hover.get("bgColor"):
        btn["buttonHoverFillColor"] = hover["bgColor"].lower()
    if hover.get("fontColor"):
        btn["buttonHoverTextColor"] = hover["fontColor"].lower()

    info = {"buttons": [btn]}

    widget_align = {}
    for old_bp, new_bp in (("sm", "xs"), ("xl", "lg"), ("md", "md")):
        if old_bp in align:
            widget_align[new_bp] = align[old_bp]
    if widget_align:
        info["widgetAlignSelf"] = widget_align

    return make_node("widget", "WidgetButtonGroup", None, info)


def build_featuresection_section(props: dict) -> dict:
    section_style = props.get("sectionStyle") or {}
    padding       = section_style.get("padding") or {}
    sm_pad        = padding.get("sm") or {}
    xl_pad        = padding.get("xl") or {}
    md_pad        = padding.get("md") or {}
    class_tokens  = set((props.get("className") or "").split())

    section_info = {}

    bg_color = section_style.get("bgColor")
    if bg_color:
        section_info["bgColor"] = bg_color.lower()

    bg_image = section_style.get("bgImage")
    if bg_image:
        section_info["bgType"]  = "image"
        section_info["bgImage"] = {"src": bg_image}
        bg_pos = section_style.get("bgPosition")
        if bg_pos:
            pos = convert_bg_position(bg_pos)
            section_info["bgPosition"] = {"lg": pos, "xs": pos}
        bg_size = section_style.get("bgSize")
        if bg_size:
            section_info["bgSize"] = {"lg": bg_size, "xs": bg_size}

    pt, pb = {}, {}
    for src, bp in ((sm_pad, "xs"), (xl_pad, "lg"), (md_pad, "md")):
        if src.get("top")    is not None: pt[bp] = parse_size(src["top"])
        if src.get("bottom") is not None: pb[bp] = parse_size(src["bottom"])
    pt, pb = merge_classname2_padding(pt, pb, props.get("className2"))
    if pt: section_info["paddingTop"]    = pt
    if pb: section_info["paddingBottom"] = pb

    heading_widget = _feat_heading_widget(props)
    feature_widget = _feat_list_widget(props)
    button_widget  = _feat_button_widget(props)

    if "direction-column" in class_tokens and "left" in class_tokens:
        col1_children = []
        if heading_widget:
            col1_children.append(heading_widget)
        if button_widget:
            col1_children.append(button_widget)
        col1 = make_node("col", None, None, {"span": {"lg": "4"}}, col1_children)
        col2 = make_node("col", None, None, {"span": {"lg": "8"}}, [feature_widget])
        row  = make_node("row", None, None, {}, [col1, col2])
    else:
        col_children = [heading_widget, feature_widget] if heading_widget else [feature_widget]
        if button_widget:
            col_children.append(button_widget)
        col = make_node("col", None, None, {}, col_children)
        row = make_node("row", None, None, {}, [col])

    return make_node("section", "FeatureList", props.get("presetName", ""), section_info, [row])


# ---------------------------------------------------------------------------
# Section builder: ProductSection → Products
# ---------------------------------------------------------------------------

def _product_extract_nickname(title: str) -> str:
    t = title or ""
    if t.startswith("["):
        end = t.find("]")
        if end > 0:
            return t[:end + 1]
    return None


_PRODUCT_SHOWROOM_MAP = {
    "recommend": "RECOMMENDED",
    "hot":       "BEST_SELLER",
    "new":       "NEW",
    "sale":      "SALE",
}

_PRODUCT_SORT_MAP = {
    "hot": "most_popular",
    "new": "newest",
}


def _product_api_options(api_opts: dict) -> dict:
    value = api_opts.get("value") or {}
    filters = {}
    options = {}

    cat_id = value.get("category_id")
    if cat_id is not None and cat_id != 0 and str(cat_id) != "":
        filters["parent_category_id"] = str(cat_id)

    if value.get("ready_to_sell") == 1:
        filters["ready_to_sell"] = True

    showroom = value.get("showroom") or ""
    if showroom in _PRODUCT_SHOWROOM_MAP:
        filters["showroom"] = _PRODUCT_SHOWROOM_MAP[showroom]

    tag = value.get("tag")
    if tag:
        filters["anyTags"] = tag

    sort = value.get("sort") or ""
    if sort in _PRODUCT_SORT_MAP:
        options["sortBy"] = _PRODUCT_SORT_MAP[sort]

    result = {}
    if filters:
        result["filters"] = filters
    if options:
        result["options"] = options
    return result


def _to_int(value, default=None):
    """v3 sometimes records numeric fields as strings ("3" instead of 3) —
    v4 expects real ints for these. Falls back to `default` when value is
    missing or not parseable as an int."""
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _product_slide_config(props: dict, layout_type: str) -> dict:
    config = {}

    slides_per_view = props.get("productSlidesToShow") or props.get("productBoxNumber") or 5
    config["slidesPerView"] = _to_int(slides_per_view, 5)

    has_pagination = props.get("hasDots", False)
    config["hasPagination"] = has_pagination
    if has_pagination:
        config["paginationType"] = "bullets"

    config["hasArrows"] = props.get("hasArrows", True)

    if props.get("isAutoplay"):
        config["isAutoplay"] = True
        config["isLoop"] = True
        autoplay_speed = props.get("slideAutoplaySpeed")
        if autoplay_speed is not None:
            config["autoplaySpeed"] = _to_int(autoplay_speed, autoplay_speed)

    slides_to_scroll = props.get("slidesToScroll")
    if slides_to_scroll is not None:
        config["slidesPerGroup"] = _to_int(slides_to_scroll, slides_to_scroll)

    if layout_type == "imageAlignBg":
        config["arrowsPosition"] = "bottom"
    else:
        arrows_pos = props.get("arrowsPosition") or ""
        if arrows_pos in ("arrowsOutside", "arrowsBottomInside"):
            config["arrowsPosition"] = "bottom"

    slide_speed = props.get("slideSpeed")
    if slide_speed is not None:
        config["speed"] = _to_int(slide_speed, slide_speed)

    return config


def _product_widget_heading(props: dict):
    title_text = props.get("title", "")
    desc_text  = props.get("description", "")
    if not title_text and not desc_text:
        return None
    info = {"title": {"text": title_text}}
    if desc_text:
        info["description"] = {"text": desc_text}
    return make_node("widget", "WidgetHeading", None, info)


def _product_infer_layout_slick(props: dict) -> tuple:
    """layoutType/isUseSlick are sometimes omitted by older v3 presets even
    though the data they gate (bannerImage / arrows-dots-slidesToShow) is
    present — infer from that data instead of silently dropping it."""
    layout_type = props.get("layoutType")
    if not layout_type:
        if props.get("bannerImage") or props.get("bannerImageMobile"):
            layout_type = "bannerImage"
        else:
            layout_type = "none"

    if "isUseSlick" in props:
        is_slick = bool(props.get("isUseSlick"))
    else:
        is_slick = bool(
            "hasArrows" in props or "hasDots" in props or "productSlidesToShow" in props
        )

    return layout_type, is_slick


def _product_widget_media_banner(props: dict) -> dict:
    image_obj = {"src": props.get("bannerImage", "")}
    if props.get("bannerImageMobile"):
        image_obj["mobileSrc"] = props["bannerImageMobile"]
    if props.get("bannerTitle"):
        image_obj["alt"] = props["bannerTitle"]
    info = {"mediaType": "image", "image": image_obj}
    if props.get("bannerLink"):
        info["to"] = props["bannerLink"]
    info["target"] = props.get("bannerTarget") or "_self"
    return make_node("widget", "WidgetMedia", None, info)


def _product_widget_product_list(props: dict, layout_type: str, is_slick: bool) -> dict:
    product_box = props.get("productBoxNumber") or 5

    cols = {"lg": str(product_box)}
    if not (is_slick and layout_type != "none"):
        cols["xs"] = "1"

    api_opts      = _product_api_options(props.get("apiOptions") or {})
    is_overflow_x = not (is_slick and layout_type != "none")
    layout_grid   = {
        "isOverflowX": is_overflow_x,
        "template":    "slider" if is_slick else "default",
    }
    if is_slick:
        layout_grid["slideConfig"] = _product_slide_config(props, layout_type)

    info = {
        "layoutGridCols": cols,
        "productNumber":  _to_int(props.get("productNumber"), 0),
        "apiOptions":     api_opts,
        "layoutGrid":     layout_grid,
    }

    api_value = (props.get("apiOptions") or {}).get("value") or {}
    if api_value.get("is_showonlymain"):
        info["cardConfig"] = {"isShowSubproduct": False}

    return make_node("widget", "WidgetProductList", None, info)


def _product_widget_button(props: dict):
    button = props.get("button")
    if not button:
        return None
    return make_node("widget", "WidgetButtonGroup", None, {
        "buttons": [{"title": button, "to": props.get("buttonLink", "/")}],
    })


def _product_bg_col_info(image_align_config: dict) -> dict:
    col_info = {
        "bgColor": image_align_config.get("color", ""),
        "bgType":  "image",
        "bgImage": {"src": image_align_config.get("image", "")},
    }
    size = image_align_config.get("size")
    if size:
        col_info["bgSize"] = {"xs": size, "lg": size}
    position = image_align_config.get("position")
    if position:
        pos = convert_bg_position(position)
        col_info["bgPosition"] = {"xs": pos, "lg": pos}
    return col_info


def build_productsection_section(props: dict) -> dict:
    layout_type, is_slick = _product_infer_layout_slick(props)

    section_info = {}
    if layout_type == "imageAlignBg":
        # Hardcoded, pre-existing approximation — NOT derived from any v3 field.
        # className2/sectionStyle.padding are intentionally not wired in for this
        # branch (out of scope today; it has the same full-bleed-image-column
        # concern as Headline's imageAlignBg layout, addressed separately if this
        # layout type ever comes up for a real theme).
        section_info["paddingTop"] = {
            "xs": {"value": 70, "unit": "px"},
            "lg": {"value": 100, "unit": "px"},
        }
        section_info["isFullwidth"] = True
    else:
        section_style = props.get("sectionStyle") or {}
        padding = section_style.get("padding") or {}
        sm_pad  = padding.get("sm") or {}
        xl_pad  = padding.get("xl") or {}
        md_pad  = padding.get("md") or {}
        pt, pb  = {}, {}
        for src, bp in ((sm_pad, "xs"), (xl_pad, "lg"), (md_pad, "md")):
            if src.get("top")    is not None: pt[bp] = parse_size(src["top"])
            if src.get("bottom") is not None: pb[bp] = parse_size(src["bottom"])
        pt, pb = merge_classname2_padding(pt, pb, props.get("className2"))
        if pt: section_info["paddingTop"]    = pt
        if pb: section_info["paddingBottom"] = pb

    heading      = _product_widget_heading(props)
    product_list = _product_widget_product_list(props, layout_type, is_slick)
    button       = _product_widget_button(props)

    if layout_type == "none":
        col_widgets = ([heading] if heading else []) + [product_list]
        if button:
            col_widgets.append(button)
        rows = [make_node("row", None, None, {},
                    [make_node("col", None, None, {}, col_widgets)])]

    elif layout_type == "bannerImage":
        media_banner = _product_widget_media_banner(props)
        if not is_slick:
            rows = []
            if heading:
                rows.append(make_node("row", None, None, {},
                    [make_node("col", None, None, {}, [heading])]))
            banner_col  = make_node("col", None, None,
                {"span": {"lg": "4"}, "verticalAlign": {"lg": "flex-start"}}, [media_banner])
            product_col_widgets = [product_list]
            if button:
                product_col_widgets.append(button)
            product_col = make_node("col", None, None,
                {"span": {"lg": "8"}}, product_col_widgets)
            rows.append(make_node("row", None, None, {}, [banner_col, product_col]))
        else:
            col_widgets = ([heading] if heading else []) + [product_list]
            if button:
                col_widgets.append(button)
            banner_col  = make_node("col", None, None,
                {"span": {"lg": "4", "xs": "12"}}, [media_banner])
            product_col = make_node("col", None, None,
                {"span": {"lg": "8", "xs": "12"}}, col_widgets)
            rows = [make_node("row", None, None, {}, [banner_col, product_col])]

    elif layout_type == "imageAlignBg":
        image_align_config = props.get("imageAlignConfig") or {}
        image_align        = image_align_config.get("imageAlign") or ""
        col_widgets = ([heading] if heading else []) + [product_list]
        if button:
            col_widgets.append(button)
        content_col = make_node("col", None, None, {}, col_widgets)
        bg_col      = make_node("col", None, None, _product_bg_col_info(image_align_config), [])
        cols = [content_col, bg_col] if image_align == "imageRight" else [bg_col, content_col]
        rows = [make_node("row", None, None, {}, cols)]

    else:
        col_widgets = ([heading] if heading else []) + [product_list]
        if button:
            col_widgets.append(button)
        rows = [make_node("row", None, None, {},
                    [make_node("col", None, None, {}, col_widgets)])]

    nickname = _product_extract_nickname(props.get("title", ""))
    return make_node("section", "Products", nickname, section_info, rows)


def build_bannerslick_section(props: dict) -> dict:
    section_info = {}
    if props.get("isFullScreen"):
        section_info["isFullwidth"] = True
    title_text = props.get("title") or ""
    desc_text  = props.get("description") or ""
    col_children = []
    if title_text or desc_text:
        h_info = {}
        if title_text:
            h_info["title"] = {"text": title_text}
        if desc_text:
            h_info["description"] = {"text": desc_text}
        col_children.append(make_node("widget", "WidgetHeading", None, h_info))

    banner_objects = props.get("bannerObjects") or []
    sliders = [
        {
            "mediaType": "image",
            "image": {"src": obj.get("image", "")},
            "title": {"text": obj.get("title", "")},
        }
        for obj in banner_objects
    ]
    slider_info: dict = {"sliders": sliders}
    if props.get("isCropAllImages"):
        slider_info["cardRatio"] = {"xs": "1 / 1", "lg": "1 / 1"}
    slider_info["slideConfig"] = {"slidesPerView": 4}
    col_children.append(make_node("widget", "WidgetSlider", None, slider_info))

    col     = make_node("col", None, None, {}, col_children)
    row     = make_node("row", None, None, {}, [col])
    section = make_node("section", "Gallery", props.get("presetName", ""), section_info, [row])
    if props.get("displayStatus") == "hide":
        section["hide"] = True
    return section


# ---------------------------------------------------------------------------
# ProductTab helpers
# ---------------------------------------------------------------------------

_PRODUCTTAB_SORT_MAP = {
    "hot": "most_popular",
    "new": "newest",
}

_PRODUCTTAB_SHOWROOM_MAP = {
    "new":       "NEW",
    "sale":      "SALE",
    "recommend": "RECOMMENDED",
    "hot":       "BEST_SELLER",
}


def _producttab_build_tab(tab_obj: dict) -> dict:
    filters = {}
    showroom = tab_obj.get("showroom", "")
    if showroom:
        mapped = _PRODUCTTAB_SHOWROOM_MAP.get(showroom)
        if mapped:
            filters["showroom"] = mapped

    ready_to_sell = tab_obj.get("ready_to_sell")
    if ready_to_sell:
        filters["ready_to_sell"] = True

    tag = tab_obj.get("tag", "")
    if tag:
        filters["tags"] = tag

    cat_id = tab_obj.get("category_id")
    if cat_id is not None and str(cat_id) not in ("0", ""):
        filters["parent_category_id"] = str(cat_id)

    options = {}
    sort = tab_obj.get("sort", "")
    if sort and sort in _PRODUCTTAB_SORT_MAP:
        options["sortBy"] = _PRODUCTTAB_SORT_MAP[sort]

    api_options = {}
    if options:
        api_options["options"] = options
    if filters:
        api_options["filters"] = filters

    tab = {"label": tab_obj.get("category_name", "")}
    if api_options:
        tab["apiOptions"] = api_options
    return tab


def _producttab_widget(props: dict) -> dict:
    tab_type  = props.get("tabProductType", "simple")
    preset_id = props.get("presetId", 1)
    product_limit = props.get("productLimit", 4)

    if tab_type == "simple":
        template = "default"
    elif tab_type == "banner":
        template = "banner-left"
    elif preset_id == 2:
        template = "default"
    else:
        template = "banner-right"

    tabs = [_producttab_build_tab(t) for t in (props.get("tabProductObjects") or [])]

    tab_info = {
        "layoutGridCols": {"lg": product_limit},
        "template":       template,
        "tabs":           tabs,
        "productNumber":  product_limit,
    }

    if tab_type == "simple":
        dist_map = {1: "flex-end", 2: "center", 3: "flex-start"}
        dist = dist_map.get(preset_id)
        if dist:
            tab_info["tabsDefaultDistribute"] = dist
    elif tab_type == "bannerWithTab" and preset_id == 2:
        tab_info["tabsDefaultDistribute"] = "center"

    if tab_type in ("banner", "bannerWithTab") and not (tab_type == "bannerWithTab" and preset_id == 2):
        banner = {}
        if props.get("bannerImage"):
            banner["src"] = props["bannerImage"]
        if props.get("bannerImageMobile"):
            banner["mobileSrc"] = props["bannerImageMobile"]
        if props.get("bannerTitle"):
            banner["alt"] = props["bannerTitle"]
        if banner:
            tab_info["banner"] = banner

    return make_node("widget", "WidgetProductTab", None, tab_info)


def _producttab_media_widget(props: dict) -> dict:
    image = {}
    if props.get("bannerImage"):
        image["src"] = props["bannerImage"]
    if props.get("bannerImageMobile"):
        image["mobileSrc"] = props["bannerImageMobile"]
    if props.get("bannerTitle"):
        image["alt"] = props["bannerTitle"]
    return make_node("widget", "WidgetMedia", None, {
        "mediaType":      "image",
        "mediaObjectFit": "cover",
        "image":          image,
    })


# ---------------------------------------------------------------------------
# GallerySection helpers
# ---------------------------------------------------------------------------

def build_gallerysection_section(props: dict) -> dict:
    section_info = {}
    if props.get("isFullScreen"):
        section_info["isFullwidth"] = True

    h_info = {}
    title = props.get("title", "")
    if title:
        h_info["title"] = {"text": title}
    desc = props.get("description", "")
    if desc:
        h_info["description"] = {"text": desc}
    heading = make_node("widget", "WidgetHeading", None, h_info)

    images = [
        {"src": obj["image"], "alt": obj.get("title", ""), "headline": {"text": obj.get("title", "")}}
        for obj in (props.get("galleryObjects") or [])
    ]
    gallery_info = {
        "images": images,
        "layoutGrid": {"isOverflowX": True},
        "layoutGridCols": {
            "lg": props.get("galleryNumberInRow", 4),
            "xs": props.get("galleryNumberMobileInRow", 2),
        },
    }
    if props.get("isCropAllImages"):
        gallery_info["elementPictureAspectRatio"] = "1 / 1"
    gallery = make_node("widget", "WidgetGalleryList", None, gallery_info)

    col_widgets = [heading, gallery]

    button_text = props.get("button", "")
    if button_text:
        btn_info = {"title": button_text, "to": props.get("buttonLink", "")}
        target = props.get("buttonTarget", "")
        if target:
            btn_info["target"] = target
        col_widgets.append(make_node("widget", "WidgetButtonGroup", None, {
            "buttons": [btn_info]
        }))

    col  = make_node("col", None, None, {}, col_widgets)
    row  = make_node("row", None, None, {}, [col])
    nick = _product_extract_nickname(title)
    return make_node("section", None, nick, section_info, [row])


def build_producttab_section(props: dict) -> dict:
    tab_type  = props.get("tabProductType", "simple")
    preset_id = props.get("presetId", 1)

    section_style = props.get("sectionStyle") or {}
    padding = section_style.get("padding") or {}
    sm_pad  = padding.get("sm") or {}
    xl_pad  = padding.get("xl") or {}
    md_pad  = padding.get("md") or {}
    pt, pb  = {}, {}
    for src, bp in ((sm_pad, "xs"), (xl_pad, "lg"), (md_pad, "md")):
        if src.get("top")    is not None: pt[bp] = parse_size(src["top"])
        if src.get("bottom") is not None: pb[bp] = parse_size(src["bottom"])
    pt, pb = merge_classname2_padding(pt, pb, props.get("className2"))
    section_info = {}
    if pt: section_info["paddingTop"]    = pt
    if pb: section_info["paddingBottom"] = pb

    h_info = {"title": {"text": props.get("title", "")}}
    desc = props.get("description", "")
    if desc:
        h_info["description"] = {"text": desc}
    if tab_type != "banner" and preset_id == 2:
        h_info["alignment"] = {"sm": "center", "lg": "center"}
    elif tab_type == "bannerWithTab" and preset_id == 1:
        h_info["alignment"] = {"sm": "left", "lg": "left"}
    heading = make_node("widget", "WidgetHeading", None, h_info)

    col_widgets = [heading]
    if tab_type == "bannerWithTab" and preset_id == 2:
        col_widgets.append(_producttab_media_widget(props))
    col_widgets.append(_producttab_widget(props))

    button_text = props.get("button", "")
    if button_text:
        col_widgets.append(make_node("widget", "WidgetButtonGroup", None, {
            "buttons": [{"title": button_text, "to": "/category"}]
        }))

    col  = make_node("col", None, None, {}, col_widgets)
    row  = make_node("row", None, None, {}, [col])
    nick = _product_extract_nickname(props.get("title", ""))
    return make_node("section", "Products", nick, section_info, [row])


_SLIDETEXT_TYPO_MAP = {
    "slidetext_style_1": "typo_paragraph_medium",
    "slidetext_style_2": "typo_paragraph_xlarge_bold",
    "slidetext_style_3": "typo_paragraph_large_bold",
}


def build_slidetextsection_section(props: dict) -> dict:
    title        = props.get("title", "").strip()
    section_style = props.get("sectionStyle", {}) or {}
    desc_style    = props.get("descriptionStyle", {}) or {}

    section_info = {}
    section_info["isFullwidth"] = True
    section_info["containerPaddingX"] = {
        "lg": {"value": 0, "unit": "px"},
        "xs": {"value": 0, "unit": "px"},
    }

    height_raw = section_style.get("height", {}) or {}
    height = {}
    for old_bp, new_bp in (("sm", "xs"), ("xl", "lg"), ("md", "md")):
        if old_bp in height_raw:
            height[new_bp] = parse_size(height_raw[old_bp])
    if height:
        section_info["height"] = height

    section_info["paddingTop"]    = {"lg": {"value": 0, "unit": "px"}}
    section_info["paddingBottom"] = {"lg": {"value": 0, "unit": "px"}}

    bg_color = section_style.get("bgColor", "")
    if bg_color:
        section_info["bgColor"] = bg_color.lower()

    bg_image = section_style.get("bgImage", "")
    if bg_image:
        section_info["bgType"]  = "image"
        section_info["bgImage"] = {"src": bg_image}

    bg_size = section_style.get("bgSize", "")
    if bg_size:
        section_info["bgSize"] = {"lg": bg_size}

    bg_repeat = section_style.get("bgRepeat", "")
    if bg_repeat:
        section_info["bgRepeat"] = bg_repeat

    dur_str = props.get("duration", "0s")
    try:
        dur_val = int(str(dur_str).rstrip("s"))
    except ValueError:
        dur_val = 0

    typo_style = _SLIDETEXT_TYPO_MAP.get(props.get("keyName", ""), "typo_paragraph_medium")
    title_obj  = {"text": title, "typoStyle": typo_style}
    font_color = desc_style.get("fontColor", "")
    if font_color:
        title_obj["color"] = font_color.lower()

    widget_info = {
        "messages": [{"title": title_obj}],
        "marqueeTextDuration": {
            "sm": {"value": dur_val, "unit": "s"},
            "lg": {"value": dur_val, "unit": "s"},
        },
    }
    widget = make_node("widget", "WidgetMarqueeText", None, widget_info)
    col    = make_node("col", None, None, {}, [widget])
    row    = make_node("row", None, None, {}, [col])
    nick   = _product_extract_nickname(title)
    return make_node("section", None, nick, section_info, [row])


# ---------------------------------------------------------------------------
# Section builder: BlogSection → BlogList
# ---------------------------------------------------------------------------

def _blog_extract_nickname(title: str):
    """Extract '[TAG]' prefix from '[BLA2]Title' → '[BLA2]'."""
    t = title or ""
    if t.startswith("["):
        end = t.find("]")
        if end > 0:
            return t[:end + 1]
    return None


def _blog_heading_widget(props: dict, key_name: str) -> dict:
    """Build WidgetHeading for BlogSection."""
    title       = props.get("title", "")
    description = props.get("description", "")

    if key_name == "simpleblog_style_2":
        info = {
            "caption":   {"as": "span"},
            "title":     {"text": title, "as": "h2"},
            "alignment": "left",
        }
        if description:
            info["description"] = {"text": description}
    else:
        info = {"title": {"text": title}}
        if description:
            info["description"] = {"text": description}

    return make_node("widget", "WidgetHeading", None, info)


def _blog_list_widget(props: dict, key_name: str, preset_id: int) -> dict:
    """Build WidgetBlogList based on keyName + presetId layout variant."""
    blog_number        = props.get("blogNumber")
    blog_in_row        = props.get("blogNumberInRow")
    blog_mobile_in_row = props.get("blogNumberMobileInRow")
    is_show_date       = props.get("isShowDate", True)
    is_show_tag        = props.get("isShowTag", False)
    is_mobile_scroll   = props.get("isMobileFreeScroll", False)
    is_crop_image      = props.get("isCropImage", False)
    tag                = props.get("tag", "")

    info = {}

    if key_name == "simpleblog_style_1" and preset_id == 2:
        # bg-image layout (BLA2)
        if blog_number is not None:
            info["blogNumber"] = blog_number
        if blog_in_row is not None and blog_mobile_in_row is not None:
            info["layoutGridCols"] = {"lg": str(blog_in_row), "xs": str(blog_mobile_in_row)}
        if is_mobile_scroll:
            info["layoutGrid"] = {"isOverflowX": True}
        info["isShowDate"]         = is_show_date
        info["isShowTag"]          = is_show_tag
        info["layoutCard"]         = {"cardInfoAlignment": "left", "variant": "bg-image"}
        info["cardDirection"]      = {"lg": "column"}
        info["cardInfoDistribute"] = "flex-end"
        if is_crop_image:
            info["cardRatio"] = {"lg": "1 / 1"}
        if tag:
            info["apiOptions"] = {"filters": {"tags": tag}}

    elif key_name == "simpleblog_style_2":
        # highlight list layout with row direction (BLA3)
        info["isShowTag"]  = is_show_tag
        layout_grid = {"template": "default"}
        if is_mobile_scroll:
            layout_grid["isOverflowX"] = True
        info["layoutGrid"] = layout_grid
        if blog_number is not None:
            info["blogNumber"] = blog_number
        info["isShowDate"]        = is_show_date
        info["layoutCard"]        = {"variant": "full-image", "cardInfoAlignment": "left", "isShowMedia": True}
        info["isShowShortContent"] = True
        info["cardDirection"]     = {"sm": "column", "lg": "row"}
        info["cardMediaBasis"]    = {"value": 50, "unit": "%"}
        info["layoutGridCols"]    = {"sm": "1", "lg": "1"}

    elif key_name == "hilightblog_style_2":
        # hilight 2-col row layout (BLA4)
        info["layoutGridCols"] = {"lg": "2", "xs": "1"}
        if is_mobile_scroll:
            info["layoutGrid"] = {"isOverflowX": True}
        info["isShowDate"]         = is_show_date
        info["isShowTag"]          = is_show_tag
        info["layoutCard"]         = {"cardInfoAlignment": "left", "variant": "full-image", "isShowMedia": True}
        info["cardDirection"]      = {"sm": "column", "lg": "row"}
        info["cardInfoDistribute"] = "flex-start"
        if is_crop_image:
            info["cardRatio"] = {"lg": "1 / 1"}
        info["cardMediaBasis"] = {"lg": {"value": 50, "unit": "%"}}

    elif key_name == "hilightblog_style_1":
        # hilight column layout, minimal (BLA5)
        info["isShowDate"]  = is_show_date
        info["isShowTag"]   = is_show_tag
        info["layoutCard"]  = {"cardInfoAlignment": "left", "variant": "full-image", "isShowMedia": True}
        info["cardDirection"] = {"sm": "column", "lg": "column"}

    else:
        # simpleblog_style_1 presetId=1 or unknown — full-image column layout (BLA6)
        info["isShowDate"] = is_show_date
        info["layoutCard"] = {"cardInfoAlignment": "left", "variant": "full-image", "isShowMedia": True}
        info["cardDirection"] = {"sm": "column", "lg": "column"}
        if blog_number is not None:
            info["blogNumber"] = blog_number
        if blog_in_row is not None and blog_mobile_in_row is not None:
            info["layoutGridCols"] = {"lg": str(blog_in_row), "xs": str(blog_mobile_in_row)}
        if is_mobile_scroll:
            info["layoutGrid"] = {"isOverflowX": True}
        info["isShowTag"] = is_show_tag
        if is_crop_image:
            info["mediaRatio"] = "1 / 1"

    return make_node("widget", "WidgetBlogList", None, info)


def build_blog_section(props: dict) -> dict:
    key_name  = props.get("keyName", "")
    preset_id = props.get("presetId", 1)
    title     = props.get("title", "")

    nickname     = _blog_extract_nickname(title)
    section_kind = "BlogList"

    section_style = props.get("sectionStyle") or {}
    padding = section_style.get("padding") or {}
    sm_pad  = padding.get("sm") or {}
    xl_pad  = padding.get("xl") or {}
    md_pad  = padding.get("md") or {}
    pt, pb  = {}, {}
    for src, bp in ((sm_pad, "xs"), (xl_pad, "lg"), (md_pad, "md")):
        if src.get("top")    is not None: pt[bp] = parse_size(src["top"])
        if src.get("bottom") is not None: pb[bp] = parse_size(src["bottom"])
    pt, pb = merge_classname2_padding(pt, pb, props.get("className2"))
    section_info = {}
    if pt: section_info["paddingTop"]    = pt
    if pb: section_info["paddingBottom"] = pb

    heading   = _blog_heading_widget(props, key_name)
    blog_list = _blog_list_widget(props, key_name, preset_id)

    col_children = [heading, blog_list]

    button_text = props.get("button", "")
    if button_text:
        btn_obj = {"title": button_text}
        link = props.get("buttonLink", "")
        if link:
            btn_obj["to"] = link
        target = props.get("buttonTarget", "")
        if target:
            btn_obj["target"] = target
        col_children.append(make_node("widget", "WidgetButtonGroup", None, {"buttons": [btn_obj]}))

    col = make_node("col", None, None, {}, col_children)
    row = make_node("row", None, None, {}, [col])
    return make_node("section", section_kind, nickname, section_info, [row])


# ---------------------------------------------------------------------------
# Section builder: TopicSection → TextStack
# ---------------------------------------------------------------------------

def _topic_extract_nickname(title: str):
    """Extract '[TAG]' prefix from '[TB1]Title' → '[TB1]'."""
    t = title or ""
    if t.startswith("["):
        end = t.find("]")
        if end > 0:
            return t[:end + 1]
    return None


def _topic_strip_html(text: str) -> str:
    """Convert <br/> variants to newline and strip remaining HTML tags."""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text


def _topic_heading_widget(props: dict) -> dict:
    """WidgetHeading for TopicSection — alignment defaults to {xs,lg:left}."""
    is_title_html = bool(props.get("isTitleHtml"))
    is_title_h1   = bool(props.get("isTitleH1"))
    # Include as:"h1" by default; skip only when isTitleHtml=true and isTitleH1 not set
    include_h1 = is_title_h1 or not is_title_html

    title_align = (props.get("titleStyle") or {}).get("align") or {}
    alignment = {}
    for old_bp, new_bp in (("sm", "xs"), ("xl", "lg"), ("md", "md")):
        if old_bp in title_align:
            alignment[new_bp] = title_align[old_bp]
    if not alignment:
        alignment = {"xs": "left", "lg": "left"}

    title_text = props.get("title", "")
    if is_title_html:
        title_text = _topic_strip_html(title_text)

    title_obj = {"text": title_text}
    if include_h1:
        title_obj["as"] = "h1"

    info = {"alignment": alignment, "title": title_obj}
    description = props.get("description", "")
    if description:
        info["description"] = {"text": description}

    return make_node("widget", "WidgetHeading", None, info)


def _topic_bullet_widget(props: dict) -> dict:
    """WidgetBulletList for TopicSection — effects only when hasBulletAnimation:true."""
    bullet_lists = [
        {"title": {"text": item}}
        for item in (props.get("bulletPoints") or [])
    ]
    info = {"bulletLists": bullet_lists}
    if props.get("hasBulletAnimation"):
        info["effects"] = [{
            "delay":     {"value": 0, "unit": "s"},
            "trigger":   "inview",
            "animation": "slideInFromRight",
            "target":    "child",
        }]
    return make_node("widget", "WidgetBulletList", None, info)


def _topic_quote_widget(quote: str):
    """WidgetInlineText for quote — returns None when quote is empty."""
    if not quote:
        return None
    return make_node("widget", "WidgetInlineText", None, {
        "text": quote,
        "as":   "span",
    })


def _topic_button_widget(props: dict):
    """WidgetJoin when buttonType=join, else WidgetButtonGroup. None when no button."""
    button = props.get("button", "")
    if not button:
        return None

    if props.get("buttonType") == "join" or button == "joinwidget":
        return make_node("widget", "WidgetJoin", None, {})

    button_style = props.get("buttonStyle") or {}
    align        = button_style.get("align") or {}

    btn = {"title": button}
    link = props.get("buttonLink", "")
    if link:
        btn["to"] = link
    target = props.get("buttonTarget", "")
    if target:
        btn["target"] = target

    info = {"buttons": [btn]}

    _ALIGN_TO_FLEX = {"left": "flex-start", "right": "flex-end", "center": "center"}
    widget_align = {}
    for old_bp, new_bp in (("sm", "xs"), ("xl", "lg"), ("md", "md")):
        if old_bp in align:
            widget_align[new_bp] = _ALIGN_TO_FLEX.get(align[old_bp], align[old_bp])
    if widget_align:
        info["widgetAlignSelf"] = widget_align

    return make_node("widget", "WidgetButtonGroup", None, info)


def _topic_parse_pos(val):
    """Parse a CSS position/size string; return None if empty or None."""
    if val is None or val == "":
        return None
    return parse_size(val)


def _topic_media_multiimage(img_obj: dict) -> dict:
    """WidgetMedia for one imageObject in the multiImage absolute-positioning col."""
    image_style = img_obj.get("imageStyle") or {}
    border      = image_style.get("border") or {}
    position    = image_style.get("position") or {}
    size        = image_style.get("size") or {}
    bp_map      = (("sm", "xs"), ("xl", "lg"), ("md", "md"))

    src    = img_obj.get("image", "")
    alt    = img_obj.get("alt", "")
    mobile = img_obj.get("imageMobile")

    image_node = {"src": src, "alt": alt}
    if mobile:
        image_node["mobileSrc"] = mobile

    info = {"mediaType": "image", "image": image_node}

    # Border radius — all 4 corners equal
    radius_str = border.get("radius")
    if radius_str:
        r = parse_size(radius_str)
        info["mediaBorderTopLeftRadius"]     = r
        info["mediaBorderTopRightRadius"]    = r
        info["mediaBorderBottomLeftRadius"]  = r
        info["mediaBorderBottomRightRadius"] = r

    # Parallax effects: speed mapped from old -100..100 to new 0.5..1.5
    if img_obj.get("isParallax"):
        parallax = img_obj.get("parallaxConfig", 0)
        speed = round(0.5 + (parallax + 100) / 200, 2)
        info["effects"] = [{
            "duration":  {"value": 0.5, "unit": "s"},
            "delay":     {"value": 0,   "unit": "s"},
            "delayStep": {"value": 0.1, "unit": "s"},
            "trigger":   "parallax",
            "speed":     speed,
        }]

    info["widgetPosition"] = "absolute"

    # widgetWidth from imageStyle.size (sm→xs, xl→lg, md→md)
    widget_width = {}
    for old_bp, new_bp in bp_map:
        w = _topic_parse_pos((size.get(old_bp) or {}).get("width"))
        if w is not None:
            widget_width[new_bp] = w
    if widget_width:
        info["widgetWidth"] = widget_width

    # widgetTop/Right/Bottom/Left from imageStyle.position
    for direction, widget_key in (
        ("top",    "widgetTop"),
        ("right",  "widgetRight"),
        ("bottom", "widgetBottom"),
        ("left",   "widgetLeft"),
    ):
        bp_vals = {}
        for old_bp, new_bp in bp_map:
            v = _topic_parse_pos((position.get(old_bp) or {}).get(direction))
            if v is not None:
                bp_vals[new_bp] = v
        if bp_vals:
            info[widget_key] = bp_vals

    link = img_obj.get("link")
    if link:
        info["to"] = link

    return make_node("widget", "WidgetMedia", None, info)


def _topic_media_oneimage(props: dict) -> dict:
    """WidgetMedia for a single static image (oneImage layout — no absolute positioning)."""
    image_style = props.get("imageStyle") or {}
    size        = image_style.get("size") or {}
    align       = image_style.get("align") or {}

    src    = props.get("image", "")
    alt    = props.get("imageAlt", "")
    mobile = props.get("imageMobile")
    link   = props.get("link", "")
    target = props.get("imageTarget", "")

    image_node = {"src": src, "alt": alt}
    if mobile:
        image_node["mobileSrc"] = mobile

    info = {"mediaType": "image", "image": image_node}
    if link:
        info["to"] = link
    if target:
        info["target"] = target

    xl_align = align.get("xl")
    if xl_align:
        info["widgetAlignSelf"] = {"lg": xl_align}

    xl_width = _topic_parse_pos((size.get("xl") or {}).get("width"))
    if xl_width is not None:
        info["widgetWidth"] = {"lg": xl_width}

    xl_height = _topic_parse_pos((size.get("xl") or {}).get("height"))
    if xl_height is not None:
        info["widgetHeight"] = {"lg": xl_height}

    return make_node("widget", "WidgetMedia", None, info)


def _topic_facebook_widget(props: dict) -> dict:
    """WidgetFacebookPage — maps facebookLikeConfig.href/width/height + buttonLink."""
    fb_config = props.get("facebookLikeConfig") or {}

    # page: from facebookLikeConfig.href only (buttonLink is for the button widget, unrelated)
    page = fb_config.get("href", "")

    # iframeWidth.lg: explicit px when facebookLikeConfig.width is set, else 100%
    fb_width  = fb_config.get("width")
    iframe_lg = {"value": int(fb_width), "unit": "px"} if fb_width else {"value": 100, "unit": "%"}

    info = {
        "page":            page,
        "iframeWidth":     {"xs": {"value": 100, "unit": "%"}, "lg": iframe_lg},
        "widgetAlignSelf": {"lg": "center"},
    }

    # widgetWidth only when no explicit pixel width is given
    if not fb_width:
        info["widgetWidth"] = {"lg": "auto"}

    # iframeHeight.lg from facebookLikeConfig.height if set
    fb_height = fb_config.get("height")
    if fb_height:
        info["iframeHeight"] = {"lg": {"value": int(fb_height), "unit": "px"}}

    return make_node("widget", "WidgetFacebookPage", None, info)


def build_topicsection_section(props: dict) -> dict:
    image_type  = props.get("imageType", "")
    image_align = props.get("imageAlign", "")
    title       = props.get("title", "")

    # Section-level info
    section_info = {}
    if props.get("isFullScreen"):
        section_info["isFullwidth"] = True

    # Section padding from sectionStyle.padding (xl→lg, sm→xs, md→md)
    padding = (props.get("sectionStyle") or {}).get("padding") or {}
    pad_top, pad_bottom = {}, {}
    for old_bp, new_bp in (("xl", "lg"), ("sm", "xs"), ("md", "md")):
        bp = padding.get(old_bp) or {}
        if bp.get("top"):
            pad_top[new_bp]    = parse_size(bp["top"])
        if bp.get("bottom"):
            pad_bottom[new_bp] = parse_size(bp["bottom"])
    pad_top, pad_bottom = merge_classname2_padding(pad_top, pad_bottom, props.get("className2"))
    if pad_top:
        section_info["paddingTop"]    = pad_top
    if pad_bottom:
        section_info["paddingBottom"] = pad_bottom

    nickname = _topic_extract_nickname(title)

    # --- Content column ---
    col_children = [_topic_heading_widget(props)]

    if props.get("bulletPoints"):
        col_children.append(_topic_bullet_widget(props))

    quote_widget = _topic_quote_widget(props.get("quote", ""))
    if quote_widget:
        col_children.append(quote_widget)

    button_widget = _topic_button_widget(props)
    if button_widget:
        col_children.append(button_widget)

    content_col = make_node("col", None, None, {
        "order": {"xs": "2"},
        "span":  {"xs": "12", "lg": "6"},
    }, col_children)

    # --- Image column ---
    if image_type == "multiImage":
        image_col = make_node("col", None, None, {
            "span":     {"lg": "6", "xs": "12"},
            "order":    {"xs": "1"},
            "overflow": "visible",
            "height":   {"xs": {"value": 250, "unit": "px"}},
        }, [_topic_media_multiimage(img) for img in (props.get("imageObjects") or [])])

    elif image_type == "oneImage":
        image_col = make_node("col", None, None, {
            "span":  {"lg": "6", "xs": "12"},
            "order": {"xs": "1"},
        }, [_topic_media_oneimage(props)])

    elif image_type == "facebookWidget":
        image_col = make_node("col", None, None, {
            "span":  {"lg": "6", "xs": "12"},
            "order": {"xs": "1"},
        }, [_topic_facebook_widget(props)])

    else:  # instagramWidget or unknown → empty col
        image_col = make_node("col", None, None, {
            "span":  {"lg": "6", "xs": "12"},
            "order": {"xs": "1"},
        }, [])

    # imageRight → DOM [content, image]; else → [image, content]
    cols = [content_col, image_col] if image_align == "imageRight" else [image_col, content_col]
    row  = make_node("row", None, None, {}, cols)
    return make_node("section", "TextStack", nickname, section_info, [row])


# ---------------------------------------------------------------------------
# Section builder: BannerSection → Gallery / FeatureList / Banner
# ---------------------------------------------------------------------------

def _banner_extract_nickname(title: str):
    """Extract '[TAG]' prefix from '[B1]Banner Title' → '[B1]'."""
    t = title or ""
    if t.startswith("["):
        end = t.find("]")
        if end > 0:
            return t[:end + 1]
    return None


def _banner_alt_from_title(title: str) -> str:
    """Convert banner object title to alt text by removing spaces. 'banner 1' → 'banner1'."""
    return (title or "").replace(" ", "")


def _banner_effect_hover(props: dict):
    """Return effectHover dict when bannerAnimation is set, else None."""
    if props.get("bannerAnimation"):
        return {"item": "grow"}
    return None


def _banner_grid_cols(template: str) -> str:
    """Derive grid column count string from a desktop template string.

    Each sN or rN token = one visual column.

    r2r2r2   → 3 groups → "3"
    s1s1s1   → 3 groups → "3"
    s1s1r2   → 3 groups → "3"
    custom3-3 → no s/r tokens → fallback first digit → "3"
    """
    if not template:
        return "3"
    # Count all sN / rN groups — each group is one visual column
    groups = re.findall(r"[sr]\d+", template)
    if groups:
        return str(len(groups))
    # Fallback for templates like "custom3-3" that don't use s/r prefixes
    m = re.search(r"\d+", template)
    return m.group() if m else "3"


def _banner_gallery_list_widget(props: dict) -> dict:
    """WidgetGalleryList — used when hasModalClick is true."""
    banner_objects = props.get("bannerObjects") or []
    images = [
        {"src": b["image"], "alt": _banner_alt_from_title(b.get("title", ""))}
        for b in banner_objects
    ]
    template = props.get("bannerDesktopTemplate", "") or props.get("bannerTemplate", "")
    info = {
        "images":         images,
        "layoutGridCols": {"lg": _banner_grid_cols(template)},
        "isModalPopup":   True,
    }
    effect = _banner_effect_hover(props)
    if effect:
        info["effectHover"] = effect
    return make_node("widget", "WidgetGalleryList", None, info)


def _banner_banner_widget(props: dict) -> dict:
    """WidgetBanner — used when template has mixed s*/r* groups (e.g. s1s1r2)."""
    banner_objects = props.get("bannerObjects") or []
    banners = [
        {
            "mediaType": "image",
            "image":     {"src": b["image"]},
            "title":     {"text": _banner_alt_from_title(b.get("title", ""))},
            "to":        b.get("link", ""),
        }
        for b in banner_objects
    ]
    info = {
        "layout":  f"simple_equal_column-{len(banners)}",
        "banners": banners,
        "variant": "bg-image",
    }
    effect = _banner_effect_hover(props)
    if effect:
        info["effectHover"] = effect
    return make_node("widget", "WidgetBanner", None, info)


def _banner_feature_list_widget(props: dict) -> dict:
    """WidgetFeatureList — default banner widget (no modal, uniform-width template)."""
    banner_objects = props.get("bannerObjects") or []
    features = [
        {
            "mediaType":   "image",
            "image":       {"src": b["image"], "alt": _banner_alt_from_title(b.get("title", ""))},
            "to":          b.get("link", ""),
            "isShowMedia": True,
        }
        for b in banner_objects
    ]
    info = {"features": features}
    effect = _banner_effect_hover(props)
    if effect:
        info["effectHover"] = effect
    return make_node("widget", "WidgetFeatureList", None, info)


def build_bannersection_section(props: dict) -> dict:
    """Build BannerSection → section > row > col > [WidgetHeading, main_widget].

    Widget routing:
      hasModalClick=True            → WidgetGalleryList (modal popup grid)
      template has both 's' and 'r' → WidgetBanner      (mixed-size layout)
      else                          → WidgetFeatureList  (uniform equal-width images)

    section.kind:
      bannerDesktopTemplate starts with 'r' → null
      otherwise                             → "About"
    """
    template = props.get("bannerDesktopTemplate", "") or props.get("bannerTemplate", "")

    # section kind: r* templates → null (grid), others → "About" (mixed/custom layouts)
    kind = None if (not template or template.startswith("r")) else "About"

    nickname = _banner_extract_nickname(props.get("title", ""))

    # Main content widget
    if props.get("hasModalClick"):
        main_widget = _banner_gallery_list_widget(props)
    elif "s" in template and "r" in template:
        main_widget = _banner_banner_widget(props)
    else:
        main_widget = _banner_feature_list_widget(props)

    # WidgetHeading (always when title is present)
    col_children = []
    title_text = (props.get("title") or "").strip()
    if title_text:
        h_info = {"title": {"text": title_text}}
        desc_text = (props.get("description") or "").strip()
        if desc_text:
            h_info["description"] = {"text": desc_text}
        col_children.append(make_node("widget", "WidgetHeading", None, h_info))

    col_children.append(main_widget)

    col = make_node("col", None, None, {}, col_children)
    row = make_node("row", None, None, {}, [col])
    return make_node("section", kind, nickname, {}, [row])


# ---------------------------------------------------------------------------
# Section builder: PromotionSlick → PromotionList
# ---------------------------------------------------------------------------

def build_promotionslick_section(props: dict) -> dict:
    """Build PromotionSlick → section > row > col > [WidgetHeading, WidgetPromotionList, WidgetButtonGroup?].

    isUseSlick=True  → layoutGrid carousel + layoutCard effectHover when bannerAnimation set
    isUseSlick=False → WidgetPromotionList with empty info {}
    isFullScreen     → section.info.isFullwidth: true
    """
    nickname = _banner_extract_nickname(props.get("title", ""))

    section_info = {}
    if props.get("isFullScreen"):
        section_info["isFullwidth"] = True

    col_children = []

    # WidgetHeading
    title_text = (props.get("title") or "").strip()
    if title_text:
        h_info = {"title": {"text": title_text}}
        desc_text = (props.get("description") or "").strip()
        if desc_text:
            h_info["description"] = {"text": desc_text}
        col_children.append(make_node("widget", "WidgetHeading", None, h_info))

    # WidgetPromotionList
    promo_info = {}
    if props.get("isUseSlick"):
        promo_info["layoutGrid"] = {
            "template":               "carousel",
            "isCarouselOverflowRight": True,
            "isCarouselArrows":        True,
            "isCarouselScrollbar":     True,
        }
        if props.get("bannerAnimation"):
            promo_info["layoutCard"] = {"effectHover": {"item": "grow"}}
    col_children.append(make_node("widget", "WidgetPromotionList", None, promo_info))

    # WidgetButtonGroup (when button text is present)
    button_text = (props.get("button") or "").strip()
    if button_text:
        col_children.append(make_node("widget", "WidgetButtonGroup", None, {
            "buttons": [{"title": button_text, "to": props.get("buttonLink", "")}],
        }))

    col = make_node("col", None, None, {}, col_children)
    row = make_node("row", None, None, {}, [col])
    return make_node("section", None, nickname, section_info, [row])


# ---------------------------------------------------------------------------
# Section builder: CouponSlick → CouponList
# ---------------------------------------------------------------------------

def build_couponslick_section(props: dict) -> dict:
    """Build CouponSlick → section > row > col > [WidgetHeading, WidgetCouponList, WidgetButtonGroup?].

    isUseSlick=True  → layoutGrid carousel (same 3 flags as PromotionSlick)
    isUseSlick=False → WidgetCouponList with empty info {}
    isFullScreen     → section.info.isFullwidth: true
    """
    nickname = _banner_extract_nickname(props.get("title", ""))

    section_info = {}
    if props.get("isFullScreen"):
        section_info["isFullwidth"] = True

    col_children = []

    # WidgetHeading
    title_text = (props.get("title") or "").strip()
    if title_text:
        h_info = {"title": {"text": title_text}}
        desc_text = (props.get("description") or "").strip()
        if desc_text:
            h_info["description"] = {"text": desc_text}
        col_children.append(make_node("widget", "WidgetHeading", None, h_info))

    # WidgetCouponList
    coupon_info = {}
    if props.get("isUseSlick"):
        coupon_info["layoutGrid"] = {
            "template":               "carousel",
            "isCarouselOverflowRight": True,
            "isCarouselScrollbar":     True,
            "isCarouselArrows":        True,
        }
    col_children.append(make_node("widget", "WidgetCouponList", None, coupon_info))

    # WidgetButtonGroup (when button text is present)
    button_text = (props.get("button") or "").strip()
    if button_text:
        col_children.append(make_node("widget", "WidgetButtonGroup", None, {
            "buttons": [{"title": button_text, "to": props.get("buttonLink", "")}],
        }))

    col = make_node("col", None, None, {}, col_children)
    row = make_node("row", None, None, {}, [col])
    return make_node("section", None, nickname, section_info, [row])


def build_contactussection_section(props: dict) -> dict:
    """Build ContactusSection → section(kind=Contact) > row > col > [WidgetHeading, WidgetForm].

    WidgetHeading always present when title is non-empty (with optional description).
    WidgetForm always added with empty info.
    """
    nickname = _banner_extract_nickname(props.get("title", ""))

    col_children = []

    # WidgetHeading
    title_text = (props.get("title") or "").strip()
    if title_text:
        h_info = {"title": {"text": title_text}}
        desc_text = (props.get("description") or "").strip()
        if desc_text:
            h_info["description"] = {"text": desc_text}
        col_children.append(make_node("widget", "WidgetHeading", None, h_info))

    # WidgetForm (always)
    col_children.append(make_node("widget", "WidgetForm", None, {}))

    col = make_node("col", None, None, {}, col_children)
    row = make_node("row", None, None, {}, [col])
    return make_node("section", "Contact", nickname, {}, [row])


def build_faqssection_section(props: dict) -> dict:
    """Build FaqsSection → section(kind=Faq) > row > col > [WidgetHeading, (WidgetTextStack + WidgetAccordion)*].

    For each faqsObject: one WidgetTextStack (category name) + one WidgetAccordion (q/a list).
    Question text is trimmed then always has "?" appended (if not already ending with "?").
    isDarkMode is handled by the global post-processor in convert_section().
    """
    nickname = _banner_extract_nickname(props.get("title", ""))

    col_children = []

    # WidgetHeading
    title_text = (props.get("title") or "").strip()
    if title_text:
        h_info = {"title": {"text": title_text}}
        desc_text = (props.get("description") or "").strip()
        if desc_text:
            h_info["description"] = {"text": desc_text}
        col_children.append(make_node("widget", "WidgetHeading", None, h_info))

    # One WidgetTextStack + WidgetAccordion per faqsObject
    for faq_obj in (props.get("faqsObjects") or []):
        name = (faq_obj.get("name") or "").strip()
        col_children.append(make_node("widget", "WidgetTextStack", None, {
            "items": [{
                "itemType":    "text",
                "textVariant": "title",
                "text":        {"text": name},
            }]
        }))
        items = []
        for qa in (faq_obj.get("list") or []):
            q_text = (qa.get("q") or "").strip()
            if q_text and not q_text.endswith("?"):
                q_text += "?"
            items.append({
                "title":   {"text": q_text},
                "content": qa.get("a") or "",
            })
        col_children.append(make_node("widget", "WidgetAccordion", None, {"items": items}))

    col = make_node("col", None, None, {}, col_children)
    row = make_node("row", None, None, {}, [col])
    return make_node("section", "Faq", nickname, {}, [row])


# ---------------------------------------------------------------------------
# Zone builder: FooterSection → footer_zone
# ---------------------------------------------------------------------------

_FOOTER_DEFAULT_NAV_ITEMS: list = [
    {"text": "สินค้าทั้งหมด", "to": "/category"},
    {"text": "สินค้ามาใหม่",  "to": "/category"},
    {"text": "สินค้าขายดี",   "to": "/category"},
    {"text": "สินค้าแนะนำ",   "to": "/category"},
    {"text": "สินค้าลดราคา",  "to": "/category"},
]

_FOOTER_DEFAULT_COPYRIGHT = (
    "Copyright © {{YEAR_AD}} by {{SHOP_NAME}} All rights reserved."
)


def _footer_map_nav_items(list_objects) -> list:
    """Map v3 customFooterListObjects {title,link} to v4 navs {text,to}.
    Returns the Thai product default list when list_objects is absent/empty."""
    if not list_objects:
        return _FOOTER_DEFAULT_NAV_ITEMS
    return [{"text": item.get("title", ""), "to": item.get("link", "")}
            for item in list_objects]


def _footer_brand_info(props: dict) -> dict:
    left_align = props.get("leftAreaAlign", "left")
    info: dict = {"textAlign": {"xs": "center", "lg": left_align}}
    if props.get("isImageLogo"):
        info["isShowImage"] = True
        if props.get("logo"):
            info["image"] = {"src": props["logo"]}
        height = (props.get("logoStyle") or {}).get("height")
        if height:
            info["mediaHeight"] = {"lg": parse_size(height)}
    else:
        if props.get("title"):
            info["title"] = {"text": props["title"]}
        if props.get("slogan"):
            info["description"] = {"text": props["slogan"]}
    return make_node("widget", "WidgetBrandInfo", None, info)


def _footer_nav_list(navs: list, title: str) -> dict:
    return make_node("widget", "WidgetNavList", None, {
        "navs": navs,
        "title": {"text": title},
        "type": "list",
        "textAlign": {"sm": "left", "lg": "left"},
    })


def _footer_account_nav() -> dict:
    return make_node("widget", "WidgetNavList", None, {
        "preset": "account",
        "type": "list",
        "textAlign": {"sm": "left", "lg": "left"},
        "title": {"text": "บัญชีของฉัน"},
    })


def _footer_social_contact(include_distribute: bool) -> dict:
    info: dict = {
        "isShowAddress": False,
        "isShowContact": False,
        "isShowSocial": True,
        "isShowWebInfo": False,
        "isShowSocialTitle": True,
        "socialTitle": "ติดตามเรา",
    }
    if include_distribute:
        info["webSocialDistribute"] = {"xs": "flex-start", "lg": "flex-start"}
    return make_node("widget", "WidgetContactInfo", None, info)


def _footer_contact_info(props: dict, preset: int) -> dict:
    has_address = "addressText" in props
    info: dict = {"contactTitle": "ติดต่อเรา"}
    if preset == 2:
        info["contactLinkVariant"] = "accent"
    info["webContactDistribute"] = {"sm": "flex-start", "lg": "flex-start"}
    info["isShowAddress"] = has_address
    info["isShowWebInfo"] = False
    info["isShowSocial"] = False
    if has_address:
        info["isShowAddressTitle"] = False
        info["isShowAddressTel"] = False
        info["isShowAddressMap"] = False
    return make_node("widget", "WidgetContactInfo", None, info)


def _footer_col(span: dict, h_align: dict, widgets: list,
                vert_align: bool = True) -> dict:
    col_info: dict = {}
    if vert_align:
        col_info["verticalAlign"] = "start"
    if span:
        col_info["span"] = span
    if h_align:
        col_info["horizontalAlign"] = h_align
    return make_node("col", None, None, col_info, widgets)


def _footer_h_align(props: dict) -> dict:
    align = props.get("leftAreaAlign", "left")
    h: dict = {"xs": "center"}
    if align == "center":
        h["lg"] = "center"
    return h


def _footer_brand_widgets(props: dict) -> list:
    widgets = [_footer_brand_info(props)]
    if props.get("isSocialIcon"):
        widgets.append(make_node("widget", "WidgetSocial", None, {}))
    widgets.append(make_node("widget", "WidgetJoin", None, {}))
    return widgets


def _footer_copyright_row(props: dict) -> dict:
    """Build copyright row appended to every footer section."""
    if props.get("isCustomCopyright"):
        html = props.get("copyrightNotice", "")
    else:
        html = _FOOTER_DEFAULT_COPYRIGHT
    widget = make_node("widget", "WidgetRichText", None, {
        "html": html,
        "textAlign": {"lg": "center", "xs": "center"},
    })
    col = make_node("col", None, "", {}, [widget])
    row = make_node("row", None, "", {}, [col])
    return row


def _footer_custom_nav_cols(props: dict, nav_span: dict) -> list:
    """Build nav columns in order: cf1 → cf2 → cf3, skipping those not shown."""
    cols = []
    # cf1
    if props.get("isCustomFooter"):
        title = props.get("customFooterTitle", "") or "ลิงก์แนะนำ"
        navs  = _footer_map_nav_items(props.get("customFooterListObjects"))
        cols.append(_footer_col(nav_span, {}, [_footer_nav_list(navs, title)]))
    # cf2
    if props.get("isCustomFooter2"):
        title = props.get("customFooter2Title", "") or "Products"
        navs  = _footer_map_nav_items(props.get("customFooter2ListObjects"))
        cols.append(_footer_col(nav_span, {}, [_footer_nav_list(navs, title)]))
    # cf3
    if props.get("isCustomFooter3"):
        title = props.get("customFooter3Title", "") or "เมนูแนะนำ"
        navs  = _footer_map_nav_items(props.get("customFooter3ListObjects"))
        cols.append(_footer_col(nav_span, {}, [_footer_nav_list(navs, title)]))
    return cols


def _footer_fixed_cols(props: dict, social_span: dict, account_span: dict,
                        contact_span: dict, include_distribute: bool,
                        preset: int) -> list:
    """Build social / account / contact columns, skipping those not shown."""
    cols = []
    if props.get("isSocialPane", True):
        cols.append(_footer_col(social_span, {},
                                [_footer_social_contact(include_distribute)]))
    if props.get("isAccountPane", True):
        cols.append(_footer_col(account_span, {}, [_footer_account_nav()]))
    if props.get("isContactPane", True):
        cols.append(_footer_col(contact_span, {},
                                [_footer_contact_info(props, preset)]))
    return cols


def _footer_preset1(props: dict) -> dict:
    h_align   = _footer_h_align(props)
    brand_col = _footer_col(
        {"xs": "12", "md": "12", "lg": "6"}, h_align,
        _footer_brand_widgets(props),
    )
    nav_span     = {"xs": "6", "md": "4", "lg": "1"}
    account_span = {"md": "4", "lg": "1"}
    contact_span = {"md": "4", "lg": "1"}
    cols = ([brand_col]
            + _footer_custom_nav_cols(props, nav_span)
            + _footer_fixed_cols(props, nav_span, account_span, contact_span,
                                  True, 1))
    section_info: dict = {}
    if props.get("isDarkMode"):
        section_info["colorScheme"] = "color-scheme-inverse"
    row = make_node("row", None, None, {}, cols)
    return make_node("section", "footer", "[preset1]", section_info,
                     [row, _footer_copyright_row(props)])


def _footer_preset2(props: dict) -> dict:
    h_align   = _footer_h_align(props)
    brand_col = _footer_col({"lg": "4"}, h_align, _footer_brand_widgets(props))
    nav_span     = {"xs": "6", "md": "4", "lg": "1"}
    account_span = {"md": "4", "lg": "2", "2xl": "2"}
    contact_span = {"md": "4", "lg": "2", "2xl": "2"}
    cols = ([brand_col]
            + _footer_custom_nav_cols(props, nav_span)
            + _footer_fixed_cols(props, nav_span, account_span, contact_span,
                                  True, 2))
    section_info: dict = {}
    if props.get("isDarkMode"):
        section_info["colorScheme"] = "color-scheme-inverse"
    row = make_node("row", None, None, {}, cols)
    return make_node("section", "footer", "[preset2]", section_info,
                     [row, _footer_copyright_row(props)])


def _footer_preset3(props: dict) -> dict:
    h_align       = _footer_h_align(props)
    brand_widgets = _footer_brand_widgets(props)
    verify_node   = make_node("widget", "WidgetVerify", None, {})
    if not props.get("isShowVerifyBadge"):
        verify_node["remove"] = True
    brand_widgets.append(verify_node)
    brand_col = _footer_col({}, h_align, brand_widgets)
    row1 = make_node("row", None, None, {}, [brand_col])

    nav_span     = {"xs": "6", "md": "3", "lg": "3"}
    account_span = {"md": "3", "lg": "3"}
    contact_span = {"md": "3", "lg": "3"}
    row2_cols = (_footer_custom_nav_cols(props, nav_span)
                 + _footer_fixed_cols(props, nav_span, account_span,
                                       contact_span, False, 3))
    row2 = make_node("row", None, None, {}, row2_cols)

    section_info: dict = {}
    if props.get("isDarkMode"):
        section_info["colorScheme"] = "color-scheme-inverse"
    return make_node("section", "footer", "[preset3]", section_info,
                     [row1, row2, _footer_copyright_row(props)])


def build_footer_section(props: dict) -> dict:
    """Convert FooterSection props → v4 footer_zone node."""
    preset_id = props.get("presetId", 1)
    if preset_id == 2:
        section = _footer_preset2(props)
    elif preset_id == 3:
        section = _footer_preset3(props)
    else:
        section = _footer_preset1(props)
    footer_zone = make_node("page", "footer", "Footer", {})
    footer_zone["children"] = [section]
    return footer_zone


def convert_footer(footer_json: dict) -> dict:
    """Convert v3 footer dict ({"FooterSection": {...}}) → v4 footer_zone."""
    props = footer_json.get("FooterSection") if isinstance(footer_json, dict) else {}
    return build_footer_section(props or {})


# ---------------------------------------------------------------------------
# HeaderSection — zone builder
# ---------------------------------------------------------------------------

def _rewrite_nav_link(link: str) -> str:
    return "/category" if link == "/search" else link


def _header_dropdown_content_item(s: dict) -> dict:
    item = {"text": s.get("title", ""), "to": _rewrite_nav_link(s.get("link", ""))}
    target = s.get("target")
    if target is not None:
        item["target"] = target if target else "_self"
    return item


def _header_menu_items(menu_list: list) -> tuple:
    """Returns (menu_items_list, has_any_dropdown)."""
    items = []
    has_dropdown = False
    for m in (menu_list or []):
        title = m.get("title", "")
        link = m.get("link", "")
        if not m.get("isShowSubMenu"):
            items.append({"text": title, "to": _rewrite_nav_link(link)})
            continue
        has_dropdown = True
        to = _rewrite_nav_link(link) if link else None
        item = {"text": title}
        if to:
            item["to"] = to
        item["isDropdown"] = True
        menu_type = m.get("type")
        template = m.get("template", "")
        if menu_type == "manual" and template == "default":
            item["dropdownType"] = "simpleMenu"
            item["dropdownContent"] = [_header_dropdown_content_item(s)
                                        for s in m.get("submenu", [])]
        elif menu_type == "manual" and template == "custom":
            item["dropdownType"] = "megaMenu"
            item["dropdownContent"] = _mega_dc_from_submenu_mega(m.get("submenuMega") or {})
            item["dropdownWidth"] = "fullWidth"
            hierarchy = m.get("hierarchyLevel", "")
            if hierarchy != "" and hierarchy is not None:
                item["maxHierarchyNumber"] = hierarchy
        elif menu_type == "auto_category" and template == "showTextLevelTemplate":
            item["dropdownType"] = "flyout"
            if "cat_id" in m and "submenu" not in m:
                item["category_id"] = str(m["cat_id"])
            hierarchy = m.get("hierarchyLevel", "")
            if hierarchy != "" and hierarchy is not None:
                item["maxHierarchyNumber"] = hierarchy
        elif menu_type == "auto_category":
            cat_id = m.get("cat_id")
            item["dropdownType"] = "megaMenu"
            item["dropdownContent"] = _mega_dc_simple(
                cat_id if isinstance(cat_id, int) and cat_id > 0 else None)
            item["dropdownWidth"] = "boxWidth" if template == "showTextTemplate" else "fullWidth"
        # no type or unrecognised template: bare isDropdown only
        items.append(item)
    return items, has_dropdown


def _mega_dc_simple(cat_id=None) -> dict:
    """dropdownContent for auto_category mega: section > row > col > WidgetNavList."""
    nav_info = {
        "type": "list",
        "layoutStackDirection": {"xs": "column", "lg": "column"},
        "preset": "category",
    }
    if cat_id is not None:
        nav_info["category_id"] = str(cat_id)
    return {
        "id": None, "type": "section", "kind": None, "nickname": None,
        "info": {"colorScheme": "color-scheme-main"}, "style": [],
        "children": [{
            "id": None, "type": "row", "kind": None, "nickname": None,
            "info": [], "style": [],
            "children": [{
                "id": None, "type": "col", "kind": None, "nickname": None,
                "info": [], "style": [],
                "children": [{
                    "id": None, "type": "widget", "kind": "WidgetNavList",
                    "nickname": None, "info": nav_info, "style": [],
                }],
            }],
        }],
    }


def _mega_col_widgets(entries: list) -> list:
    """Build WidgetMedia / WidgetNavList widgets from one submenuMega column."""
    widgets = []
    for entry in entries:
        if not entry:
            continue
        image = entry.get("image")
        title = entry.get("title", "")
        children = entry.get("children")
        if image:
            widgets.append({
                "id": None, "type": "widget", "kind": "WidgetMedia",
                "nickname": None,
                "info": {"mediaType": "image", "image": {"src": image}},
                "style": [],
            })
        has_title = bool(title)
        has_children = bool(children)
        if has_title or has_children:
            nav_info = {
                "type": "list",
                "layoutStackDirection": {"xs": "column", "lg": "column"},
            }
            if has_title:
                nav_info["title"] = {"text": title}
            if has_children:
                nav_info["navs"] = [
                    {"text": c.get("title", ""),
                     "to": _rewrite_nav_link(c.get("link") or "")}
                    for c in children
                ]
            widgets.append({
                "id": None, "type": "widget", "kind": "WidgetNavList",
                "nickname": None, "info": nav_info, "style": [],
            })
    return widgets


def _mega_dc_from_submenu_mega(submenu_mega: dict) -> dict:
    """dropdownContent for manual mega: section > row > cols from submenuMega."""
    cols = []
    for col_name in ["column1", "column2", "column3", "column4", "column5", "column6"]:
        entries = submenu_mega.get(col_name, [])
        if not entries:
            continue
        cols.append({
            "id": None, "type": "col", "kind": None, "nickname": col_name,
            "info": {"verticalAlign": {"lg": "flex-start"}}, "style": [],
            "children": _mega_col_widgets(entries),
        })
    return {
        "id": None, "type": "section", "kind": None, "nickname": None,
        "info": {"colorScheme": "color-scheme-main"}, "style": [],
        "children": [{
            "id": None, "type": "row", "kind": None, "nickname": None,
            "info": [], "style": [],
            "children": cols,
        }],
    }


def _is_dark_hex(color: str) -> bool:
    """Return True if hex color has low luminance (dark color like #000000)."""
    h = (color or "").lstrip("#")
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    if len(h) != 6:
        return False
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (r + g + b) < 382
    except ValueError:
        return False


def _header_extra_section_info(props: dict) -> dict:
    info = {}
    if props.get("isFullScreen"):
        info["isFullwidth"] = True
    if props.get("isShowSubMenuPane"):
        info["headerZIndex"] = 11
    pane = props.get("headerPane") or {}
    is_dark = pane.get("isDarkMode")
    bg_color = ((pane.get("sectionStyle") or {}).get("bgColor") or "").strip()
    height_preset = pane.get("heightPresetId")
    _HEIGHTS = {1: 60, 2: 70, 3: 80, 4: 90}

    if props.get("isBgTransparent"):
        info["stickyType"] = "always"
        font_color = (props.get("bgTransparentFontColor") or "").strip()
        info["colorSchemeFixTop"] = "color-scheme-main" if _is_dark_hex(font_color) else "color-scheme-inverse"
        info["headerBgColorFixTop"] = "transparent"
        info["colorSchemeFixScroll"] = "color-scheme-inverse" if is_dark else "color-scheme-main"
        if bg_color:
            info["headerBgColorFixScroll"] = bg_color.lower()
        info["fixPaths"] = ["/"]
    else:
        if (props.get("subHeaderPane") or {}).get("isFixTop"):
            info["stickyType"] = "always"
        info["colorScheme"] = "color-scheme-inverse" if is_dark else "color-scheme-main"
        if bg_color:
            info["headerBgColor"] = bg_color.lower()

    if height_preset:
        px = _HEIGHTS.get(height_preset)
        if px:
            info["headerHeight"] = {"xs": {"value": px, "unit": "px"}, "lg": {"value": px, "unit": "px"}}
    return info


def _header_logo_info(props: dict, base_info: dict = None) -> dict:
    info = dict(base_info) if base_info else {}
    if props.get("isImageLogo"):
        logo = (props.get("logo") or "").strip()
        logo_side = (props.get("logoSideMenu") or logo).strip()
        if logo:
            info["brandImageMode"] = "custom"
            info["brandImage"] = {"src": logo, "mobileSrc": logo_side}
        logo_style = props.get("logoStyle") or {}
        height = logo_style.get("height") or ""
        if height:
            size = parse_size(height)
            info["widgetHeight"] = {"xs": size, "lg": size}
    elif (props.get("headerPane") or {}).get("isDarkMode"):
        info["brandImageMode"] = "dark"
    return info


def _header_mnl_extra(props: dict) -> dict:
    """Extra WidgetMainNavigationList fields: drawer logo + side pane color scheme."""
    extra = {}
    if props.get("isImageLogo"):
        logo = (props.get("logo") or "").strip()
        logo_side = (props.get("logoSideMenu") or logo).strip()
        if logo:
            extra["isDrawerLogo"] = True
            extra["drawerLogoMode"] = "custom"
            extra["drawerLogo"] = {"src": logo_side or logo}
    side = props.get("sideMenuPane") or {}
    dark = side.get("isDarkMode")
    if dark is not None:
        extra["sidePaneColorScheme"] = "color-scheme-main" if dark else "color-scheme-inverse"
    return extra


def _subheader_section(props: dict) -> dict:
    sub_pane = props.get("subHeaderPane") or {}
    is_dark = sub_pane.get("isDarkMode")
    color = "color-scheme-inverse" if is_dark else "color-scheme-main"

    navs = []
    for m in (props.get("subMenuListObjects") or []):
        title = m.get("title") or ""
        if not title:
            continue
        entry = {"text": title}
        link = (m.get("link") or "").strip()
        if link:
            entry["to"] = link
        target = (m.get("target") or "").strip()
        if target:
            entry["target"] = target
        navs.append(entry)

    preset = sub_pane.get("alignPresetId")
    distribute_map = {1: "flex-start", 2: "center", 3: "flex-end"}

    navlist_info = {
        "navs": navs,
        "type": "list",
        "layoutStack": {"isOverflowX": True},
        "layoutStackDirection": {"xs": "row", "lg": "row"},
        "layoutStackWrap": {"xs": "nowrap"},
        "layoutStackAlignment": {"xs": "center"},
        "layoutStackGap": {"xs": {"value": 2, "unit": "em"}, "lg": {"value": 2, "unit": "em"}},
    }
    if preset in distribute_map:
        val = distribute_map[preset]
        navlist_info["layoutStackDistribute"] = {"lg": val, "xs": val}

    section_info = {"colorScheme": color}
    if sub_pane.get("isFixTop"):
        section_info["stickyType"] = "always"
    bg_color = ((sub_pane.get("sectionStyle") or {}).get("bgColor") or "").strip()
    if bg_color:
        section_info["headerBgColor"] = bg_color.lower()
    height_preset = sub_pane.get("heightPresetId")
    if height_preset:
        _SUB_HEIGHTS = {1: 40, 2: 50, 3: 60, 4: 70}
        px = _SUB_HEIGHTS.get(height_preset)
        if px:
            section_info["headerHeight"] = {"xs": {"value": px, "unit": "px"}, "lg": {"value": px, "unit": "px"}}

    is_transparent = props.get("isBgTransparent")
    row_info = {} if is_transparent else {"headerGap": {"xs": {"value": 10, "unit": "px"}}}
    row = make_node("row", None, None, row_info,
                    [make_node("col", None, None, {},
                               [make_node("widget", "WidgetNavList", None, navlist_info)])])
    return make_node("section", "header", "subHeader-default", section_info, [row])


def _searchbox_text_stack(area_config: dict):
    title = (area_config.get("title") or "").strip()
    subtitle = (area_config.get("subtitle") or "").strip()
    link = (area_config.get("Link ข้อความหลัก") or "").strip()

    items = []
    if title:
        item = {"itemType": "text",
                "text": {"text": title, "typoStyle": "typo_heading_medium"}}
        if link:
            item["to"] = link
        items.append(item)
    if subtitle:
        items.append({"itemType": "text", "text": {"text": subtitle}})

    if not items:
        return None
    return {"items": items, "gap": {"lg": {"value": 0.5, "unit": "em"}}}


def _searchbox_bullet_list(image_objects: list):
    bullets = []
    for obj in (image_objects or []):
        media = obj.get("mediaType", "")
        if media == "iconfont":
            entry = {"mediaType": "icon", "icon": {"name": obj["iconfont"]}}
        elif media == "image":
            entry = {"mediaType": "image",
                     "image": {"src": obj["image"], "alt": obj.get("title", "")}}
        else:
            continue
        link = (obj.get("link") or "").strip()
        if link:
            entry["to"] = link
        target = obj.get("target") or ""
        if target:
            entry["target"] = target
        bullets.append(entry)

    if not bullets:
        return None
    return {
        "bulletLists": bullets,
        "elementBulletListDirection": "row",
        "elementBulletListAlign": "center",
        "layout": "grid",
        "bulletGridCols": {"lg": "2"},
    }


def _searchbox_side_col(area_config: dict) -> dict:
    image_objects = area_config.get("imageObjects") or []
    title_position = area_config.get("titlePosition") or ""

    bullet_info = _searchbox_bullet_list(image_objects)
    text_info = _searchbox_text_stack(area_config)

    children = []
    if title_position == "left":
        if text_info:
            children.append(make_node("widget", "WidgetTextStack", None, text_info))
        if bullet_info:
            children.append(make_node("widget", "WidgetBulletList", None, bullet_info))
    else:
        if bullet_info:
            children.append(make_node("widget", "WidgetBulletList", None, bullet_info))
        if text_info:
            children.append(make_node("widget", "WidgetTextStack", None, text_info))

    return make_node("col", None, None, {"headerDisplay": {"xs": "none"}}, children)


def _searchbox_section(search_box: dict) -> dict:
    placeholder = (search_box.get("placeholder") or "").strip()
    search_info = {}
    if placeholder:
        search_info["placeholder"] = placeholder
    search_info["submitButton"] = {"title": "ค้นหา", "variant": "primary"}
    search_info["searchTextSubmitOrder"] = "0"

    left_config = search_box.get("leftAreaConfig")
    right_config = search_box.get("rightAreaConfig")

    if left_config is not None or right_config is not None:
        left_col = _searchbox_side_col(left_config or {})
        center_col = make_node("col", None, None, {},
                               [make_node("widget", "WidgetSearchForm", None, search_info)])
        right_col = _searchbox_side_col(right_config or {})
        row = make_node("row", None, None, {}, [left_col, center_col, right_col])
    else:
        row = make_node("row", None, None, {},
                        [make_node("col", None, None, {},
                                   [make_node("widget", "WidgetSearchForm", None, search_info)])])

    is_dark = search_box.get("isDarkMode")
    color = "color-scheme-inverse" if is_dark else "color-scheme-main"
    section_info = {"colorScheme": color}
    bg_color = ((search_box.get("sectionStyle") or {}).get("bgColor") or "").strip()
    if bg_color:
        section_info["headerBgColor"] = bg_color.lower()

    return make_node("section", "header", "searchBox-default", section_info, [row])


def _header_section(nickname: str, row: dict, extra_info: dict = None, include_padding_x: bool = True) -> dict:
    info = {}
    if include_padding_x:
        info["headerContainerPaddingX"] = {"xs": {"value": 0, "unit": "px"}, "lg": {"value": 0, "unit": "px"}}
    if extra_info:
        info.update(extra_info)
    return make_node("section", "header", nickname, info, [row])


def _header_preset1(props: dict) -> dict:
    menus = props.get("menuListObjects", [])
    items, has_dropdown = _header_menu_items(menus)
    mnl_info = {
        "menuItems": items,
        "widgetMnlZIndex": 2,
        "widgetMnlOrder": {"xs": "1"},
        "drawerHeaderDistribute": {"xs": "flex-end"},
    }
    if has_dropdown:
        mnl_info["dropdownActivate"] = "hover"
        mnl_info["isShowDropdownIconOnHover"] = True
    mnl_info.update(_header_mnl_extra(props))
    logo_nav_col = make_node("col", None, None, {
        "span": {"xs": "8", "lg": "8"},
        "headerHorizontalAlign": {"lg": "flex-start", "xs": "flex-start"},
        "headerVerticalAlign": {"lg": "center", "xs": "center"},
        "headerZIndex": 2,
    }, [
        make_node("widget", "WidgetHeaderLogo", None,
                  _header_logo_info(props, {"widgetOrder": {"xs": "2"}})),
        make_node("widget", "WidgetMainNavigationList", None, mnl_info),
    ])
    action_col = make_node("col", None, None, {
        "span": {"xs": "4", "lg": "4"},
        "headerHorizontalAlign": {"xs": "flex-end", "lg": "flex-end"},
        "headerVerticalAlign": {"lg": "center", "xs": "center"},
    }, [
        make_node("widget", "WidgetHeaderActionSearch", None, {}),
        make_node("widget", "WidgetHeaderActionCart", None, {}),
        make_node("widget", "WidgetHeaderActionUser", None,
                  {"actionTextDisplay": {"xs": "none"}}),
    ])
    return _header_section("SimpleHeader1",
                           make_node("row", None, None, {}, [logo_nav_col, action_col]),
                           _header_extra_section_info(props),
                           include_padding_x=not props.get("isBgTransparent"))


def _header_preset2(props: dict) -> dict:
    menus = props.get("menuListObjects", [])
    items, has_dropdown = _header_menu_items(menus)
    mnl_info = {"menuItems": items, "drawerHeaderDistribute": {"xs": "flex-end"}}
    if has_dropdown:
        mnl_info["dropdownActivate"] = "hover"
        mnl_info["isShowDropdownIconOnHover"] = True
    mnl_info.update(_header_mnl_extra(props))
    logo_col = make_node("col", None, None, {
        "headerHorizontalAlign": {"xs": "start", "lg": "start"},
        "span": {"lg": 3, "xs": "5"},
        "headerOrder": {"xs": "2"},
    }, [make_node("widget", "WidgetHeaderLogo", None, _header_logo_info(props))])
    nav_col = make_node("col", None, None, {
        "span": {"lg": 6, "xs": "2"},
        "headerZIndex": 2,
        "headerHorizontalAlign": {"xs": "center", "lg": "center"},
        "headerOrder": {"xs": "1"},
    }, [make_node("widget", "WidgetMainNavigationList", None, mnl_info)])
    action_col = make_node("col", None, None, {
        "span": {"lg": 3, "xs": "5"},
        "headerHorizontalAlign": {"xs": "flex-end", "lg": "flex-end"},
        "headerVerticalAlign": {"lg": "center", "xs": "center"},
        "headerOrder": {"xs": "3"},
    }, [
        make_node("widget", "WidgetHeaderActionSearch", None, {}),
        make_node("widget", "WidgetHeaderActionCart", None, {}),
        make_node("widget", "WidgetHeaderActionUser", None,
                  {"actionTextDisplay": {"xs": "none"}}),
    ])
    return _header_section("SimpleHeader2",
                           make_node("row", None, None, {}, [logo_col, nav_col, action_col]),
                           _header_extra_section_info(props),
                           include_padding_x=not props.get("isBgTransparent"))


def _header_preset3(props: dict) -> dict:
    menus = props.get("menuListObjects", [])
    items, has_dropdown = _header_menu_items(menus)
    mnl_info = {
        "menuItems": items,
        "drawerHeaderDistribute": {"xs": "flex-end", "lg": "flex-end"},
        "widgetMnlZIndex": 2,
        "widgetMnlOrder": {"xs": "2"},
    }
    if has_dropdown:
        mnl_info["dropdownActivate"] = "hover"
        mnl_info["isShowDropdownIconOnHover"] = True
    mnl_info.update(_header_mnl_extra(props))
    logo_col = make_node("col", None, None, {
        "headerHorizontalAlign": {"xs": "start", "lg": "start"},
        "headerOrder": {"xs": "2"},
        "span": {"lg": "3", "xs": "6"},
    }, [make_node("widget", "WidgetHeaderLogo", None, _header_logo_info(props))])
    content_col = make_node("col", None, None, {
        "headerHorizontalAlign": {"xs": "flex-end", "lg": "flex-end"},
        "headerVerticalAlign": {"lg": "center", "xs": "center"},
        "headerOrder": {"xs": "3"},
        "span": {"lg": "9", "xs": "6"},
    }, [
        make_node("widget", "WidgetMainNavigationList", None, mnl_info),
        make_node("widget", "WidgetHeaderActionSearch", None,
                  {"widgetOrder": {"xs": "1"}}),
        make_node("widget", "WidgetHeaderActionCart", None,
                  {"widgetOrder": {"xs": "1"}}),
        make_node("widget", "WidgetHeaderActionUser", None, {
            "actionTextDisplay": {"xs": "none"},
            "widgetOrder": {"xs": "1"},
        }),
    ])
    return _header_section("SimpleHeader3",
                           make_node("row", None, None, {}, [logo_col, content_col]),
                           _header_extra_section_info(props),
                           include_padding_x=not props.get("isBgTransparent"))


def _header_preset4(props: dict) -> dict:
    menus = props.get("menuListObjects", [])
    items, has_dropdown = _header_menu_items(menus)
    mnl_info = {"menuItems": items, "drawerHeaderDistribute": {"xs": "flex-end"}}
    if has_dropdown:
        mnl_info["dropdownActivate"] = "hover"
        mnl_info["isShowDropdownIconOnHover"] = True
    mnl_info.update(_header_mnl_extra(props))
    nav_col = make_node("col", None, None, {
        "headerHorizontalAlign": {"xs": "start", "lg": "start"},
        "headerZIndex": 2,
        "span": {"xs": "2", "lg": "5"},
    }, [make_node("widget", "WidgetMainNavigationList", None, mnl_info)])
    logo_col = make_node("col", None, None, {
        "span": {"xs": "6", "lg": "2"},
        "headerHorizontalAlign": {"xs": "flex-start", "lg": "center"},
    }, [make_node("widget", "WidgetHeaderLogo", None, _header_logo_info(props))])
    action_col = make_node("col", None, None, {
        "span": {"lg": "5", "xs": "4"},
        "headerHorizontalAlign": {"xs": "flex-end", "lg": "flex-end"},
        "headerVerticalAlign": {"lg": "center", "xs": "center"},
        "headerOrder": {"xs": "3"},
    }, [
        make_node("widget", "WidgetHeaderActionSearch", None, {}),
        make_node("widget", "WidgetHeaderActionCart", None, {}),
        make_node("widget", "WidgetHeaderActionUser", None,
                  {"actionTextDisplay": {"xs": "none"}}),
    ])
    return _header_section("SimpleHeader4",
                           make_node("row", None, None, {}, [nav_col, logo_col, action_col]),
                           _header_extra_section_info(props),
                           include_padding_x=not props.get("isBgTransparent"))


def _build_header_main_section(props: dict) -> dict:
    """Build the main header section node only (preset row, no subHeader/searchBox)."""
    preset_id = (props.get("headerPane") or {}).get("alignPresetId", 1)
    if preset_id == 2:
        return _header_preset2(props)
    elif preset_id == 3:
        return _header_preset3(props)
    elif preset_id == 4:
        return _header_preset4(props)
    else:
        return _header_preset1(props)


def build_header_section(props: dict) -> dict:
    """Convert HeaderSection props → v4 header_zone (main section + subHeader if enabled)."""
    children = [_build_header_main_section(props)]
    if props.get("isShowSubMenuPane"):
        children.append(_subheader_section(props))
    header_zone = make_node("page", "header", "Header", {})
    header_zone["children"] = children
    return header_zone


def convert_header(header_json: dict) -> dict:
    """Convert v3 header dict ({"HeaderSection": {...}, "SearchBox": {...}}) → v4 header_zone."""
    props = (header_json.get("HeaderSection") if isinstance(header_json, dict) else {}) or {}
    search_box = (header_json.get("SearchBox") or {}) if isinstance(header_json, dict) else {}

    header_zone = build_header_section(props)

    if search_box.get("enableSearchBoxWidget"):
        header_zone["children"][0]["info"].setdefault("headerZIndex", 11)
        header_zone["children"].append(_searchbox_section(search_box))

    return header_zone


# ---------------------------------------------------------------------------
# Theme config (currentColors / currentFonts → :root + fontManifest)
# ---------------------------------------------------------------------------

# Fonts bundled in the v4 system (canonical names, from fontlist.txt). A font
# NOT in this set is treated as a Google font; because the converter runs
# offline (CLI + Pyodide) it can't verify Google availability, so such fonts
# are dropped from the family stack with a warning — handle them manually in v4.
_SYSTEM_FONTS = [
    # Thai
    "IBM Plex Sans Thai", "Noto Sans Thai", "Prompt", "Sarabun", "Kanit",
    "Mitr", "Tahoma", "Leelawadee UI", "Sukhumvit Set", "Thonburi",
    # English / Latin
    "Inter", "Roboto", "Open Sans", "Poppins", "Lato", "Cormorant Garamond",
    "Arial", "Helvetica Neue", "Helvetica", "Segoe UI", "Georgia",
    "Times New Roman", "Times", "Trebuchet MS",
]
_SYSTEM_FONTS_LOWER = {f.lower(): f for f in _SYSTEM_FONTS}

# v3 currentColors array index → v4 style[":root"] color variable.
_THEME_COLOR_KEYS = [
    "colorBrand",            # [0]
    "colorBrandAlt",         # [1]
    "colorNeutralSubtlest",  # [2]
    "colorNeutralBoldest",   # [3]
    "colorBrandSubtle",      # [4]
    "colorBrandBold",        # [5]
]

# v3 base typography constants (from v3/palletes/color-x_main.css), the same for
# every v3 site. Status colors are intentionally NOT carried over — v4's own status
# palette is used instead (see _seed_base + skip-if-equals-base).
# --text_base_size (1.4em) × --text_base_html (62.5%) = 14px; --text_base_lineheight;
# --text_base_weight (normal → 400). These match v4 defaults but are emitted for completeness.
_V3_BASE_TYPOGRAPHY = {
    "bodyFontSize": {"xs": {"value": 14, "unit": "px"}},
    "typoParagraphLineHeight": 1.5,
    "typoParagraphFontWeightRegular": 400,
}

# v4-base :root defaults (from v3/v4-base.json) for the keys we synthesize. A
# synthesized value equal to its base default is redundant (the base layer already
# supplies it), so it is NOT written — keeps the website JSON to real overrides only.
_V4_BASE_ROOT_DEFAULTS = {
    "bodyFontSize": {"xs": {"value": 14, "unit": "px"}, "lg": {"value": 16, "unit": "px"}},
    "typoParagraphLineHeight": 1.5,
    "typoParagraphFontWeightRegular": 400,
}


# Per-theme global text-base typography that OVERRIDES the v3/v4 base default,
# keyed by v3 `currentTheme`. Generated from the theme palette CSS by
# tools/gen_theme_typography.py (only in-themes.js themes; only values ≠ base).
# Looked up at convert time and emitted via _seed_base (skip-if-equals-base).
_THEME_TYPOGRAPHY = {
    "x_elite":          {"typoParagraphLineHeight": 1.4},
    "x_luxurygold":     {"typoParagraphFontWeightRegular": 300},
    "x_solid_round_fw": {"typoParagraphLineHeight": 1.4},
    "x_solid_shape_fw": {"typoParagraphLineHeight": 1.4},
    "x_solid_wide_fw":  {"typoParagraphLineHeight": 1.4},
    "x_solidfw":        {"bodyFontSize": {"xs": {"value": 16, "unit": "px"}}},
    "x_swift":          {"bodyFontSize": {"xs": {"value": 16, "unit": "px"}}},
}


# ---------------------------------------------------------------------------
# Theme registry + alt-scheme templates — read from v3/ CSS at RUNTIME.
#
# Theme conversion (`convert_theme`/`generate_all_themes`, CLI `theme` mode) is
# CLI-only: verified not referenced by converter2v4.html / htmlfix.html /
# mergecode.html, so unlike _THEME_TYPOGRAPHY/_THEME_COLOR_KEYS above (which the
# BROWSER's convert_global also needs, via _build_theme_root), this data does not
# need to be embedded for Pyodide. The person running `theme` always has v3/
# checked out locally, so we just parse it on demand instead of maintaining an
# embed → regenerate → paste-back ritual. Cached with lru_cache so a `theme all`
# batch (31 themes) only reads each file once. Formerly generated by
# tools/gen_theme_registry.py + tools/gen_theme_scheme2.py (both folded in here
# and removed — see git history for the standalone scripts).
# ---------------------------------------------------------------------------

def _v3_path(*parts):
    """Path to a file under v3/ (gitignored, developer-local; theme CLI mode
    only). Computed lazily inside functions — never evaluated at module import,
    so it's harmless even in a Pyodide context where __file__ may not resolve."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "v3", *parts)


def _strip_css_comments(t):
    t = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
    return re.sub(r"//[^\n]*", "", t)


def _js_str_list(body):
    """Parse a JS array body like `"a", 'b'` → ['a', 'b'] (quotes/space stripped,
    empties dropped). For non-positional lists like font stacks."""
    out = []
    for part in body.split(","):
        part = part.strip().strip("'\"").strip()
        if part:
            out.append(part)
    return out


def _js_color_list(body):
    """Like _js_str_list but POSITION-PRESERVING: keeps interior empty anchors
    (e.g. a missing brandAlt at index 1) so index→color-key alignment holds.
    Only a trailing-comma artifact is dropped."""
    out = [p.strip().strip("'\"").strip() for p in body.split(",")]
    while out and out[-1] == "":
        out.pop()
    return out


# The 6 anchor slots, in themes.js `colors` order, = these palette-CSS master vars.
_THEME_CSS_MASTER_VARS = ["color_schemeA", "color_schemeB", "color_light", "color_dark",
                          "color_schemeA_l", "color_schemeA_d"]
_THEME_HEX_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")
_THEME_GENERIC_TERMINATORS = {"serif", "sans-serif", "monospace", "cursive", "fantasy",
                              "system-ui", "ui-serif", "ui-sans-serif", "ui-monospace"}

# Ground-truth font stacks captured from each theme's LIVE demo `currentFonts` (the
# exact heading/text fonts the demo renders) for the themes where neither the
# palette CSS nor themes.js matches — both had drifted since the demo was built.
# Audited against all 33 demos 2026-07-08; these are the only mismatches. Highest-
# priority font source — overrides both CSS and themes.js.
_DEMO_FONTS = {
    "x_bakery":      {"heading": ["IBM Plex Serif", "IBM Plex Sans Thai", "serif"],
                      "text":    ["IBM Plex Sans", "IBM Plex Sans Thai", "sans-serif"]},
    "x_void":        {"heading": ["Poppins", "Noto Sans Thai", "sans-serif"],
                      "text":    ["Nunito Sans", "Noto Sans Thai", "sans-serif"]},
    "x_pottery":     {"heading": ["Playfair Display", "IBM Plex Sans Thai", "serif"],
                      "text":    ["IBM Plex Sans Thai", "sans-serif"]},
    "x_optic":       {"heading": ["IBM Plex Sans Thai", "sans-serif"],
                      "text":    ["IBM Plex Sans Thai", "sans-serif"]},
    # ceramicstore: demo body leads with Noto Sans Thai (not Noto Sans); heading
    # keeps a Noto Sans Thai fallback for Thai glyphs.
    "x_ceramicstore": {"heading": ["Noto Sans", "Noto Sans Thai", "sans-serif"],
                       "text":    ["Noto Sans Thai", "sans-serif"]},
}

# Ground-truth anchor colors captured from a theme's LIVE demo `currentColors` (the
# 6 anchors the demo explicitly renders) where the palette-CSS anchor correction
# over-corrected it — the demo matches the original themes.js, not the CSS. Only
# themes whose demo has a POPULATED currentColors AND differs qualify. Audited
# 2026-07-08. Position-preserving; "" = empty anchor (inherit Base). Highest-
# priority color source — overrides both CSS and themes.js.
_DEMO_COLORS = {
    "x_futuristic": ["#644fe1", "#6655cb", "#ffffff", "#050505", "#f3f4fa", "#6655cb"],
    "x_luxurygold": ["#e0c06e", "", "#ffffff", "#222222", "#f8f5f0", "#ab8a36"],
}

# Published (isActive && isSelectable) themes to EXCLUDE from the `theme` CLI
# batch anyway — the design team has already built these directly in the real
# v4 theme system, so a converter-generated theme JSON for them is redundant.
# Not a v3-publication concept (unlike isActive/isSelectable) — purely a v4
# deliverable-scope decision, kept separate from themes.js.
_THEME_ALREADY_DESIGNED = {"x_cozy_fw", "x_orderly"}


def _theme_ensure_generic(stack):
    """Append 'sans-serif' if a non-empty stack lacks a trailing generic family
    (serif stacks already carry 'serif' from CSS/_DEMO_FONTS). Empty stacks —
    meaning 'inherit Base' — are left untouched."""
    if stack and stack[-1].lower() not in _THEME_GENERIC_TERMINATORS:
        return list(stack) + ["sans-serif"]
    return stack


@functools.lru_cache(maxsize=None)
def _theme_css_fonts(tid):
    """(heading, text) font stacks from a theme's palette CSS master vars
    (--heading_base_family / --text_base_family), or None if the file is absent.
    A stack is None when the var is missing or has no real (non-generic) font —
    the caller then falls back to themes.js for that slot. The palette CSS is
    what v3 renders, so it's authoritative over themes.js where they disagree."""
    path = _v3_path("palletes", "color-%s.partial.css" % tid)
    if not os.path.exists(path):
        return None
    t = _strip_css_comments(open(path).read())

    def fam(var):
        m = re.search(r"--%s\s*:\s*([^;{}]+);" % var, t)
        if not m:
            return None
        lst = _js_str_list(m.group(1))
        return lst if any(x.lower() not in _THEME_GENERIC_TERMINATORS for x in lst) else None

    return fam("heading_base_family"), fam("text_base_family")


@functools.lru_cache(maxsize=None)
def _theme_css_anchors(tid):
    """The 6 anchor colors from a theme's palette CSS master variables
    (color-<id>.partial.css), or None if the file is absent. The palette CSS is
    what v3 actually renders, so it's authoritative over themes.js's preview
    `colors` array where the two disagree. A slot is None when the var is
    missing or isn't a literal hex (e.g. a var() reference) — the caller then
    falls back to themes.js for that slot."""
    path = _v3_path("palletes", "color-%s.partial.css" % tid)
    if not os.path.exists(path):
        return None
    t = _strip_css_comments(open(path).read())
    out = []
    for var in _THEME_CSS_MASTER_VARS:
        m = re.search(r"--%s\s*:\s*([^;{}]+);" % re.escape(var), t)
        val = m.group(1).strip() if m else ""
        out.append(val if _THEME_HEX_RE.match(val) else None)
    return out


@functools.lru_cache(maxsize=None)
def _theme_registry():
    """Per-theme source data for the `theme` CLI mode (v3 theme → v4 theme JSON):
    title, demo URL, fonts (heading/text stacks, may be empty → inherit Base),
    colors (6 anchors, same shape as a site's currentColors). Covers the
    published themes (isActive AND isSelectable in v3/themes.js — live/in real
    use; excludes private designs and unfinished themes like x_futuristic/x_soda).
    Color anchors and fonts: demo `currentFonts`/`currentColors` ground truth
    (_DEMO_FONTS/_DEMO_COLORS) wins outright when captured; otherwise the palette
    CSS master vars win per-slot (authoritative — it's what v3 actually renders),
    falling back to themes.js's preview arrays where the CSS is absent/undefined."""
    src = open(_v3_path("themes.js")).read()
    # Top-level theme entries are indented with exactly one tab OR four spaces
    # (themes.js mixes both); nested objects (fonts/tag/...) are deeper, so this
    # anchors only theme starts.
    starts = [m for m in re.finditer(r"^(?:\t|    )(\w+):\s*\{", src, re.M)]
    registry = {}
    for i, m in enumerate(starts):
        tid = m.group(1)
        block = src[m.end():(starts[i + 1].start() if i + 1 < len(starts) else len(src))]
        # Only themes that are actually published/in real use: BOTH selectable in
        # the editor AND active ("ready to be used"). isSelectable:false = a
        # private design; isActive:false = unfinished — excluded.
        if not (re.search(r"isSelectable\s*:\s*true", block)
                and re.search(r"isActive\s*:\s*true", block)):
            continue
        if tid in _THEME_ALREADY_DESIGNED:
            continue
        title = re.search(r"title\s*:\s*['\"]([^'\"]*)['\"]", block)
        heading = re.search(r"heading\s*:\s*\[([^\]]*)\]", block)
        text = re.search(r"text\s*:\s*\[([^\]]*)\]", block)
        colors = re.search(r"colors\s*:\s*\[([^\]]*)\]", block)
        demo = re.search(r"demoUrl\s*:\s*['\"]([^'\"]*)['\"]", block)
        js_colors = [c.lower() for c in (_js_color_list(colors.group(1)) if colors else [])]
        js_heading = _js_str_list(heading.group(1)) if heading else []
        js_text = _js_str_list(text.group(1)) if text else []

        # Colors: demo `currentColors` ground truth wins outright when captured;
        # otherwise prefer palette-CSS master vars, per-slot falling back to
        # themes.js where the CSS is absent/undefined.
        if tid in _DEMO_COLORS:
            anchors = [c.lower() for c in _DEMO_COLORS[tid]]
        else:
            css = _theme_css_anchors(tid)
            if css:
                anchors = [((css[i] or (js_colors[i] if i < len(js_colors) else "")) or "").lower()
                           for i in range(6)]
            else:
                anchors = js_colors

        # Fonts: demo `currentFonts` ground truth wins outright when captured;
        # otherwise CSS wins per slot when it has a real font, else themes.js.
        if tid in _DEMO_FONTS:
            fh = _DEMO_FONTS[tid]["heading"]
            ft = _DEMO_FONTS[tid]["text"]
        else:
            cf = _theme_css_fonts(tid)
            fh = cf[0] if (cf and cf[0]) else js_heading
            ft = cf[1] if (cf and cf[1]) else js_text

        # Close every non-empty stack with a generic terminator. themes.js-sourced
        # stacks often lack one; all such fonts are sans-serif (serif themes get
        # their `serif` terminator from the CSS/_DEMO_FONTS source). Empty =
        # inherit Base, left as-is.
        fh = _theme_ensure_generic(fh)
        ft = _theme_ensure_generic(ft)

        registry[tid] = {
            "title": title.group(1) if title else tid,
            "demo": demo.group(1) if demo else "",
            "fonts": {"heading": fh, "text": ft},
            "colors": anchors,
        }
    return registry


# The v4 alternative color scheme `.color-scheme-main-2` schema — the 74-token key
# ORDER every theme's block is emitted in (an independently-curated schema, NOT
# v4 Base's own `.color-scheme-main` key order). Values are read from v4 Base's
# `.color-scheme-main` at runtime by _scheme2_template() (neutral scale, no
# box-shadow — a safe, theme-adaptive fallback for tokens a theme hasn't
# decided): `sectionBorderColor` (unique to main-2) mirrors main's `borderColor`,
# and main's two slider-input keys (unique to main, not part of main-2) are
# dropped. Per-theme overrides from _theme_scheme2_overrides() layer on top via
# _build_scheme2().
_SCHEME2_SCHEMA = [
    "bgColor", "sectionBorderColor", "borderColor", "textColor", "textSubtleColor",
    "titleTextColor", "captionTextColor", "descriptionTextColor", "linkAccentColor",
    "linkAccentHoverColor", "linkDefaultColor", "linkDefaultHoverColor",
    "buttonPrimaryFillColor", "buttonPrimaryBorderColor", "buttonPrimaryTextColor",
    "buttonPrimaryBoxShadow", "buttonPrimaryBoxShadowColor", "buttonPrimaryHoverFillColor",
    "buttonPrimaryHoverBorderColor", "buttonPrimaryHoverTextColor", "buttonPrimaryHoverBoxShadow",
    "buttonPrimaryHoverBoxShadowColor", "buttonSecondaryBoxShadow", "buttonSecondaryBoxShadowColor",
    "buttonSecondaryHoverBoxShadow", "buttonSecondaryHoverBoxShadowColor",
    "buttonSecondaryHoverTextColor", "buttonSecondaryHoverBorderColor", "buttonSecondaryTextColor",
    "buttonSecondaryBorderColor", "buttonSecondaryFillColor", "buttonSecondaryHoverFillColor",
    "buttonGhostBorderColor", "buttonGhostHoverFillColor", "buttonGhostHoverBorderColor",
    "buttonGhostHoverTextColor", "buttonGhostTextColor", "buttonDisabledFillColor",
    "buttonDisabledTextColor", "tagDefaultBorderColor", "tagDefaultHoverBorderColor",
    "tagDefaultBgColor", "tagDefaultTextColor", "tagDefaultHoverBgColor", "tagDefaultHoverTextColor",
    "tagAccentBorderColor", "tagAccentHoverBorderColor", "tagAccentBgColor", "tagAccentTextColor",
    "tagAccentHoverBgColor", "tagAccentHoverTextColor", "arrowsTextColor", "arrowsBorderColor",
    "arrowsBgColor", "arrowsHoverBgColor", "arrowsHoverBorderColor", "arrowsHoverTextColor",
    "arrowsBoxShadow", "arrowsBoxShadowColor", "arrowsHoverBoxShadow", "arrowsHoverBoxShadowColor",
    "sliderBulletsBgColor", "sliderBulletsHoverBgColor", "sliderBulletsActiveBgColor",
    "scrollbarBgColor", "scrollbarTrackColor", "formTextColor", "formErrorColor",
    "inputIconColor", "inputTextColor", "inputFocusColor", "inputBorderColor", "inputBgColor",
    "inputPlaceholderColor",
]


@functools.lru_cache(maxsize=None)
def _scheme2_template():
    """The full 74-token `.color-scheme-main-2` template every theme starts from,
    read from v4 Base's own `.color-scheme-main` (v3/v4-base.json) and re-keyed
    to the main-2 schema (see _SCHEME2_SCHEMA)."""
    main = json.load(open(_v3_path("v4-base.json")))["style"][".color-scheme-main"]
    return {k: (main["borderColor"] if k == "sectionBorderColor" else main[k])
            for k in _SCHEME2_SCHEMA}


# A few themes declare their darkMode background/text as CSS RULES in the theme
# file (v3/themes/theme-<id>.partial.css `&.darkMode { background-color: ...;
# color: ... }`) instead of the palette's --background_darkBG_style mixin, so the
# palette scan misses them. Only themes with a REAL alternative background belong
# here — a darkMode that just sets `color: var(--color_light)` with no background
# is a plain inverse and is left to color-scheme-inverse. Values are (background,
# color), verified by hand:
#   x_void: `&.darkMode { background-color: var(--color_schemeB); }` + text `var(--color_dark)`
_CSS_RULE_DARKMODE = {
    "x_void": ("var(--color_schemeB)", "var(--color_dark)"),
}

# v3 `--color_<anchor>`  →  v4 palette ref name (`var(--color-<this>)`).
_SCHEME2_ANCHOR_MAP = {
    "schemeA": "brand", "schemeA_l": "brand-subtle", "schemeA_d": "brand-bold",
    "schemeB": "brand-alt", "neutral": "neutral",
    # light/light100 and dark/dark100 map to the theme's own neutral-subtlest/
    # neutral-boldest anchors, NOT the literal white/black tokens: every palette CSS
    # that defines --color_light100/--color_dark100 sets them as a plain `var()` alias
    # of --color_light/--color_dark (verified across all 27 themes that define them),
    # and colorNeutralSubtlest/colorNeutralBoldest are already derived from those exact
    # same v3 variables elsewhere (_THEME_CSS_MASTER_VARS). Using literal white/black
    # was invisible on Bakery (its dark/light are already near-black/white) but wrong
    # on themes whose dark/light are a real hue (e.g. Blue Horizon's navy `--color_dark`).
    "light": "neutral-subtlest", "light75": "neutral-subtlest", "light100": "neutral-subtlest",
    "dark": "neutral-boldest", "dark75": "neutral-boldest", "dark100": "neutral-boldest",
}

# Exceptions to the default p/s/t-button naming convention (buttonPrimary<-pbutton,
# buttonSecondary<-sbutton, link<-link, tag<-buttontag/tag) — only for a theme
# whose real markup deviates from it. Empty so far: verified by hand that x_bakery
# follows the convention exactly (including tertiary correctly NOT qualifying as
# ghost-shaped).
_SCHEME2_TOKEN_SOURCES = {}

# v3 mixin family name (without _lightBG_style/_darkBG_style suffix) that feeds
# each v4 token family, under the default convention.
_SCHEME2_DEFAULT_MIXIN_FAMILY = {
    "link": "link", "buttonPrimary": "pbutton", "buttonSecondary": "sbutton",
    "buttonGhost": "tbutton",  # only used if _looks_like_ghost() on its resolved style
    "tagDefault": "buttontag", "tagAccent": "buttontag",
}


def _scheme2_scalars(t):
    """All `--name: value;` scalar declarations (for resolving var() indirection)."""
    return dict((n, v.strip()) for n, v in
                re.findall(r"--([A-Za-z0-9_]+)\s*:\s*([^;{}]+);", t))


def _scheme2_bg_style(t):
    """(background, color) raw values from --background_darkBG_style, or None."""
    m = re.search(r"--background_darkBG_style\s*\{([^}]*)\}", t)
    if not m:
        return None
    body = m.group(1)

    def decl(prop):
        # lookbehind so `color` doesn't match inside `background-color`
        mm = re.search(r"(?<![-\w])%s\s*:\s*([^;]+);" % prop, body)
        return mm.group(1).strip() if mm else None

    return decl("background-color") or decl("background"), decl("color")


def _scheme2_to_ref(val, scal, depth=0):
    """v3 value → v4 scheme ref. Raw hex/transparent kept verbatim; `var(--color_X)`
    → mapped ref; any other `var(--Y)` is resolved one level through the palette's
    scalars (e.g. --darkBG_color → var(--color_neutral)); unmapped → None."""
    if not val or depth > 4:
        return None
    val = val.strip()
    if val.startswith("#") or val == "transparent":
        return val
    m = re.fullmatch(r"var\(--([A-Za-z0-9_]+)\)", val)
    if not m:
        return None
    name = m.group(1)
    if name.startswith("color_"):
        a = _SCHEME2_ANCHOR_MAP.get(name[len("color_"):])
        if a == "neutral":
            # "neutral" (bare) isn't a real v4 anchor — v4 only defines
            # neutral-subtlest/neutral-boldest, no plain neutral CSS var — so
            # emitting "var(--color-neutral)" would be a dangling reference
            # with no :root definition. Fall back to the v3 slot's own literal
            # hex from the palette scalars instead of losing the value.
            # Confirmed via x_periwinkle's live demo (2026-07-16): real value
            # #f3ffff, not derivable from the 6 named anchors. Only periwinkle
            # uses this slot as of the 16 alt-scheme themes checked.
            raw = scal.get(name)
            return raw if raw and raw.startswith("#") else None
        return "var(--color-%s)" % a if a else None
    return _scheme2_to_ref(scal.get(name), scal, depth + 1)  # indirect var → resolve


# ---------------------------------------------------------------------------
# Component mixin extraction (Link/Button/Tag) — brace-balanced, @apply-chain-aware
# ---------------------------------------------------------------------------

def _scheme2_extract_block(t, mixin_name):
    """Brace-balanced extraction of a `--mixin_name { ... }` body, or None. (button/
    link/tag mixins nest a `&:hover { ... }` block, which a naive non-nested regex
    can't handle — hence real brace counting instead of `[^}]*`.)"""
    m = re.search(r"--%s\s*\{" % re.escape(mixin_name), t)
    if not m:
        return None
    depth, i = 1, m.end()
    while i < len(t) and depth > 0:
        if t[i] == "{":
            depth += 1
        elif t[i] == "}":
            depth -= 1
        i += 1
    return t[m.end():i - 1]


def _scheme2_parse_own(body):
    """Parse the OWN (not nested) `@apply`s and `prop: value;` decls of a mixin body,
    plus one nested `&:hover { ... }` block if present. Returns
    (applies: [str], decls: {prop: val}, hover_decls: {prop: val})."""
    applies, decls, hover_decls = [], {}, {}
    i, n = 0, len(body)
    while i < n:
        ch = body[i]
        if ch.isspace():
            i += 1
            continue
        if body[i:i + 7] == "@apply ":
            j = body.index(";", i)
            applies.append(body[i + 7:j].strip().lstrip("-"))
            i = j + 1
            continue
        if ch == "&":
            j = body.index("{", i)
            depth, k = 1, j + 1
            while k < n and depth > 0:
                if body[k] == "{":
                    depth += 1
                elif body[k] == "}":
                    depth -= 1
                k += 1
            selector, inner = body[i:j].strip(), body[j + 1:k - 1]
            if "hover" in selector:
                for pm in re.finditer(r"([a-zA-Z-]+)\s*:\s*([^;]+);", inner):
                    hover_decls[pm.group(1)] = pm.group(2).strip()
            i = k
            continue
        semi = body.find(";", i)
        if semi < 0:
            break
        if ":" in body[i:semi]:
            prop, val = body[i:semi].split(":", 1)
            decls[prop.strip()] = val.strip()
        i = semi + 1
    return applies, decls, hover_decls


def _scheme2_border_color_from_shorthand(val):
    """`1px solid var(--color_schemeA)` → `var(--color_schemeA)` (last color-ish token)."""
    if not val:
        return None
    m = re.search(r"(var\([^)]+\)|#[0-9a-fA-F]{3,8}|transparent)\s*$", val.strip())
    return m.group(1) if m else None


def _scheme2_component_style(t, mixin_name, depth=0):
    """Resolve a mixin (through its @apply chain — dark falls back to light where
    aliased, tag falls back to buttontag, etc.) into
    {color, background-color, border-color, hover: {...}}, or None if it doesn't exist."""
    if depth > 6:
        return None
    body = _scheme2_extract_block(t, mixin_name)
    if body is None:
        return None
    applies, decls, hover_decls = _scheme2_parse_own(body)
    style = {"hover": {}}
    for applied in applies:
        base = _scheme2_component_style(t, applied, depth + 1)
        if base:
            for k in ("color", "background-color", "border-color", "border"):
                if base.get(k) is not None:
                    style[k] = base[k]
            style["hover"].update(base.get("hover", {}))
    style.update(decls)
    style["hover"].update(hover_decls)
    if "border-color" not in style and "border" in style:
        bc = _scheme2_border_color_from_shorthand(style["border"])
        if bc:
            style["border-color"] = bc
    return style


def _scheme2_text_role_tokens(t, scal, fallback):
    """titleTextColor/textSubtleColor/captionTextColor/descriptionTextColor for one
    theme's alt scheme, sourced from the specific title/subtitle/imagetitle/
    description darkBG mixins (verified live against Bakery: title/imagetitle are a
    distinct brand color from subtitle/description's black, on both schemes) — falls
    back to `fallback` (the `--background_darkBG_style` mixin's own `color`) when a
    role's mixin is absent or its color doesn't resolve to a v4 ref. `font-style`
    (e.g. italic on title) is intentionally dropped — v4 has no italic token."""
    out = {}
    for token, mixin in (
        ("titleTextColor", "title_darkBG_style"),
        ("textSubtleColor", "subtitle_darkBG_style"),
        ("captionTextColor", "imagetitle_darkBG_style"),
        ("descriptionTextColor", "description_darkBG_style"),
    ):
        style = _scheme2_component_style(t, mixin)
        ref = _scheme2_to_ref(style.get("color"), scal) if style else None
        out[token] = ref or fallback
    return out


def _scheme2_looks_like_ghost(style):
    """True if a resolved component style has no fill (transparent/absent background) —
    the defining trait of a ghost/text button."""
    if not style:
        return False
    return (style.get("background-color") or "").strip() in ("", "transparent")


def _scheme2_link_tokens(style, scal):
    color = _scheme2_to_ref(style.get("color"), scal)
    if color is None:
        return {}
    hover = _scheme2_to_ref(style["hover"].get("color"), scal) or color
    return {
        "linkDefaultColor": color, "linkDefaultHoverColor": hover,
        "linkAccentColor": color, "linkAccentHoverColor": hover,
    }


def _scheme2_button_solid_tokens(prefix, style, scal):
    """Primary/Secondary shape: Fill/Border/Text + Hover variants (no BoxShadow — no
    v3 source for that; left on the generic template default)."""
    out = {}
    fill = _scheme2_to_ref(style.get("background-color"), scal)
    border = _scheme2_to_ref(style.get("border-color"), scal)
    text = _scheme2_to_ref(style.get("color"), scal)
    hover = style.get("hover", {})
    if fill is not None:
        out[prefix + "FillColor"] = fill
        out[prefix + "HoverFillColor"] = _scheme2_to_ref(hover.get("background-color"), scal) or fill
    if border is not None:
        out[prefix + "BorderColor"] = border
        out[prefix + "HoverBorderColor"] = _scheme2_to_ref(hover.get("border-color"), scal) or border
    if text is not None:
        out[prefix + "TextColor"] = text
        out[prefix + "HoverTextColor"] = _scheme2_to_ref(hover.get("color"), scal) or text
    return out


def _scheme2_same_solid_button(prim, sec):
    """True if primary is a SOLID button (real fill, not transparent) AND secondary
    resolved to that same fill/border/text — i.e. v3 gave no visually distinct
    secondary (e.g. bakery, where --sbutton just @apply's the same mixin as --pbutton).
    Only the solid case is handled here: a theme whose primary is itself an outline
    (transparent fill, e.g. bluehorizon/swift) is left as-is for separate per-theme
    review — synthesizing 'an outline of an outline' would just be transparent."""
    fill = prim.get("buttonPrimaryFillColor")
    if not fill or fill == "transparent":
        return False
    return all(
        prim.get("buttonPrimary" + k) == sec.get("buttonSecondary" + k)
        for k in ("FillColor", "BorderColor", "TextColor"))


def _scheme2_outline_secondary(prim):
    """An OUTLINE version of the primary button, for the case where a theme's primary
    and secondary are the same solid style. v4 shows primary & secondary as opposite
    styles (one solid, one outline), so we synthesize: transparent fill, border+text =
    primary's fill color; hover fills solid (fill+border = primary fill, text = primary
    text)."""
    fill = prim.get("buttonPrimaryFillColor")
    text = prim.get("buttonPrimaryTextColor")
    out = {"buttonSecondaryFillColor": "transparent"}
    if fill is not None:
        out["buttonSecondaryBorderColor"] = fill
        out["buttonSecondaryTextColor"] = fill
        out["buttonSecondaryHoverFillColor"] = fill
        out["buttonSecondaryHoverBorderColor"] = fill
    if text is not None:
        out["buttonSecondaryHoverTextColor"] = text
    return out


def _scheme2_button_ghost_tokens(style, scal):
    """Ghost shape: BorderColor + TextColor (base) + Hover Fill/Border/Text (no base
    FillColor key exists in the v4 schema — ghost has no fill by definition)."""
    out = {}
    border = _scheme2_to_ref(style.get("border-color"), scal)
    text = _scheme2_to_ref(style.get("color"), scal)
    hover = style.get("hover", {})
    if border is not None:
        out["buttonGhostBorderColor"] = border
        out["buttonGhostHoverBorderColor"] = _scheme2_to_ref(hover.get("border-color"), scal) or border
    if text is not None:
        out["buttonGhostTextColor"] = text
        out["buttonGhostHoverTextColor"] = _scheme2_to_ref(hover.get("color"), scal) or text
    hfill = _scheme2_to_ref(hover.get("background-color"), scal)
    if hfill is not None:
        out["buttonGhostHoverFillColor"] = hfill
    return out


def _scheme2_tag_tokens(prefix, style, scal):
    out = {}
    bg = _scheme2_to_ref(style.get("background-color"), scal)
    border = _scheme2_to_ref(style.get("border-color"), scal)
    text = _scheme2_to_ref(style.get("color"), scal)
    hover = style.get("hover", {})
    if bg is not None:
        out[prefix + "BgColor"] = bg
        out[prefix + "HoverBgColor"] = _scheme2_to_ref(hover.get("background-color"), scal) or bg
    if border is not None:
        out[prefix + "BorderColor"] = border
        out[prefix + "HoverBorderColor"] = _scheme2_to_ref(hover.get("border-color"), scal) or border
    if text is not None:
        out[prefix + "TextColor"] = text
        out[prefix + "HoverTextColor"] = _scheme2_to_ref(hover.get("color"), scal) or text
    return out


def _scheme2_component_tokens(tid, t, scal):
    """Link/Button(Primary/Secondary/Ghost)/Tag tokens for one theme, via the default
    p/s/t-button convention (or _SCHEME2_TOKEN_SOURCES exceptions)."""
    sources = dict(_SCHEME2_DEFAULT_MIXIN_FAMILY)
    sources.update(_SCHEME2_TOKEN_SOURCES.get(tid, {}))
    out = {}

    link_style = _scheme2_component_style(t, sources["link"] + "_darkBG_style")
    if link_style:
        out.update(_scheme2_link_tokens(link_style, scal))

    primary_style = _scheme2_component_style(t, sources["buttonPrimary"] + "_darkBG_style")
    prim = _scheme2_button_solid_tokens("buttonPrimary", primary_style, scal) if primary_style else {}
    out.update(prim)

    secondary_style = _scheme2_component_style(t, sources["buttonSecondary"] + "_darkBG_style")
    if secondary_style:
        sec = _scheme2_button_solid_tokens("buttonSecondary", secondary_style, scal)
        # v4 convention: primary & secondary must be visually distinct (one solid, one
        # outline). If v3 gave no distinct secondary (bakery: --sbutton == --pbutton),
        # turn secondary into an outline of the primary.
        if _scheme2_same_solid_button(prim, sec):
            sec = _scheme2_outline_secondary(prim)
        out.update(sec)

    tertiary_style = _scheme2_component_style(t, sources["buttonGhost"] + "_darkBG_style")
    if tertiary_style and _scheme2_looks_like_ghost(tertiary_style):
        out.update(_scheme2_button_ghost_tokens(tertiary_style, scal))

    tag_family = sources["tagDefault"]
    tag_style = _scheme2_component_style(t, tag_family + "_darkBG_style")
    if tag_style:
        out.update(_scheme2_tag_tokens("tagDefault", tag_style, scal))
        out.update(_scheme2_tag_tokens("tagAccent", tag_style, scal))

    return out


# Themes whose `--background_darkBG_style` mixin resolves to a genuinely DARK
# bg/light text (should be `.color-scheme-inverse`, an existing v4 concept) --
# not a pale "alt background" (what `.color-scheme-main-2` actually means).
# `_theme_scheme2_overrides()` below has no brightness check at all (only "does
# this mixin exist"), so it was building main-2 out of what's really inverse
# content. First confirmed fix (2026-07-21): x_swift, where the misclassified
# "main-2" resolves to `#393e41` -- the EXACT same hex already used by this
# theme's own `.color-scheme-inverse` (the header's real dark scheme, see
# `_THEME_INVERSE["x_swift"]`) -- so excluding it here needs no new slot at
# all; content that used to get tagged main-2 now falls through to the
# converter's own default isDarkMode->`color-scheme-inverse` tagging (always
# emitted regardless of whether a theme "has main-2"), which already resolves
# correctly. Originally found as a class of bug affecting 4 themes total
# (`VERIFIED.md`'s "Known bug — main-2 vs inverse misclassification": swift,
# elite, mixednuts, petestate) -- petestate is NOT added here yet. It needs
# its own check (does the misclassified color coincidentally match an
# existing inverse, like swift, or does it need a brand-new inverse slot of
# its own?) before joining this set -- do not batch it in without doing that
# per-theme work first.
# x_elite (2026-08-04): unlike swift, no existing inverse slot to reuse --
# `_THEME_INVERSE["x_elite"]` is a brand-new, CSS-grounded build (see its own
# comment). Live-demo QA'd, confirmed done 2026-08-06.
# x_mixednuts (2026-08-06, DRAFT): also a brand-new build -- this theme's
# palette CSS is unusually sparse (no title/subtitle/tag/link darkBG mixins
# at all, only background+button), so most of `_THEME_INVERSE["x_mixednuts"]`
# is synthesized per this project's standing convention, not CSS-grounded.
# Header/Footer/subheader are NOT touched -- all three have proper
# `.darkMode.X` CSS gates already (the normal, already-handled pattern), and
# none is actually `isDarkMode:true` in the real v3 demo, so out of scope for
# now (same as x_elite's header before the user separately asked about it).
_THEME_SCHEME2_MISCLASSIFIED_DARK = {"x_swift", "x_elite", "x_mixednuts", "x_petestate"}


@functools.lru_cache(maxsize=None)
def _theme_scheme2_overrides():
    """Per-theme `.color-scheme-main-2` overrides: bg/text from each v3 palette's
    --background_darkBG_style ("alternative background"); the 4 text-role tokens
    (title/subtitle/caption/description) from their own specific mixins via
    _scheme2_text_role_tokens (falls back to the background mixin's color when a
    role mixin is absent); plus Link/Button (Primary/Secondary/Ghost)/Tag tokens
    from the p/s/t-button naming convention (--pbutton_*/--sbutton_*/--tbutton_*/
    --link_*/--buttontag_*), resolved through each mixin's @apply chain. A theme
    without a real alt background (no --background_darkBG_style / _CSS_RULE_DARKMODE
    entry) gets no key here and falls back to _scheme2_template() untouched. Themes
    in `_THEME_SCHEME2_MISCLASSIFIED_DARK` are skipped even if a mixin exists --
    their "alt background" is actually dark and belongs to `.color-scheme-inverse`
    instead (see that set's comment).
    Layered by _build_scheme2()."""
    ids = set(_theme_registry()) - _THEME_SCHEME2_MISCLASSIFIED_DARK
    reg = {}
    palletes_dir = _v3_path("palletes")
    if os.path.isdir(palletes_dir):
        for fn in sorted(os.listdir(palletes_dir)):
            if not (fn.startswith("color-") and fn.endswith(".partial.css")):
                continue
            tid = fn[len("color-"):-len(".partial.css")]
            if tid not in ids:
                continue
            t = _strip_css_comments(open(os.path.join(palletes_dir, fn)).read())
            bs = _scheme2_bg_style(t)
            if not bs:
                continue
            scal = _scheme2_scalars(t)
            bg, color = _scheme2_to_ref(bs[0], scal), _scheme2_to_ref(bs[1], scal)
            entry = {}
            if bg:
                entry["bgColor"] = bg
            if color:
                entry["textColor"] = color
                entry.update(_scheme2_text_role_tokens(t, scal, color))
            if entry:
                entry.update(_scheme2_component_tokens(tid, t, scal))
                reg[tid] = entry

    # Themes whose darkMode bg/text live in the theme CSS as rules, not the palette
    # mixin (see _CSS_RULE_DARKMODE). Translate the same way, via the palette scalars.
    for tid, (bg_raw, color_raw) in _CSS_RULE_DARKMODE.items():
        if tid not in ids or tid in reg:
            continue
        pf = _v3_path("palletes", "color-%s.partial.css" % tid)
        t = _strip_css_comments(open(pf).read()) if os.path.exists(pf) else ""
        scal = _scheme2_scalars(t)
        bg, color = _scheme2_to_ref(bg_raw, scal), _scheme2_to_ref(color_raw, scal)
        entry = {}
        if bg:
            entry["bgColor"] = bg
        if color:
            entry["textColor"] = color
            entry.update(_scheme2_text_role_tokens(t, scal, color))
        if entry:
            entry.update(_scheme2_component_tokens(tid, t, scal))
            reg[tid] = entry

    return dict(sorted(reg.items()))


@functools.lru_cache(maxsize=None)
def _scheme_inverse_template():
    """The v4 inverse color scheme `.color-scheme-inverse`, verbatim from the
    peapea theme (v3/v4-peapea-theme.json) — the full 75-token template. A
    genuine dark/colored scheme (dark bg, light text), so it's a sensible
    fallback as-is (unlike main-2). Emitted per theme only when the theme has a
    real inverse override (_THEME_INVERSE); most themes just inherit the v4
    default. Layered by _build_inverse()."""
    return json.load(open(_v3_path("v4-peapea-theme.json")))["style"][".color-scheme-inverse"]


def _scheme_inverse2_template():
    """The v4 `.color-scheme-inverse-2` template — a SECOND inverse slot, same
    75-token schema as `.color-scheme-inverse` (v4's color-scheme system reads any
    `.color-scheme-<name>` class by name; the key schema itself isn't tied to a
    specific class). No separate reference JSON exists for it (nothing in v3/ ships
    a `-2` variant), so this reuses `_scheme_inverse_template()`'s shape verbatim.
    Needed when a single theme's own v3 CSS gives header and footer genuinely
    DIFFERENT inverse colors (e.g. x_petfriendly: header bg schemeA/orange, footer
    bg schemeB/blue) — one shared `.color-scheme-inverse` can't represent both, so
    the second (usually footer, per _THEME_INVERSE2) gets this second class instead.
    Layered by _build_inverse2()."""
    return _scheme_inverse_template()


# Per-theme `.color-scheme-inverse-2` overrides — see _scheme_inverse2_template()'s
# docstring for why this exists. Scoped to `v4-demos/` only for now (2026-07-20): the
# production website converter (build_footer_section/build_header_section) has no
# theme awareness at all, so it always emits plain "color-scheme-inverse" for a dark
# footer/header regardless of theme — a real petfriendly site conversion needs manual
# correction in the v4 admin to point its footer at "color-scheme-inverse-2" until/
# unless the production converter gains theme-awareness (separate, bigger scope,
# deferred). tools/regen_demos.py's per-theme footer→inverse-2 rewrite is the only
# place this currently gets wired up automatically.
_THEME_INVERSE2 = {
    "x_petfriendly": {
        "bgColor": "var(--color-brand-alt)",
        "textColor": "var(--color-neutral-subtlest)",
        "textSubtleColor": "var(--color-neutral-subtlest)",
        "titleTextColor": "var(--color-neutral-subtlest)",
        "captionTextColor": "var(--color-neutral-subtlest)",
        "descriptionTextColor": "var(--color-neutral-subtlest)",
        "linkDefaultColor": "var(--color-neutral-subtlest)",
        "linkDefaultHoverColor": "var(--color-neutral-boldest)",
        "linkAccentColor": "var(--color-neutral-subtlest)",
        "linkAccentHoverColor": "var(--color-neutral-boldest)",
        # General borders (2026-07-20, ported verbatim from a manual edit the
        # user made directly on the generated JSON): white instead of the v4
        # default's black. Literal var(--color-white), matching the user's own
        # choice exactly -- same value as neutral-subtlest for this theme
        # (its neutral-subtlest IS #ffffff) but kept literal, not substituted,
        # to stay faithful to what was hand-edited.
        "borderColor": "var(--color-white)",
        "sectionBorderColor": "var(--color-white)",
        "sectionHeaderBorderColor": "var(--color-white)",
        # Arrows (slider/carousel), same manual-edit source: default icon is
        # brand-colored (not black); hover flips to a solid black fill + white
        # icon -- opposite direction from the Button/Tag hover rule below.
        "arrowsTextColor": "var(--color-brand)",
        "arrowsBorderColor": "var(--color-white)",
        "arrowsHoverBgColor": "var(--color-black)",
        "arrowsHoverTextColor": "var(--color-white)",
        # Outline style by DEFAULT across all buttons (user request, 2026-07-20):
        # white border/transparent fill/white text. HOVER (updated later same
        # day, standing rule for this theme): solid neutral-subtlest (white)
        # fill/bg + neutral-boldest (black) text, uniformly across
        # Primary/Secondary/Ghost/Tag -- the exact opposite of main/main-2's
        # hover rule (see _THEME_MAIN2_OVERRIDES/_THEME_MAIN_OVERRIDES). NOT
        # zone-relative this time (same fixed swap in both inverse/inverse-2) --
        # supersedes the earlier per-widget-family hover designs (light-blue
        # outline, zone's-own-bg text). Link is unaffected, excluded from this
        # rule. Primary's DEFAULT (not hover) was further refined by the same
        # manual edit above: solid white fill (not outline) + brand text, no
        # border -- diverges from Secondary/Ghost, which stay outline by default.
        "buttonPrimaryFillColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryBorderColor": "transparent",
        "buttonPrimaryTextColor": "var(--color-brand)",
        "buttonPrimaryBoxShadow": "none",
        "buttonPrimaryBoxShadowColor": "transparent",
        "buttonPrimaryHoverFillColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverBorderColor": "transparent",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-boldest)",
        "buttonPrimaryHoverBoxShadow": "none",
        "buttonPrimaryHoverBoxShadowColor": "transparent",
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryBorderColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverFillColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverBorderColor": "transparent",
        "buttonSecondaryHoverTextColor": "var(--color-neutral-boldest)",
        "buttonGhostBorderColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverBorderColor": "transparent",
        "buttonGhostTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverTextColor": "var(--color-neutral-boldest)",
        "buttonGhostHoverFillColor": "var(--color-neutral-subtlest)",
        "tagDefaultBgColor": "transparent",
        "tagDefaultBorderColor": "var(--color-neutral-subtlest)",
        "tagDefaultTextColor": "var(--color-neutral-subtlest)",
        "tagDefaultHoverBgColor": "var(--color-neutral-subtlest)",
        "tagDefaultHoverBorderColor": "transparent",
        "tagDefaultHoverTextColor": "var(--color-neutral-boldest)",
        "tagAccentBgColor": "transparent",
        "tagAccentBorderColor": "var(--color-neutral-subtlest)",
        "tagAccentTextColor": "var(--color-neutral-subtlest)",
        "tagAccentHoverBgColor": "var(--color-neutral-subtlest)",
        "tagAccentHoverBorderColor": "transparent",
        "tagAccentHoverTextColor": "var(--color-neutral-boldest)",
    },
    # x_swift (drafted 2026-07-21, NOT yet live-demo QA'd): FOOTER ONLY, scoped
    # narrowly on user request. This theme has THREE genuinely different dark
    # contexts (headerPane -> neutral-boldest #393e41 dark gray;
    # subHeaderPane.darkMode -> INVERTED polarity, neutral-subtlest bg + dark
    # text; footer -> brand-alt #01a7c2 teal) that don't share one convenient
    # inverse story. Header is EXPLICITLY left untouched for now (not
    # `_THEME_INVERSE`, not `_FORCE_HEADER_INVERSE`) -- it's tangled up with
    # both the still-deferred main-2/inverse misclassification bug (x_swift is
    # one of the original 4 flagged themes) AND a separate unresolved layout
    # issue the user flagged (subHeaderPane floats over the home page's first
    # section) that has nothing to do with color. Only the footer -- which has
    # NO isDarkMode key in the demo at all despite unconditionally-colored CSS
    # -- gets built out here, via inverse-2 (not the primary inverse slot) so
    # it can't collide with whatever header ends up needing later.
    # `tools/regen_demos.py` gained `_FORCE_FOOTER_INVERSE`/
    # `_force_footer_inverse_top_level()` (mirrors the existing header
    # mechanism) to set footer's colorScheme in the first place before the
    # existing inverse-2 flip logic relabels it.
    #
    # Grounded from `.footerLayout` (theme-x_swift.partial.css, unconditional,
    # no &.darkMode gate): bg=var(--color_schemeB) (teal), `.detailArea`
    # text/link=var(--color_light) (a warm off-white, #f6f7eb -- this theme's
    # neutral-subtlest is NOT pure white). Link has no hover color change at
    # all (just `text-decoration: underline`), kept the same color throughout.
    # Button Primary/Secondary ARE genuinely grounded and, unusually, byte-
    # IDENTICAL in the source CSS (`--pbutton_darkBG_style`/`--sbutton_
    # darkBG_style`): outline default (border+text=light, transparent fill),
    # hover flips via `--button_darkBG_transition` (fill grows solid light,
    # text becomes dark) -- a real "flip" pattern, not inferred. Since v3 gives
    # zero distinction between Primary/Secondary here, Secondary was
    # synthesized as a visually distinct family per this project's standing
    # convention (every other theme needing this got the same treatment):
    # outline using Brand (schemeA, red-orange) instead of white, hover fills
    # solid brand + light text -- doesn't collide with the teal bg. Ghost
    # (maps to `--tbutton_darkBG_style`, the underlined tertiary-link style):
    # text=light, hover CSS explicitly keeps the same color (`!important`,
    # only opacity fades) -- respected literally, no hover color change. Tag
    # has no clean solid-color grounding (`--tag_darkBG_style`/`--buttontag_
    # darkBG_style` are alpha-transparency/border-only) -- synthesized as an
    # outline consistent with Secondary's brand-red-orange hover family.
    "x_swift": {
        "bgColor": "var(--color-brand-alt)",
        "textColor": "var(--color-neutral-subtlest)",
        "textSubtleColor": "var(--color-neutral-subtlest)",
        "titleTextColor": "var(--color-neutral-subtlest)",
        "captionTextColor": "var(--color-neutral-subtlest)",
        "descriptionTextColor": "var(--color-neutral-subtlest)",
        "linkDefaultColor": "var(--color-neutral-subtlest)",
        "linkDefaultHoverColor": "var(--color-neutral-subtlest)",
        "linkAccentColor": "var(--color-neutral-subtlest)",
        "linkAccentHoverColor": "var(--color-neutral-subtlest)",
        # Button (2026-07-21, live-demo QA): hover text resolves to THIS
        # scheme's own bg (brand-alt/teal here, vs neutral-boldest for the
        # primary inverse slot/header, `_THEME_INVERSE["x_swift"]` -- see
        # CSS-QUIRKS.md's "x_swift" entry for the back-and-forth on whether
        # that slot should exist at all; it was removed, then restored).
        "buttonPrimaryFillColor": "var(--color-brand)",
        "buttonPrimaryBorderColor": "transparent",
        "buttonPrimaryTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryBoxShadow": "none",
        "buttonPrimaryBoxShadowColor": "transparent",
        "buttonPrimaryHoverFillColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverBorderColor": "transparent",
        "buttonPrimaryHoverTextColor": "var(--color-brand-alt)",
        "buttonPrimaryHoverBoxShadow": "none",
        "buttonPrimaryHoverBoxShadowColor": "transparent",
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryBorderColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverFillColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverBorderColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverTextColor": "var(--color-brand-alt)",
        "buttonGhostBorderColor": "transparent",
        "buttonGhostTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverFillColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverBorderColor": "transparent",
        "buttonGhostHoverTextColor": "var(--color-brand-alt)",
        # Tag (2026-07-21, live-demo QA): literal values given all matched
        # existing computed anchors exactly (neutral-subtle `#dfe1d7`,
        # neutral-boldest `#393e41`, brand-alt-bold `#017d92`,
        # brand-alt-subtle `#67cada`, brand-alt-boldest `#005461`).
        "tagDefaultBgColor": "var(--color-neutral-subtle)",
        "tagDefaultBorderColor": "transparent",
        "tagDefaultTextColor": "var(--color-neutral-boldest)",
        "tagDefaultHoverBgColor": "var(--color-brand-alt-bold)",
        "tagDefaultHoverBorderColor": "transparent",
        "tagDefaultHoverTextColor": "var(--color-neutral-subtlest)",
        "tagAccentBgColor": "var(--color-brand-alt-subtle)",
        "tagAccentBorderColor": "transparent",
        "tagAccentTextColor": "var(--color-brand-alt-boldest)",
        "tagAccentHoverBgColor": "var(--color-brand-alt-bold)",
        "tagAccentHoverBorderColor": "transparent",
        "tagAccentHoverTextColor": "var(--color-neutral-subtlest)",
    },
    # x_mixednuts (2026-08-06, user-corrected -- still fully hand-specified, NOT
    # CSS-grounded, NOT yet wired to any section): the theme's real header-
    # darkMode look is a designed background IMAGE (green-toned, with fake non-
    # functional text/buttons baked into the artwork itself) -- there's no live
    # CSS/JSON case for a real, functional green header scheme to read colors
    # from. User asked for this scheme to exist anyway, as a prepared option for
    # whoever wants a real (non-image) green header dark-mode alternative.
    # Secondary/Ghost/Link Default are explicitly "same as (primary) inverse" per
    # the user -- copied verbatim from `_THEME_INVERSE["x_mixednuts"]` above, incl.
    # Secondary's hover going to brand GREEN even though this scheme's own bg is
    # ALSO green (a literal instruction, not re-derived for this bg -- flag for
    # live-demo confirmation it isn't a brand-on-brand collision in practice).
    # Primary/Link Accent/Tag hover are specific to this scheme. Not committed to
    # `_FORCE_*` in tools/regen_demos.py since there's no live dark header to
    # point it at yet.
    "x_mixednuts": {
        "bgColor": "var(--color-brand)",
        "textColor": "var(--color-neutral-subtlest)",
        "textSubtleColor": "var(--color-neutral-subtlest)",
        "titleTextColor": "var(--color-neutral-subtlest)",
        "captionTextColor": "var(--color-neutral-subtlest)",
        "descriptionTextColor": "var(--color-neutral-subtlest)",
        "linkDefaultColor": "var(--color-neutral-subtlest)",
        "linkDefaultHoverColor": "var(--color-neutral-subtlest)",
        "linkAccentColor": "var(--color-neutral-boldest)",
        "linkAccentHoverColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryFillColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryBorderColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryTextColor": "var(--color-brand)",
        "buttonPrimaryHoverFillColor": "var(--color-neutral-boldest)",
        "buttonPrimaryHoverBorderColor": "var(--color-neutral-boldest)",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryBorderColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverFillColor": "var(--color-brand)",
        "buttonSecondaryHoverBorderColor": "var(--color-brand)",
        "buttonSecondaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverFillColor": "var(--color-neutral-bold)",
        "buttonGhostHoverBorderColor": "transparent",
        "buttonGhostHoverTextColor": "var(--color-neutral-subtlest)",
        "tagDefaultBgColor": "transparent",
        "tagDefaultBorderColor": "var(--color-neutral-subtlest)",
        "tagDefaultTextColor": "var(--color-neutral-subtlest)",
        "tagDefaultHoverBgColor": "var(--color-brand-subtlest)",
        "tagDefaultHoverBorderColor": "var(--color-neutral-subtlest)",
        # Hover text (2026-08-06, user correction): the pale hover fill needs a
        # dark text, not white -- matches this SCHEME's own bg color
        # (var(--color-brand), the green this inverse-2 slot is built around).
        "tagDefaultHoverTextColor": "var(--color-brand)",
        # Accent (2026-08-06, user correction): border/text white -> brand-subtlest
        # -- now deliberately different from Default, which stays white. Hover
        # border tracks the new default; hover bg/text untouched from before.
        "tagAccentBgColor": "transparent",
        "tagAccentBorderColor": "var(--color-brand-subtlest)",
        "tagAccentTextColor": "var(--color-brand-subtlest)",
        "tagAccentHoverBgColor": "var(--color-brand-subtlest)",
        "tagAccentHoverBorderColor": "var(--color-brand-subtlest)",
        "tagAccentHoverTextColor": "var(--color-brand)",
    },
}


@functools.lru_cache(maxsize=None)
def _scheme_main_template():
    """v4 Base's own `.color-scheme-main` (v3/v4-base.json), verbatim, native key set —
    this IS the v4 default every theme inherits already, so per-theme overrides here are
    for a theme whose main-scheme buttons/tags need to visually match its own main-2
    (e.g. x_oasis: user asked for the two to use identical button/tag colors). Emitted
    per theme only when `_THEME_MAIN_OVERRIDES` has an entry; most themes just inherit
    the v4 default untouched (Phase 4 proper — a general per-theme light-scheme pass —
    is a separate, not-yet-started piece of work, see VERIFIED.md). Layered by
    _build_main()."""
    return json.load(open(_v3_path("v4-base.json")))["style"][".color-scheme-main"]


# Tag border width (2026-07-21, user-found on x_supercar, then rolled out on
# request): v4-base's :root default is `tagBorderWidth`/`tagHoverBorderWidth` =
# 0px, so a Tag border-COLOR token set anywhere in .color-scheme-* renders
# invisibly regardless of theme — width is a separate, unrelated :root key, not
# part of any .color-scheme-* block. Every theme below has a real (non-
# transparent) Tag border color set somewhere in its own overrides (found by
# scanning all 29 generated deliverables); x_playground is deliberately
# excluded — its Tag border is `transparent` everywhere, borderless by design,
# no bug there. 1px is a PLACEHOLDER, not a per-theme CSS-verified final value
# (only x_supercar's own CSS was actually checked: `border: 1px solid`,
# color-x_supercar.partial.css) — explicitly not live-demo re-confirmed on the
# other 7, unlike this project's usual per-theme verification standard. Purpose
# is narrow: unblock seeing the border COLOR at all (was invisible at 0px) while
# doing color QA now. The user decided (2026-07-21) the actual width value for
# every theme gets decided for real in Phase 5 (button/tag border-radius, still
# not started, see VERIFIED.md) — these 7 do NOT need a standalone re-check
# before then, Phase 5's own pass covers it. Applied in convert_theme via
# `theme_id in _THEME_TAG_BORDER_WIDTH` — root-level, so one entry fixes
# visibility across every scheme (main/main-2/inverse/inverse-2) that theme has
# at once.
_THEME_TAG_BORDER_WIDTH = {
    "x_bakery", "x_denim_fw", "x_eco", "x_luxurygold", "x_oasis",
    "x_periwinkle", "x_petfriendly", "x_supercar", "x_bluehorizon",
    # x_mixednuts (2026-08-06, user-confirmed): STANDING RULE going forward --
    # whenever a theme's `.color-scheme-*` sets a real (non-transparent) Tag
    # border color anywhere, add it here too. v4-base's tagBorderWidth/
    # tagHoverBorderWidth default to 0px, so a border-COLOR alone renders
    # invisibly regardless of theme.
    "x_mixednuts",
    # x_elite (2026-08-06, user caught this one was missed) -- has real Tag
    # border colors too (`#00050026` in main, `#faf8f780` in inverse, both
    # literal alpha hex, no anchor match), just never added when that work
    # was done earlier this session. Same rule applies retroactively.
    "x_elite",
    # x_petestate (2026-08-07): inverse Tag has a real border color
    # (var(--color-brand-alt), teal) from `.btnTag`'s theme CSS -- same rule.
    "x_petestate",
}


# Per-theme overrides for a `.widget-<kind>` global style block (v4-base.json's
# `style` dict already has one entry per widget kind, e.g. `.widget-heading`,
# `.widget-button-group` -- these are theme-wide DEFAULTS every instance of
# that widget inherits unless the section's own `info` overrides it, same
# cascade as `.color-scheme-*`). x_elite (2026-08-04, user-suggested
# mechanism): `h2.headline { text-align: center; }` + `.headline-text
# { text-align: center; }` (both unconditional, theme-x_elite.partial.css) --
# confirmed live-demo-side as "almost the entire page except header/footer"
# is centered by default, and that setting alignment explicitly per-section
# already renders correctly in any direction. Only `h1.headline` (the
# hero-only tag, `isTitleH1` in v3) has no such rule -- but the converter's
# WidgetHeading `alignment` field can't distinguish "renders as h1" at the
# theme-style level the way v3's CSS tag-selector can, so this is a broad
# default: a future h1 hero built on this theme would need alignment set
# back to left per-instance manually, same as any other override. Applied in
# convert_theme() as its own `style` key, layered over Base's
# `.widget-heading{gap:...}` (v4 merges sparse overrides, doesn't replace the
# whole block).
_THEME_WIDGET_STYLE_OVERRIDES = {
    "x_elite": {
        ".widget-heading": {"alignment": {"xs": "center", "lg": "center"}},
    },
}


# Manual per-theme corrections layered onto the CSS-derived `.color-scheme-main-2`
# (_theme_scheme2_overrides()), for cases that registry gets wrong. x_petfriendly
# (2026-07-20): standing rule from the user, this theme only — Button
# (Primary/Secondary/Ghost) and Tag hover in main/main-2 = solid
# neutral-boldest (black) fill/bg + neutral-subtlest (white) text, uniformly
# (not per-widget-family); inverse/inverse-2 do the opposite (see
# _THEME_INVERSE/_THEME_INVERSE2 below). Link is explicitly excluded — not
# part of this rule. Supersedes the earlier narrower "Ghost hover text was
# blending" fix (folded into this broader uniform rule).
_THEME_MAIN2_OVERRIDES = {
    "x_petfriendly": {
        "buttonPrimaryHoverFillColor": "var(--color-neutral-boldest)",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverFillColor": "var(--color-neutral-boldest)",
        "buttonSecondaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverFillColor": "var(--color-neutral-boldest)",
        "buttonGhostHoverTextColor": "var(--color-neutral-subtlest)",
        "tagDefaultHoverBgColor": "var(--color-neutral-boldest)",
        "tagDefaultHoverTextColor": "var(--color-neutral-subtlest)",
        "tagAccentHoverBgColor": "var(--color-neutral-boldest)",
        "tagAccentHoverTextColor": "var(--color-neutral-subtlest)",
        # Link hover (2026-07-21): CSS-derived registry read these as BrandBold,
        # which this theme's own palette CSS sets == Brand (schemeA_d == schemeA,
        # see COLORS.md/VERIFIED.md) -- so they rendered identical to Link
        # Default's non-hover color. Repointed at Brand explicitly (same visual
        # result today, but no longer riding on BrandBold's coincidental value --
        # see the BrandBold placeholder note in convert_theme).
        "linkAccentHoverColor": "var(--color-brand)",
        "linkDefaultHoverColor": "var(--color-brand)",
    },
    # x_playground (2026-07-21): user supplied the literal CSS-grounded values
    # directly -- matches this theme's actual (single, undistinguished)
    # --button_lightBG_style mixin exactly: fill=brand-subtle (teal #3ec293),
    # hover fill=brand-alt (yellow #ffd33a), text=white always (both states). No
    # per-family distinction in the source CSS at all, so Primary/Secondary/Ghost
    # all get the identical treatment. Tag explicitly told to match the same
    # pattern, in every scheme (also applied to _THEME_MAIN_OVERRIDES and
    # _THEME_INVERSE below). titleTextColor already correctly var(--color-brand)
    # from the CSS-derived registry -- no override needed here.
    "x_playground": {
        # linkAccentColor (2026-07-21): green (brand-subtle), overriding the
        # CSS-derived registry's neutral-boldest default. linkDefaultColor and
        # both hover colors were already correct as auto-computed (hover =
        # brand/purple for both default+accent).
        "linkAccentColor": "var(--color-brand-subtle)",
        "buttonPrimaryFillColor": "var(--color-brand-subtle)",
        "buttonPrimaryBorderColor": "transparent",
        "buttonPrimaryTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverFillColor": "var(--color-brand-alt)",
        "buttonPrimaryHoverBorderColor": "var(--color-brand-alt)",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-subtlest)",
        # Secondary (2026-07-21): outline, distinct from Primary's solid fill
        # (they'd looked identical since Primary was unified with this same
        # brand-subtle/brand-alt palette). Hover border matches hover fill
        # (not left transparent) so the border doesn't visibly vanish mid-
        # transition when the fill color changes.
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryBorderColor": "var(--color-brand-subtle)",
        "buttonSecondaryTextColor": "var(--color-brand-subtle)",
        "buttonSecondaryHoverFillColor": "var(--color-brand-alt)",
        "buttonSecondaryHoverBorderColor": "var(--color-brand-alt)",
        "buttonSecondaryHoverTextColor": "var(--color-neutral-subtlest)",
        # Ghost has no default-fill slot in v4's schema at all (always transparent
        # until hover) -- white text per the user's "always white" instruction would
        # be invisible with no fill behind it against this scheme's light bg, so
        # DEFAULT stays brand-subtle border+text (visible outline) as the one
        # necessary exception; HOVER (which does have a fill slot) follows the
        # instruction exactly: brand-alt fill + white text.
        "buttonGhostBorderColor": "var(--color-brand-subtle)",
        "buttonGhostTextColor": "var(--color-brand-subtle)",
        "buttonGhostHoverFillColor": "var(--color-brand-alt)",
        "buttonGhostHoverBorderColor": "transparent",
        "buttonGhostHoverTextColor": "var(--color-neutral-subtlest)",
        "tagDefaultBgColor": "var(--color-brand-subtle)",
        "tagDefaultBorderColor": "transparent",
        "tagDefaultTextColor": "var(--color-neutral-subtlest)",
        "tagDefaultHoverBgColor": "var(--color-brand-alt)",
        "tagDefaultHoverBorderColor": "transparent",
        "tagDefaultHoverTextColor": "var(--color-neutral-subtlest)",
        "tagAccentBgColor": "var(--color-brand-subtle)",
        "tagAccentBorderColor": "transparent",
        "tagAccentTextColor": "var(--color-neutral-subtlest)",
        "tagAccentHoverBgColor": "var(--color-brand-alt)",
        "tagAccentHoverBorderColor": "transparent",
        "tagAccentHoverTextColor": "var(--color-neutral-subtlest)",
    },
    # x_supercar (2026-07-21, live-demo QA corrections): Primary was already
    # correct as CSS-derived (fill=brand #bc1212, hover fill=neutral-boldest
    # black) -- no change needed there. Ghost/Link/Tag all needed correction:
    "x_supercar": {
        # Ghost: CSS gives no per-family signal (button_darkBG_style aliases
        # lightBG, no distinct Ghost mixin) -- the auto-derived brand-bold/
        # boldest text was wrong per live-demo; user wants plain black default,
        # brand red on hover.
        "buttonGhostTextColor": "var(--color-neutral-boldest)",
        "buttonGhostHoverTextColor": "var(--color-brand)",
        # Link Default (2026-07-21, refined): black default, brand red on
        # hover, no underline (linkHoverTextDecoration root override below).
        # Was briefly brand-subtle on hover in an earlier round -- corrected
        # to plain brand.
        "linkDefaultHoverColor": "var(--color-brand)",
        # Link Accent (2026-07-21, refined): default=brand, hover=brand-bold
        # (dark red) -- was neutral-boldest (black) in an earlier round,
        # corrected so Accent's hover stays within the red family instead of
        # matching Default's black-adjacent look.
        "linkAccentColor": "var(--color-brand)",
        "linkAccentHoverColor": "var(--color-brand-bold)",
        # Tag (Default + Accent, same treatment): auto-derived registry filled
        # these with a solid subtlest/subtle bg, which doesn't match the live
        # demo at all -- outline style instead (transparent bg, brand
        # border+text), hover flips border+text to black, bg stays transparent
        # throughout.
        "tagDefaultBgColor": "transparent",
        "tagDefaultBorderColor": "var(--color-brand)",
        "tagDefaultTextColor": "var(--color-brand)",
        "tagDefaultHoverBgColor": "transparent",
        "tagDefaultHoverBorderColor": "var(--color-neutral-boldest)",
        "tagDefaultHoverTextColor": "var(--color-neutral-boldest)",
        "tagAccentBgColor": "transparent",
        "tagAccentBorderColor": "var(--color-brand)",
        "tagAccentTextColor": "var(--color-brand)",
        "tagAccentHoverBgColor": "transparent",
        "tagAccentHoverBorderColor": "var(--color-neutral-boldest)",
        "tagAccentHoverTextColor": "var(--color-neutral-boldest)",
    },
    # x_bluehorizon (2026-07-21, live-demo QA corrections): Primary's
    # CSS-derived values were already correct as-is (outline: border+text=
    # brand, transparent fill; hover: fill=brand, text=white) -- kept
    # unchanged, no override needed. Secondary/Ghost/Tag all needed
    # correction:
    "x_bluehorizon": {
        # bgColor (2026-07-21, bug found while fixing the Subtle/Subtlest
        # swap below): _theme_scheme2_overrides() derives this independently
        # from the raw schemeA_l anchor via a FIXED "schemeA_l -> BrandSubtle"
        # token-name mapping -- it does NOT adapt to the runtime :root
        # override in convert_theme (theme_id == "x_bluehorizon" block) that
        # re-points BrandSubtle to a new value and moves schemeA_l's actual
        # hex (`#f8fbfd`) onto BrandSubtlest instead. Left alone, main-2's own
        # bg would silently resolve to the NEW (wrong, more saturated)
        # BrandSubtle instead of the pale alt-bg it's supposed to be -- this
        # override keeps it pointed at the correct token.
        "bgColor": "var(--color-brand-subtlest)",
        # Secondary: solid brand-subtle fill (not an outline like Primary),
        # dark-navy text; hover matches Primary's hover exactly.
        "buttonSecondaryFillColor": "var(--color-brand-subtle)",
        "buttonSecondaryBorderColor": "transparent",
        "buttonSecondaryTextColor": "var(--color-neutral-boldest)",
        "buttonSecondaryHoverFillColor": "var(--color-brand)",
        "buttonSecondaryHoverBorderColor": "var(--color-brand)",
        "buttonSecondaryHoverTextColor": "var(--color-neutral-subtlest)",
        # Ghost: text color was already correct (brand); hover fill now
        # matches Primary's hover too (was: no fill change, text stayed
        # brand). Hover TEXT (2026-07-21, user correction) kept equal to the
        # default text color (brand) instead of flipping to white -- v4's
        # "Button Link" variant (WidgetButton variant="link") has no token of
        # its own and falls back to these Ghost tokens; its hover has no fill
        # behind it at all, so a white hover text blended into the (white)
        # main-scheme bg. Trade-off, flagged not resolved: this also changes
        # the REAL Ghost widget's hover text to brand-on-brand (fill is still
        # brand from buttonGhostHoverFillColor above) -- accepted as the
        # user's explicit call, not verified against a real Ghost button
        # instance.
        "buttonGhostHoverFillColor": "var(--color-brand)",
        "buttonGhostHoverBorderColor": "var(--color-brand)",
        "buttonGhostHoverTextColor": "var(--color-brand)",
        # Tag (Default + Accent, same treatment): outline style (light-gray
        # border, transparent bg, black text) instead of the CSS-derived
        # registry's filled-pill style -- hover only changes the text color
        # (black -> brand), border/bg stay the same.
        "tagDefaultBgColor": "transparent",
        "tagDefaultBorderColor": "var(--color-neutral-subtle)",
        "tagDefaultTextColor": "var(--color-neutral-boldest)",
        "tagDefaultHoverBgColor": "transparent",
        "tagDefaultHoverBorderColor": "var(--color-neutral-subtle)",
        "tagDefaultHoverTextColor": "var(--color-brand)",
        "tagAccentBgColor": "transparent",
        "tagAccentBorderColor": "var(--color-neutral-subtle)",
        "tagAccentTextColor": "var(--color-neutral-boldest)",
        "tagAccentHoverBgColor": "transparent",
        "tagAccentHoverBorderColor": "var(--color-neutral-subtle)",
        "tagAccentHoverTextColor": "var(--color-brand)",
    },
    # x_swift: NO entry here (2026-07-21) -- this theme is in
    # `_THEME_SCHEME2_MISCLASSIFIED_DARK` (see that set's comment), so
    # `.color-scheme-main-2` is never built for it at all; a prior version of
    # this entry (live-demo QA'd button/tag/link colors) is dead code now that
    # main-2 doesn't exist for this theme -- removed rather than left stale.
    # `_THEME_MAIN_OVERRIDES["x_swift"]` (below) is unaffected -- `.color-
    # scheme-main` is the theme's genuinely light default scheme, unrelated to
    # this fix.
}


# Scoped, one-off `.color-scheme-main` overrides — NOT the general Phase 4 pass (still
# not started, see VERIFIED.md). Standing rule from the user (2026-07-20, not a
# blanket policy — decided per theme, not auto-applied to all 29): button colors
# should generally match across main/main-2, and across inverse/inverse-2, UNLESS a
# specific pairing collides with its own background (handled per-theme when it comes
# up, not pre-emptively). x_oasis + x_petfriendly: user asked explicitly for main's
# button/tag colors to match main-2's — verbatim copy of the button/tag keys from
# _theme_scheme2_overrides()[theme_id] (post `_THEME_MAIN2_OVERRIDES`, i.e. the
# corrected values, kept in sync).
_THEME_MAIN_OVERRIDES = {
    "x_oasis": {
        "buttonPrimaryFillColor": "var(--color-brand)",
        "buttonPrimaryHoverFillColor": "var(--color-brand-bold)",
        "buttonPrimaryTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryBorderColor": "var(--color-brand)",
        "buttonSecondaryTextColor": "var(--color-brand)",
        "buttonSecondaryHoverFillColor": "var(--color-brand)",
        "buttonSecondaryHoverBorderColor": "var(--color-brand)",
        "buttonSecondaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostBorderColor": "var(--color-brand)",
        "buttonGhostHoverBorderColor": "var(--color-brand)",
        "buttonGhostTextColor": "var(--color-brand)",
        "buttonGhostHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverFillColor": "var(--color-brand)",
        "tagDefaultBgColor": "transparent",
        "tagDefaultHoverBgColor": "transparent",
        "tagDefaultBorderColor": "var(--color-neutral-boldest)",
        "tagDefaultHoverBorderColor": "var(--color-brand)",
        "tagDefaultTextColor": "var(--color-neutral-boldest)",
        "tagDefaultHoverTextColor": "var(--color-brand)",
        "tagAccentBgColor": "transparent",
        "tagAccentHoverBgColor": "transparent",
        "tagAccentBorderColor": "var(--color-neutral-boldest)",
        "tagAccentHoverBorderColor": "var(--color-brand)",
        "tagAccentTextColor": "var(--color-neutral-boldest)",
        "tagAccentHoverTextColor": "var(--color-brand)",
    },
    "x_petfriendly": {
        # linkAccentColor (2026-07-21): same BrandBold→Brand repoint as
        # _THEME_MAIN2_OVERRIDES above, kept in sync -- see that entry's comment.
        "linkAccentColor": "var(--color-brand)",
        "buttonPrimaryFillColor": "var(--color-brand)",
        "buttonPrimaryHoverFillColor": "var(--color-neutral-boldest)",
        "buttonPrimaryTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryFillColor": "var(--color-brand-alt)",
        "buttonSecondaryHoverFillColor": "var(--color-neutral-boldest)",
        "buttonSecondaryTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostBorderColor": "var(--color-brand)",
        "buttonGhostHoverBorderColor": "var(--color-brand)",
        "buttonGhostTextColor": "var(--color-brand)",
        "buttonGhostHoverFillColor": "var(--color-neutral-boldest)",
        "buttonGhostHoverTextColor": "var(--color-neutral-subtlest)",
        "tagDefaultBgColor": "transparent",
        "tagDefaultHoverBgColor": "var(--color-neutral-boldest)",
        "tagDefaultBorderColor": "var(--color-neutral-boldest)",
        "tagDefaultHoverBorderColor": "var(--color-brand)",
        "tagDefaultTextColor": "var(--color-neutral-boldest)",
        "tagDefaultHoverTextColor": "var(--color-neutral-subtlest)",
        "tagAccentBgColor": "transparent",
        "tagAccentHoverBgColor": "var(--color-neutral-boldest)",
        "tagAccentBorderColor": "var(--color-neutral-boldest)",
        "tagAccentHoverBorderColor": "var(--color-brand)",
        "tagAccentTextColor": "var(--color-neutral-boldest)",
        "tagAccentHoverTextColor": "var(--color-neutral-subtlest)",
    },
    # x_playground (2026-07-21): same button/tag values as _THEME_MAIN2_OVERRIDES
    # (see that entry's comment) -- user said "light scheme" covering both main and
    # main-2, since v3's own CSS doesn't distinguish between them either (one
    # generic mixin, not scoped per v4 scheme). titleTextColor DOES need an
    # explicit override here (unlike main-2, which already got it for free from
    # the CSS-derived registry) -- v4 Base's own main template defaults it to
    # neutral-boldest, not this theme's brand purple.
    "x_playground": {
        "titleTextColor": "var(--color-brand)",
        # Link (2026-07-21): copied verbatim from main-2's values (incl. the
        # linkAccentColor fix) so main and main-2 stay in sync, same as
        # everything else in this theme's entry.
        "linkDefaultColor": "var(--color-neutral-boldest)",
        "linkDefaultHoverColor": "var(--color-brand)",
        "linkAccentColor": "var(--color-brand-subtle)",
        "linkAccentHoverColor": "var(--color-brand)",
        "buttonPrimaryFillColor": "var(--color-brand-subtle)",
        "buttonPrimaryBorderColor": "transparent",
        "buttonPrimaryTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverFillColor": "var(--color-brand-alt)",
        "buttonPrimaryHoverBorderColor": "var(--color-brand-alt)",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-subtlest)",
        # Secondary (2026-07-21): outline, distinct from Primary's solid fill
        # (they'd looked identical since Primary was unified with this same
        # brand-subtle/brand-alt palette). Hover border matches hover fill
        # (not left transparent) so the border doesn't visibly vanish mid-
        # transition when the fill color changes.
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryBorderColor": "var(--color-brand-subtle)",
        "buttonSecondaryTextColor": "var(--color-brand-subtle)",
        "buttonSecondaryHoverFillColor": "var(--color-brand-alt)",
        "buttonSecondaryHoverBorderColor": "var(--color-brand-alt)",
        "buttonSecondaryHoverTextColor": "var(--color-neutral-subtlest)",
        # Ghost has no default-fill slot in v4's schema at all (always transparent
        # until hover) -- white text per the user's "always white" instruction would
        # be invisible with no fill behind it against this scheme's light bg, so
        # DEFAULT stays brand-subtle border+text (visible outline) as the one
        # necessary exception; HOVER (which does have a fill slot) follows the
        # instruction exactly: brand-alt fill + white text.
        "buttonGhostBorderColor": "var(--color-brand-subtle)",
        "buttonGhostTextColor": "var(--color-brand-subtle)",
        "buttonGhostHoverFillColor": "var(--color-brand-alt)",
        "buttonGhostHoverBorderColor": "transparent",
        "buttonGhostHoverTextColor": "var(--color-neutral-subtlest)",
        "tagDefaultBgColor": "var(--color-brand-subtle)",
        "tagDefaultBorderColor": "transparent",
        "tagDefaultTextColor": "var(--color-neutral-subtlest)",
        "tagDefaultHoverBgColor": "var(--color-brand-alt)",
        "tagDefaultHoverBorderColor": "transparent",
        "tagDefaultHoverTextColor": "var(--color-neutral-subtlest)",
        "tagAccentBgColor": "var(--color-brand-subtle)",
        "tagAccentBorderColor": "transparent",
        "tagAccentTextColor": "var(--color-neutral-subtlest)",
        "tagAccentHoverBgColor": "var(--color-brand-alt)",
        "tagAccentHoverBorderColor": "transparent",
        "tagAccentHoverTextColor": "var(--color-neutral-subtlest)",
    },
    # x_supercar (2026-07-21): live-demo QA'd main and main-2 side by side and asked
    # for them to match -- verbatim copy of the button/tag/link keys from
    # _theme_scheme2_overrides()["x_supercar"] post `_THEME_MAIN2_OVERRIDES` (i.e.
    # the corrected values above), kept in sync, same pattern as oasis/petfriendly/
    # playground.
    "x_supercar": {
        "linkDefaultColor": "var(--color-neutral-boldest)",
        "linkDefaultHoverColor": "var(--color-brand)",
        "linkAccentColor": "var(--color-brand)",
        "linkAccentHoverColor": "var(--color-brand-bold)",
        "buttonPrimaryFillColor": "var(--color-brand)",
        "buttonPrimaryBorderColor": "transparent",
        "buttonPrimaryTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverFillColor": "var(--color-neutral-boldest)",
        "buttonPrimaryHoverBorderColor": "transparent",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryBorderColor": "var(--color-brand)",
        "buttonSecondaryTextColor": "var(--color-brand)",
        "buttonSecondaryHoverFillColor": "var(--color-brand)",
        "buttonSecondaryHoverBorderColor": "var(--color-brand)",
        "buttonSecondaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostBorderColor": "transparent",
        "buttonGhostTextColor": "var(--color-neutral-boldest)",
        "buttonGhostHoverBorderColor": "transparent",
        "buttonGhostHoverFillColor": "transparent",
        "buttonGhostHoverTextColor": "var(--color-brand)",
        "tagDefaultBgColor": "transparent",
        "tagDefaultBorderColor": "var(--color-brand)",
        "tagDefaultTextColor": "var(--color-brand)",
        "tagDefaultHoverBgColor": "transparent",
        "tagDefaultHoverBorderColor": "var(--color-neutral-boldest)",
        "tagDefaultHoverTextColor": "var(--color-neutral-boldest)",
        "tagAccentBgColor": "transparent",
        "tagAccentBorderColor": "var(--color-brand)",
        "tagAccentTextColor": "var(--color-brand)",
        "tagAccentHoverBgColor": "transparent",
        "tagAccentHoverBorderColor": "var(--color-neutral-boldest)",
        "tagAccentHoverTextColor": "var(--color-neutral-boldest)",
    },
    # x_bluehorizon (2026-07-21): `.color-scheme-main` had NOTHING for this
    # theme until now (no entry existed) -- user live-demo QA'd main/main-2
    # side by side and asked for Button/Tag to match; verbatim copy of the
    # corrected values from _THEME_MAIN2_OVERRIDES["x_bluehorizon"] above
    # (Primary was already correct there as CSS-derived, restated here since
    # main needs it stated explicitly). Link/bg/text/title not requested this
    # round -- left unset, main still inherits Base for those until asked.
    "x_bluehorizon": {
        "buttonPrimaryFillColor": "transparent",
        "buttonPrimaryBorderColor": "var(--color-brand)",
        "buttonPrimaryTextColor": "var(--color-brand)",
        "buttonPrimaryHoverFillColor": "var(--color-brand)",
        "buttonPrimaryHoverBorderColor": "var(--color-brand)",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryFillColor": "var(--color-brand-subtle)",
        "buttonSecondaryBorderColor": "transparent",
        "buttonSecondaryTextColor": "var(--color-neutral-boldest)",
        "buttonSecondaryHoverFillColor": "var(--color-brand)",
        "buttonSecondaryHoverBorderColor": "var(--color-brand)",
        "buttonSecondaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostTextColor": "var(--color-brand)",
        "buttonGhostHoverFillColor": "var(--color-brand)",
        "buttonGhostHoverBorderColor": "var(--color-brand)",
        # Ghost hover text (2026-07-21, user correction, kept in sync with
        # _THEME_MAIN2_OVERRIDES above) -- see that entry's comment for the
        # "Button Link" fallback reasoning and the real-Ghost trade-off.
        "buttonGhostHoverTextColor": "var(--color-brand)",
        "tagDefaultBgColor": "transparent",
        "tagDefaultBorderColor": "var(--color-neutral-subtle)",
        "tagDefaultTextColor": "var(--color-neutral-boldest)",
        "tagDefaultHoverBgColor": "transparent",
        "tagDefaultHoverBorderColor": "var(--color-neutral-subtle)",
        "tagDefaultHoverTextColor": "var(--color-brand)",
        "tagAccentBgColor": "transparent",
        "tagAccentBorderColor": "var(--color-neutral-subtle)",
        "tagAccentTextColor": "var(--color-neutral-boldest)",
        "tagAccentHoverBgColor": "transparent",
        "tagAccentHoverBorderColor": "var(--color-neutral-subtle)",
        "tagAccentHoverTextColor": "var(--color-brand)",
    },
    # x_swift (2026-07-21): main synced to match main-2 -- verbatim copy of the
    # button/tag/link keys from _THEME_MAIN2_OVERRIDES["x_swift"] above.
    "x_swift": {
        "buttonPrimaryFillColor": "var(--color-brand)",
        "buttonPrimaryBorderColor": "transparent",
        "buttonPrimaryTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverFillColor": "var(--color-neutral-boldest)",
        "buttonPrimaryHoverBorderColor": "transparent",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryBorderColor": "var(--color-neutral)",
        "buttonSecondaryTextColor": "var(--color-neutral)",
        "buttonSecondaryHoverFillColor": "var(--color-neutral-boldest)",
        "buttonSecondaryHoverBorderColor": "var(--color-neutral-boldest)",
        "buttonSecondaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostTextColor": "var(--color-brand)",
        "buttonGhostHoverFillColor": "var(--color-neutral-boldest)",
        "buttonGhostHoverBorderColor": "transparent",
        "buttonGhostHoverTextColor": "var(--color-neutral-subtlest)",
        "linkAccentColor": "var(--color-brand)",
        "linkAccentHoverColor": "var(--color-neutral-boldest)",
        "linkDefaultHoverColor": "var(--color-brand)",
        "tagDefaultBgColor": "var(--color-neutral-subtle)",
        "tagDefaultBorderColor": "transparent",
        "tagDefaultTextColor": "var(--color-neutral-boldest)",
        "tagDefaultHoverBgColor": "var(--color-neutral-subtle)",
        "tagDefaultHoverBorderColor": "transparent",
        "tagDefaultHoverTextColor": "var(--color-brand)",
        "tagAccentBgColor": "var(--color-brand-subtlest)",
        "tagAccentBorderColor": "transparent",
        "tagAccentTextColor": "var(--color-brand-bold)",
        "tagAccentHoverBgColor": "var(--color-brand-subtlest)",
        "tagAccentHoverBorderColor": "transparent",
        "tagAccentHoverTextColor": "var(--color-brand)",
    },
    # x_elite (2026-08-04, live-demo QA'd): main scheme had NO override before
    # (pure v4-base defaults), which is why buttons/tag/link were wrong on the
    # live demo -- this is the first pass, sourced from the user's own
    # devtools hex read of the live main-scheme demo (not derived from CSS).
    "x_elite": {
        "buttonPrimaryFillColor": "var(--color-brand)",
        "buttonPrimaryBorderColor": "var(--color-brand)",
        "buttonPrimaryTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverFillColor": "transparent",
        "buttonPrimaryHoverBorderColor": "var(--color-brand)",
        "buttonPrimaryHoverTextColor": "var(--color-brand)",
        # Secondary hover is a text-decoration (underline) change in the live
        # demo, not a color change -- v4 has no underline-on-hover button
        # token, so hover colors are kept identical to default (no-op).
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryBorderColor": "var(--color-brand)",
        "buttonSecondaryTextColor": "var(--color-brand)",
        "buttonSecondaryHoverFillColor": "transparent",
        "buttonSecondaryHoverBorderColor": "var(--color-brand)",
        "buttonSecondaryHoverTextColor": "var(--color-brand)",
        # Tag border is `rgba(0,5,0,.15)` on the live demo -- this theme's
        # neutral-boldest anchor (`#000500`) at 15% alpha, no v4 var()+alpha
        # mechanism exists so kept as a literal 8-digit hex (user-confirmed
        # this is fine, e.g. `#ffffff88` elsewhere in this session).
        "tagDefaultBgColor": "transparent",
        "tagDefaultBorderColor": "#00050026",
        "tagDefaultTextColor": "var(--color-brand-alt)",
        "tagDefaultHoverBgColor": "var(--color-brand)",
        "tagDefaultHoverBorderColor": "var(--color-brand-alt)",
        "tagDefaultHoverTextColor": "var(--color-neutral-subtlest)",
        # Accent tag: not covered by the user's corrections -- mirrors
        # Default verbatim as a placeholder, same treatment as the inverse
        # scheme's Accent tag.
        "tagAccentBgColor": "transparent",
        "tagAccentBorderColor": "#00050026",
        "tagAccentTextColor": "var(--color-brand-alt)",
        "tagAccentHoverBgColor": "var(--color-brand)",
        "tagAccentHoverBorderColor": "var(--color-brand-alt)",
        "tagAccentHoverTextColor": "var(--color-neutral-subtlest)",
        "linkDefaultColor": "var(--color-brand-alt)",
        "linkDefaultHoverColor": "var(--color-brand-alt)",
        "linkAccentColor": "var(--color-brand)",
        "linkAccentHoverColor": "var(--color-brand)",
    },
    # x_mixednuts (2026-08-06, user-supplied, main == main-2 verbatim -- the exact
    # same values are also set in `_THEME_MAIN2_FROM_MAIN["x_mixednuts"]` below,
    # kept in sync since the user gave one shared spec for both schemes). Primary
    # solid brand green default, hover flips to solid neutral-boldest (dark
    # brown, this theme's real anchor for "brown"); Secondary outline green
    # border/text, hover flips to solid neutral-boldest fill + white text; Ghost
    # text=brand green, hover bg=neutral (this theme's closest anchor to a true
    # grey -- the others are all brown-tinted) with text UNCHANGED; Link Default
    # brown, no hover color change (relies on v4-base's own
    # `linkHoverTextDecoration:underline`); Link Accent green, hover brown; Tag
    # transparent/green border+text, hover only tints the bg to brand-subtlest
    # (palest green), border/text unchanged.
    "x_mixednuts": {
        "buttonPrimaryFillColor": "var(--color-brand)",
        "buttonPrimaryBorderColor": "var(--color-brand)",
        "buttonPrimaryTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverFillColor": "var(--color-neutral-boldest)",
        "buttonPrimaryHoverBorderColor": "var(--color-neutral-boldest)",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryBorderColor": "var(--color-brand)",
        "buttonSecondaryTextColor": "var(--color-brand)",
        "buttonSecondaryHoverFillColor": "var(--color-neutral-boldest)",
        "buttonSecondaryHoverBorderColor": "var(--color-neutral-boldest)",
        "buttonSecondaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostTextColor": "var(--color-brand)",
        "buttonGhostHoverFillColor": "var(--color-neutral)",
        "buttonGhostHoverBorderColor": "transparent",
        "buttonGhostHoverTextColor": "var(--color-brand)",
        # Tag Default (2026-08-06, user correction): border/text green -> brown
        # (neutral-boldest) -- now deliberately DIFFERENT from Accent, which
        # stays green. Hover border/text stay unchanged-through-hover (same
        # convention as before), just now brown; hover bg untouched.
        "tagDefaultBgColor": "transparent",
        "tagDefaultBorderColor": "var(--color-neutral-boldest)",
        "tagDefaultTextColor": "var(--color-neutral-boldest)",
        "tagDefaultHoverBgColor": "var(--color-brand-subtlest)",
        "tagDefaultHoverBorderColor": "var(--color-neutral-boldest)",
        "tagDefaultHoverTextColor": "var(--color-neutral-boldest)",
        "tagAccentBgColor": "transparent",
        "tagAccentBorderColor": "var(--color-brand)",
        "tagAccentTextColor": "var(--color-brand)",
        "tagAccentHoverBgColor": "var(--color-brand-subtlest)",
        "tagAccentHoverBorderColor": "var(--color-brand)",
        "tagAccentHoverTextColor": "var(--color-brand)",
        "linkDefaultColor": "var(--color-neutral-boldest)",
        "linkDefaultHoverColor": "var(--color-neutral-boldest)",
        "linkAccentColor": "var(--color-brand)",
        "linkAccentHoverColor": "var(--color-neutral-boldest)",
    },
    # x_petestate (2026-08-07, DRAFT -- NOT yet fully live-demo QA'd, Tag
    # confirmed by user directly): main scheme had NO override before (pure
    # v4-base defaults). Primary grounded from `--button_lightBG_style`
    # (palette CSS): solid navy fill (neutral-boldest), white text; hover
    # flips to solid brand (yellow) fill, text STAYS navy. Secondary
    # (`.btn_secondary`, theme CSS, light/default variant) is a byte-for-byte
    # duplicate of Primary's colors, same as the inverse scheme's `.darkMode
    # .btn_secondary` -- drafted as an OUTLINE of Primary instead (this
    # project's standing "primary==secondary solid -> outline" convention),
    # not literally CSS-grounded as an outline. Tag (`.btnTag`, unconditional,
    # same rule as inverse) user-confirmed directly 2026-08-07: transparent
    # fill, brand-alt (teal) border+text; hover border+fill flip to brand
    # (yellow), text goes dark (neutral-boldest). Link grounded from
    # `--link_lightBG_style`/`--linkArticle_lightBG_style`: Default navy,
    # hover teal; Accent teal, hover navy (mirrors Default, flipped). Ghost
    # has zero CSS grounding -- placeholder mirroring Link's hover-to-teal
    # pattern, unconfirmed.
    "x_petestate": {
        "buttonPrimaryFillColor": "var(--color-neutral-boldest)",
        "buttonPrimaryBorderColor": "transparent",
        "buttonPrimaryTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverFillColor": "var(--color-brand)",
        "buttonPrimaryHoverBorderColor": "transparent",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-boldest)",
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryBorderColor": "var(--color-neutral-boldest)",
        "buttonSecondaryTextColor": "var(--color-neutral-boldest)",
        "buttonSecondaryHoverFillColor": "transparent",
        "buttonSecondaryHoverBorderColor": "var(--color-brand)",
        "buttonSecondaryHoverTextColor": "var(--color-brand)",
        "buttonGhostTextColor": "var(--color-neutral-boldest)",
        "buttonGhostHoverFillColor": "transparent",
        "buttonGhostHoverBorderColor": "transparent",
        "buttonGhostHoverTextColor": "var(--color-brand-alt)",
        "tagDefaultBgColor": "transparent",
        "tagDefaultBorderColor": "var(--color-brand-alt)",
        "tagDefaultTextColor": "var(--color-brand-alt)",
        "tagDefaultHoverBgColor": "var(--color-brand)",
        "tagDefaultHoverBorderColor": "var(--color-brand)",
        "tagDefaultHoverTextColor": "var(--color-neutral-boldest)",
        "tagAccentBgColor": "transparent",
        "tagAccentBorderColor": "var(--color-brand-alt)",
        "tagAccentTextColor": "var(--color-brand-alt)",
        "tagAccentHoverBgColor": "var(--color-brand)",
        "tagAccentHoverBorderColor": "var(--color-brand)",
        "tagAccentHoverTextColor": "var(--color-neutral-boldest)",
        "linkDefaultColor": "var(--color-neutral-boldest)",
        "linkDefaultHoverColor": "var(--color-brand-alt)",
        "linkAccentColor": "var(--color-brand-alt)",
        "linkAccentHoverColor": "var(--color-neutral-boldest)",
    },
}


# Per-theme `.color-scheme-inverse` overrides — for a theme whose v3 darkMode is a
# white-text-on-colored scheme (an INVERSE pattern), distinct from its main-2 alt bg.
# x_bakery: the footer's `.footerLayout &.darkMode` rule (theme-x_bakery.partial.css) —
# background var(--color_schemeA) = brand (red), text/titles/links var(--color_light) =
# white, link hover var(--color_schemeB) = brand-alt. (Content darkMode sections are a
# separate cream/black alt bg → they use .color-scheme-main-2 from _theme_scheme2_overrides().)
# x_denim_fw: the footer's `.footerLayout &.darkMode` rule (theme-x_denim_fw.partial.css) —
# background var(--color_dark) = neutral-boldest (black), text/titles var(--color_light) =
# neutral-subtlest (white), link hover var(--color_light50) (~50%-opacity white — no v4
# anchor for this "N% opacity" family, kept as a literal rgba). Buttons/tags: the footer's
# `.darkMode` doesn't override `.btn_primary`/`.btn_secondary`/`.btn_tertiary`/`.tag`/
# `.btnTag` (only `.joinButton`, which is v4's WidgetJoin — not a themed token), so per v3's
# own CSS cascade they inherit the theme's generic `pbutton_darkBG_style`/`sbutton_darkBG_style`/
# `tbutton_darkBG_style`/`buttontag_darkBG_style` mixins — the exact same ones already resolved
# for `.color-scheme-main-2` — so those tokens are copied verbatim from
# _theme_scheme2_overrides()["x_denim_fw"]. Live-demo confirmed bg/text qualitatively (dark
# bg, white text); buttons/tags are mixin-faithful but unverified visually (no Button/Tag
# widget present in the footer's actual content).
# Hand-authored, one theme at a time; layered over _scheme_inverse_template() by _build_inverse().
_THEME_INVERSE = {
    "x_bakery": {
        "bgColor": "var(--color-brand)",
        "textColor": "var(--color-white)",
        "textSubtleColor": "var(--color-white)",
        "titleTextColor": "var(--color-white)",
        "captionTextColor": "var(--color-white)",
        "descriptionTextColor": "var(--color-white)",
        "linkDefaultColor": "var(--color-white)",
        "linkDefaultHoverColor": "var(--color-brand-alt)",
        "linkAccentColor": "var(--color-white)",
        "linkAccentHoverColor": "var(--color-brand-alt)",
        # Buttons follow the inverse convention (colored/dark bg → flip): PRIMARY is
        # solid-inverted (light fill, dark text) = flip of main-2's red-fill/white-text →
        # white fill + brand text; SECONDARY is the outline (transparent, white
        # border+text, hover brand-alt); GHOST is transparent/no-border with contrasting
        # (white) text. primary & secondary stay opposite styles, per v4.
        "buttonPrimaryFillColor": "var(--color-white)",
        "buttonPrimaryBorderColor": "var(--color-white)",
        "buttonPrimaryTextColor": "var(--color-brand)",
        "buttonPrimaryBoxShadow": "none",
        "buttonPrimaryBoxShadowColor": "transparent",
        "buttonPrimaryHoverFillColor": "var(--color-brand-alt)",
        "buttonPrimaryHoverBorderColor": "var(--color-brand-alt)",
        "buttonPrimaryHoverTextColor": "var(--color-brand)",
        "buttonPrimaryHoverBoxShadow": "none",
        "buttonPrimaryHoverBoxShadowColor": "transparent",
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryBorderColor": "var(--color-white)",
        "buttonSecondaryTextColor": "var(--color-white)",
        "buttonSecondaryBoxShadow": "none",
        "buttonSecondaryBoxShadowColor": "transparent",
        "buttonSecondaryHoverFillColor": "transparent",
        "buttonSecondaryHoverBorderColor": "var(--color-brand-alt)",
        "buttonSecondaryHoverTextColor": "var(--color-brand-alt)",
        "buttonSecondaryHoverBoxShadow": "none",
        "buttonSecondaryHoverBoxShadowColor": "transparent",
        "buttonGhostBorderColor": "transparent",
        "buttonGhostTextColor": "var(--color-white)",
        "buttonGhostHoverFillColor": "transparent",
        "buttonGhostHoverBorderColor": "transparent",
        "buttonGhostHoverTextColor": "var(--color-brand-alt)"
    },
    "x_denim_fw": {
        "bgColor": "var(--color-neutral-boldest)",
        "textColor": "var(--color-neutral-subtlest)",
        "textSubtleColor": "var(--color-neutral-subtlest)",
        "titleTextColor": "var(--color-neutral-subtlest)",
        "captionTextColor": "var(--color-neutral-subtlest)",
        "descriptionTextColor": "var(--color-neutral-subtlest)",
        "linkDefaultColor": "var(--color-neutral-subtlest)",
        "linkDefaultHoverColor": "var(--color-brand-subtle)",
        "linkAccentColor": "var(--color-brand-subtle)",
        "linkAccentHoverColor": "var(--color-neutral-subtlest)",
        # Buttons/tags: footer's `.darkMode` doesn't override `.btn_primary`/`.tag`/
        # `.btnTag` (only `.joinButton`, not v4-themeable — see comment above), so
        # bg/fill/hover-fill are copied verbatim from main-2's darkBG mixins. But
        # DEFAULT (non-hover) border/text for Secondary/Ghost/Tag were corrected
        # 2026-07-17 per live-demo QA: literal `.joinButton` CSS (the one concrete
        # darkMode button in this theme) shows a WHITE default border+text, brand
        # only on hover — not brand-by-default as first drafted. Tag default was
        # also literally invisible (black border/text on the black bg) until fixed.
        "buttonPrimaryFillColor": "var(--color-brand)",
        "buttonPrimaryBorderColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryBoxShadow": "none",
        "buttonPrimaryBoxShadowColor": "transparent",
        "buttonPrimaryHoverFillColor": "var(--color-neutral-boldest)",
        "buttonPrimaryHoverBorderColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverBoxShadow": "none",
        "buttonPrimaryHoverBoxShadowColor": "transparent",
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryHoverFillColor": "var(--color-brand)",
        "buttonSecondaryBorderColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverBorderColor": "var(--color-brand)",
        "buttonSecondaryTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostBorderColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverBorderColor": "var(--color-brand)",
        "buttonGhostTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverFillColor": "var(--color-brand)",
        "tagDefaultBgColor": "transparent",
        "tagDefaultHoverBgColor": "transparent",
        "tagDefaultBorderColor": "var(--color-neutral-subtlest)",
        "tagDefaultHoverBorderColor": "var(--color-brand)",
        "tagDefaultTextColor": "var(--color-neutral-subtlest)",
        "tagDefaultHoverTextColor": "var(--color-brand)",
        "tagAccentBgColor": "transparent",
        "tagAccentHoverBgColor": "transparent",
        "tagAccentBorderColor": "var(--color-neutral-subtlest)",
        "tagAccentHoverBorderColor": "var(--color-brand)",
        "tagAccentTextColor": "var(--color-neutral-subtlest)",
        "tagAccentHoverTextColor": "var(--color-brand)"
    },
    # x_luxurygold: the footer's `.footerLayout &.darkMode` rule (theme-x_luxurygold.
    # partial.css) — no base (non-darkMode) footer style exists at all in this theme's
    # own CSS, only the darkMode variant. background var(--color_dark) = neutral-boldest
    # (#222222, dark gray not literal black), text var(--color_light) = neutral-subtlest
    # (white). Plain link color var(--color_light50) (~50%-opacity white, same
    # unresolvable "N%-opacity" family as denim_fw — approximated here with the
    # `neutral-subtle` anchor, #e4e4e4, a light gray that reads similarly on a dark bg).
    # Link hover: live-demo QA 2026-07-17 corrected both Default and Accent hover to
    # `var(--color-brand)` (gold #e0c06e) — the literal footer CSS's `--color_light`
    # (full white) guess wasn't what the user wanted visually; no distinct accent-link
    # style exists in the footer CSS either way, so Accent mirrors Default throughout.
    # Buttons: unlike denim_fw, this theme's OWN `pbutton_darkBG_style`/
    # `sbutton_darkBG_style`/`buttontag_darkBG_style` mixins are literally aliases of
    # their `_lightBG_style` counterparts (no genuine darkBG-specific style authored) —
    # so Primary is safely reused verbatim from main-2 (solid gold fill #e0c06e, white
    # text, no border — `border: 0` in `--button_lightBG_style`). Secondary/Ghost/Tag:
    # v4 synthesizes an outline-of-primary (brand border+text) since v3 gave no distinct
    # secondary mixin, but per the x_denim_fw lesson this theme's own literal
    # `.joinButton` darkMode CSS shows a WHITE default border+text with gold only on
    # hover (border AND text both flip to gold on hover, not just one — a real
    # per-theme difference from denim_fw, where hover only changed the button's fill and
    # text stayed white) — corrected to match that literal pattern rather than the
    # synthesized brand default.
    "x_luxurygold": {
        "bgColor": "var(--color-neutral-boldest)",
        "textColor": "var(--color-neutral-subtlest)",
        "textSubtleColor": "var(--color-neutral-subtlest)",
        "titleTextColor": "var(--color-neutral-subtlest)",
        "captionTextColor": "var(--color-neutral-subtlest)",
        "descriptionTextColor": "var(--color-neutral-subtlest)",
        "linkDefaultColor": "var(--color-neutral-subtle)",
        "linkDefaultHoverColor": "var(--color-brand)",
        "linkAccentColor": "var(--color-neutral-subtle)",
        "linkAccentHoverColor": "var(--color-brand)",
        "buttonPrimaryFillColor": "var(--color-brand)",
        "buttonPrimaryBorderColor": "transparent",
        "buttonPrimaryTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryBoxShadow": "none",
        "buttonPrimaryBoxShadowColor": "transparent",
        "buttonPrimaryHoverFillColor": "var(--color-brand-bold)",
        "buttonPrimaryHoverBorderColor": "transparent",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverBoxShadow": "none",
        "buttonPrimaryHoverBoxShadowColor": "transparent",
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryHoverFillColor": "transparent",
        "buttonSecondaryBorderColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverBorderColor": "var(--color-brand)",
        "buttonSecondaryTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverTextColor": "var(--color-brand)",
        "buttonGhostBorderColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverBorderColor": "var(--color-brand)",
        "buttonGhostTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverTextColor": "var(--color-brand)",
        "buttonGhostHoverFillColor": "transparent",
        "tagDefaultBgColor": "transparent",
        "tagDefaultHoverBgColor": "transparent",
        "tagDefaultBorderColor": "var(--color-neutral-subtlest)",
        "tagDefaultHoverBorderColor": "var(--color-brand-bold)",
        "tagDefaultTextColor": "var(--color-neutral-subtlest)",
        "tagDefaultHoverTextColor": "var(--color-brand-bold)",
        "tagAccentBgColor": "transparent",
        "tagAccentHoverBgColor": "transparent",
        "tagAccentBorderColor": "var(--color-neutral-subtlest)",
        "tagAccentHoverBorderColor": "var(--color-brand-bold)",
        "tagAccentTextColor": "var(--color-neutral-subtlest)",
        "tagAccentHoverTextColor": "var(--color-brand-bold)"
    },
    # x_oasis: BOTH `.headerLayout .darkMode`/`.footerLayout &.darkMode` (theme-x_oasis.
    # partial.css) — the first theme in this batch where header AND footer are
    # genuinely dark, and (unlike denim_fw/luxurygold) they use the SAME bg/text, so one
    # shared inverse scheme is architecturally correct for both. background
    # var(--color_schemeA) = brand (green #40966c) — genuinely brand-colored, not
    # near-black/gray like the previous 2 themes. text var(--color_light) = white.
    # This changes the calculus for hover colors: denim_fw/luxurygold's live-demo-
    # confirmed "hover = brand" pattern would be brand-ON-brand here (invisible) since
    # the bg itself IS the brand color — chose the muted `neutral-subtle` (#e0e0e0,
    # approximating var(--color_light75), same unresolvable "N%-opacity" family as the
    # other 2 themes) instead, matching the theme's own literal intent (a dimmed white,
    # not a color shift) — flagged for live-demo QA same as before.
    # Buttons/tags: same alias situation as x_luxurygold (pbutton/sbutton/tbutton/
    # buttontag darkBG mixins are literal `_lightBG_style` aliases, no genuine darkBG
    # style) — but `_theme_scheme2_overrides()`'s resolved Secondary/Ghost/Tag border+
    # text default to brand (green), which is the SAME hex as this bg → invisible by
    # construction (worse than denim_fw's black-on-black, since it's TWO widget
    # families, not one). Corrected Secondary/Ghost default border+text and Tag's
    # HOVER border+text to white (their hover fill/text already reuses main-2's
    # brand-fill+white-text unchanged — white text stays visible regardless of the
    # fill color, so hover didn't need correcting there, only where a colored
    # border/text sat directly against the matching-color bg). Tag's DEFAULT
    # border+text (black/neutral-boldest) was left as main-2 gives it — black against
    # the medium-brightness green reads as acceptable contrast, unlike the exact-match
    # cases — flagged as a judgment call, not a confirmed read, same as Link.
    "x_oasis": {
        "bgColor": "var(--color-brand)",
        "textColor": "var(--color-neutral-subtlest)",
        "textSubtleColor": "var(--color-neutral-subtlest)",
        "titleTextColor": "var(--color-neutral-subtlest)",
        "captionTextColor": "var(--color-neutral-subtlest)",
        "descriptionTextColor": "var(--color-neutral-subtlest)",
        "linkDefaultColor": "var(--color-neutral-subtlest)",
        "linkDefaultHoverColor": "var(--color-neutral-subtle)",
        "linkAccentColor": "var(--color-neutral-subtlest)",
        "linkAccentHoverColor": "var(--color-neutral-subtle)",
        # 2026-07-17 live-demo QA: Primary's fill (brand, same hex as this bg) and
        # Secondary/Ghost/Tag's hover (fill/border also brand-on-brand) both read as
        # blending into the background — not just a "text stays legible" edge case,
        # a real problem. Switched to a solid "flip" convention instead: default state
        # = white outline (or white-fill for Primary), hover = solid white fill + brand
        # text — guarantees contrast against the brand-colored bg in every state.
        "buttonPrimaryFillColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryBorderColor": "transparent",
        "buttonPrimaryTextColor": "var(--color-brand)",
        "buttonPrimaryBoxShadow": "none",
        "buttonPrimaryBoxShadowColor": "transparent",
        "buttonPrimaryHoverFillColor": "var(--color-brand-bold)",
        "buttonPrimaryHoverBorderColor": "transparent",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverBoxShadow": "none",
        "buttonPrimaryHoverBoxShadowColor": "transparent",
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryHoverFillColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryBorderColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverBorderColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverTextColor": "var(--color-brand)",
        "buttonGhostBorderColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverBorderColor": "var(--color-neutral-subtlest)",
        "buttonGhostTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverTextColor": "var(--color-brand)",
        "buttonGhostHoverFillColor": "var(--color-neutral-subtlest)",
        "tagDefaultBgColor": "transparent",
        "tagDefaultHoverBgColor": "var(--color-neutral-subtlest)",
        "tagDefaultBorderColor": "var(--color-neutral-subtlest)",
        "tagDefaultHoverBorderColor": "var(--color-neutral-subtlest)",
        "tagDefaultTextColor": "var(--color-neutral-subtlest)",
        "tagDefaultHoverTextColor": "var(--color-brand)",
        "tagAccentBgColor": "transparent",
        "tagAccentHoverBgColor": "var(--color-neutral-subtlest)",
        "tagAccentBorderColor": "var(--color-neutral-subtlest)",
        "tagAccentHoverBorderColor": "var(--color-neutral-subtlest)",
        "tagAccentTextColor": "var(--color-neutral-subtlest)",
        "tagAccentHoverTextColor": "var(--color-brand)"
    },
    # x_petfriendly: header's `.headerLayout .darkMode` rule (theme-x_petfriendly.
    # partial.css) — bg var(--color_schemeA) = brand orange `#f46f43`, text
    # var(--color_light) = white; link hover var(--color_dark) (literal black — both
    # header AND footer use this same hover color, no opacity-guess needed this time).
    # First theme in this batch where header/footer genuinely need DIFFERENT bg colors
    # (footer bg = schemeB/blue, not schemeA) — footer gets `.color-scheme-inverse-2`
    # instead (_THEME_INVERSE2), since v4 supports arbitrary `.color-scheme-<name>`
    # classes (confirmed by user 2026-07-20). Buttons/tags: main-2's Primary
    # (brand/orange fill) and footer's Secondary (brand-alt/blue fill) would each be
    # brand-on-brand in ONE of the two zones (not both) — rather than reason a
    # separate exception per zone (the oasis lesson: that kind of per-token judgment
    # call is unreliable), applied ONE consistent flip design to both
    # _THEME_INVERSE/_THEME_INVERSE2 uniformly: white solid fill/outline by default
    # (safe against any bg color), hover flips to each button family's own natural
    # accent (Primary/Ghost/Tag → brand orange, Secondary → brand-alt blue) with a
    # boldest/darker fill so hover is visibly distinct from the zone's own bg too.
    "x_petfriendly": {
        "bgColor": "var(--color-brand)",
        "textColor": "var(--color-neutral-subtlest)",
        "textSubtleColor": "var(--color-neutral-subtlest)",
        "titleTextColor": "var(--color-neutral-subtlest)",
        "captionTextColor": "var(--color-neutral-subtlest)",
        "descriptionTextColor": "var(--color-neutral-subtlest)",
        "linkDefaultColor": "var(--color-neutral-subtlest)",
        "linkDefaultHoverColor": "var(--color-neutral-boldest)",
        "linkAccentColor": "var(--color-neutral-subtlest)",
        "linkAccentHoverColor": "var(--color-neutral-boldest)",
        # General borders (2026-07-20, ported verbatim from a manual edit the
        # user made directly on the generated JSON): white instead of the v4
        # default's black. Literal var(--color-white), matching the user's own
        # choice exactly -- same value as neutral-subtlest for this theme
        # (its neutral-subtlest IS #ffffff) but kept literal, not substituted,
        # to stay faithful to what was hand-edited.
        "borderColor": "var(--color-white)",
        "sectionBorderColor": "var(--color-white)",
        "sectionHeaderBorderColor": "var(--color-white)",
        # Arrows (slider/carousel), same manual-edit source: default icon is
        # brand-colored (not black); hover flips to a solid black fill + white
        # icon -- opposite direction from the Button/Tag hover rule below.
        "arrowsTextColor": "var(--color-brand)",
        "arrowsBorderColor": "var(--color-white)",
        "arrowsHoverBgColor": "var(--color-black)",
        "arrowsHoverTextColor": "var(--color-white)",
        # Outline style by DEFAULT across all buttons (user request, 2026-07-20):
        # white border/transparent fill/white text. HOVER (updated later same
        # day, standing rule for this theme): solid neutral-subtlest (white)
        # fill/bg + neutral-boldest (black) text, uniformly across
        # Primary/Secondary/Ghost/Tag -- the exact opposite of main/main-2's
        # hover rule (see _THEME_MAIN2_OVERRIDES/_THEME_MAIN_OVERRIDES). NOT
        # zone-relative this time (same fixed swap in both inverse/inverse-2) --
        # supersedes the earlier per-widget-family hover designs (light-blue
        # outline, zone's-own-bg text). Link is unaffected, excluded from this
        # rule. Primary's DEFAULT (not hover) was further refined by the same
        # manual edit above: solid white fill (not outline) + brand text, no
        # border -- diverges from Secondary/Ghost, which stay outline by default.
        "buttonPrimaryFillColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryBorderColor": "transparent",
        "buttonPrimaryTextColor": "var(--color-brand)",
        "buttonPrimaryBoxShadow": "none",
        "buttonPrimaryBoxShadowColor": "transparent",
        "buttonPrimaryHoverFillColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverBorderColor": "transparent",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-boldest)",
        "buttonPrimaryHoverBoxShadow": "none",
        "buttonPrimaryHoverBoxShadowColor": "transparent",
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryBorderColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverFillColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverBorderColor": "transparent",
        "buttonSecondaryHoverTextColor": "var(--color-neutral-boldest)",
        "buttonGhostBorderColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverBorderColor": "transparent",
        "buttonGhostTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverTextColor": "var(--color-neutral-boldest)",
        "buttonGhostHoverFillColor": "var(--color-neutral-subtlest)",
        "tagDefaultBgColor": "transparent",
        "tagDefaultBorderColor": "var(--color-neutral-subtlest)",
        "tagDefaultTextColor": "var(--color-neutral-subtlest)",
        "tagDefaultHoverBgColor": "var(--color-neutral-subtlest)",
        "tagDefaultHoverBorderColor": "transparent",
        "tagDefaultHoverTextColor": "var(--color-neutral-boldest)",
        "tagAccentBgColor": "transparent",
        "tagAccentBorderColor": "var(--color-neutral-subtlest)",
        "tagAccentTextColor": "var(--color-neutral-subtlest)",
        "tagAccentHoverBgColor": "var(--color-neutral-subtlest)",
        "tagAccentHoverBorderColor": "transparent",
        "tagAccentHoverTextColor": "var(--color-neutral-boldest)"
    },
    # x_playground: UNUSUAL — the header's colored bg is NOT gated by isDarkMode at
    # all: `.headerPane { background-color: var(--color_schemeA); color: var(--color_
    # light); }` is unconditional (theme-x_playground.partial.css), no `&.darkMode`
    # needed. Confirmed the header's own v3 isDarkMode flag is unset/false in the
    # actual demo, yet the CSS still renders it purple — the isDarkMode-driven
    # colorScheme classification doesn't capture this theme's header at all.
    # tools/regen_demos.py forces header_zone to color-scheme-inverse for this theme
    # specifically (2026-07-20, same scoped/v4-demos-only treatment as petfriendly's
    # footer->inverse-2 rewrite). Footer's OWN `&.darkMode` (isDarkMode IS true in the
    # demo) resolves to the SAME bg (`var(--color_schemeA)`) + text (`var(--color_
    # light)`) as the header's unconditional state, so one shared `.color-scheme-
    # inverse` correctly serves both zones — no inverse-2 needed this time.
    # bg=brand (purple #9486e9), text=neutral-subtlest (white). Link hover grounded
    # from CSS too: both zones use var(--color_schemeB) (yellow, brand-alt) on hover.
    # Tag: reused verbatim from main-2 (this theme's buttontag_darkBG_style mixin
    # aliases its lightBG counterpart, same "no divergence" situation as luxurygold/
    # oasis) — border/text = brand-subtle (teal-green #3ec293 here, this theme's
    # anchors are NOT tints of one hue), safely distinct from the purple bg, no
    # brand-on-brand risk.
    # Buttons: this theme's palette has NO pbutton/sbutton/tbutton mixins at all (only
    # a generic --button_lightBG_style, not matched by our per-family convention) —
    # zero CSS signal, unlike every other theme done so far. Designed from pure
    # convention (Bakery-style Primary flip + petfriendly-style outline
    # Secondary/Ghost), hover -> brand-alt (yellow) fill + dark text for contrast
    # against the bright yellow. Flagged low-confidence, needs live-demo QA more than
    # any other part of this entry.
    "x_playground": {
        "bgColor": "var(--color-brand)",
        "textColor": "var(--color-neutral-subtlest)",
        "textSubtleColor": "var(--color-neutral-subtlest)",
        # title (2026-07-21): white, same as the rest of this scheme's text --
        # user tried brand-alt-subtle (pale yellow) first, then decided white
        # reads better.
        "titleTextColor": "var(--color-neutral-subtlest)",
        "captionTextColor": "var(--color-neutral-subtlest)",
        "descriptionTextColor": "var(--color-neutral-subtlest)",
        "linkDefaultColor": "var(--color-neutral-subtlest)",
        "linkDefaultHoverColor": "var(--color-brand-alt)",
        # linkAccentColor (2026-07-21): pale yellow (brand-alt-subtle), matching
        # the title color -- was neutral-subtlest (white, same as default, no
        # distinction from Link Default).
        "linkAccentColor": "var(--color-brand-alt-subtle)",
        "linkAccentHoverColor": "var(--color-brand-alt)",
        # Primary (2026-07-21): matches main/main-2's button treatment now --
        # brand-subtle (teal) fill, brand-alt (yellow) hover fill, white text
        # always. Was previously a distinct white-fill/brand-text design; user
        # asked to unify it with the light-scheme buttons instead.
        "buttonPrimaryFillColor": "var(--color-brand-subtle)",
        "buttonPrimaryBorderColor": "transparent",
        "buttonPrimaryTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryBoxShadow": "none",
        "buttonPrimaryBoxShadowColor": "transparent",
        "buttonPrimaryHoverFillColor": "var(--color-brand-alt)",
        "buttonPrimaryHoverBorderColor": "var(--color-brand-alt)",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverBoxShadow": "none",
        "buttonPrimaryHoverBoxShadowColor": "transparent",
        # Secondary (2026-07-21): outline default (white, matches this scheme's
        # general look), hover mirrors main/main-2's recipe -- fill+border both
        # go brand-alt (yellow), text white (not the earlier neutral-boldest).
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryBorderColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverFillColor": "var(--color-brand-alt)",
        "buttonSecondaryHoverBorderColor": "var(--color-brand-alt)",
        "buttonSecondaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostBorderColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverBorderColor": "transparent",
        "buttonGhostTextColor": "var(--color-neutral-subtlest)",
        # was neutral-boldest (dark) -- leftover from before the yellow-hover
        # rule, fixed (2026-07-21): white text on the yellow hover fill.
        "buttonGhostHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverFillColor": "var(--color-brand-alt)",
        # Tag (2026-07-21): user said to use the same button-fill pattern for Tag
        # in EVERY scheme, including here -- brand-subtle (teal) fill/brand-alt
        # (yellow) hover fill/white text always. Safe against this inverse's
        # purple bg (teal and yellow are both distinct from brand/purple, no
        # brand-on-brand collision).
        "tagDefaultBgColor": "var(--color-brand-subtle)",
        "tagDefaultBorderColor": "transparent",
        "tagDefaultTextColor": "var(--color-neutral-subtlest)",
        "tagDefaultHoverBgColor": "var(--color-brand-alt)",
        "tagDefaultHoverBorderColor": "transparent",
        "tagDefaultHoverTextColor": "var(--color-neutral-subtlest)",
        "tagAccentBgColor": "var(--color-brand-subtle)",
        "tagAccentBorderColor": "transparent",
        "tagAccentTextColor": "var(--color-neutral-subtlest)",
        "tagAccentHoverBgColor": "var(--color-brand-alt)",
        "tagAccentHoverBorderColor": "transparent",
        "tagAccentHoverTextColor": "var(--color-neutral-subtlest)"
    },
    # x_supercar (drafted 2026-07-21, NOT yet live-demo QA'd): header's `.headerPane`/
    # `.subHeaderPane` background is UNCONDITIONAL CSS (`background-color: var(--color_
    # dark)`, no `&.darkMode` gate needed) -- same unconditional-header pattern as
    # x_playground -- but v3's own demo already has isDarkMode:True set on both header
    # panes anyway (unlike playground, where it was unset), so no
    # `_FORCE_HEADER_INVERSE` entry needed here; standard conversion already tags it
    # inverse. Footer's `.footerLayout &.darkMode` resolves to the SAME bg (`var(--
    # color_dark)`, #171717) + text (`var(--color_light)`, white) as the header --
    # one shared `.color-scheme-inverse` covers both, no inverse-2 needed.
    # Link: headerPane's primary nav hovers to `var(--color_schemeA_l)` (brand-subtle,
    # bright red #fd1313); subHeaderPane's own links hover to `var(--color_schemeA)`
    # (brand, #bc1212) instead -- a genuine distinction between two link contexts in
    # this theme's CSS, mapped onto Link Default (headerPane, more prominent) vs Link
    # Accent (subHeaderPane) rather than defaulting Accent = Default like denim_fw/
    # playground did (no distinct accent-hover existed there; here one actually does).
    # Footer's own link hover also uses schemeA_l, consistent with Link Default.
    #
    # Button/Tag: this theme's `--pbutton_darkBG_style`/`--sbutton_darkBG_style`/
    # `--tag_darkBG_style` mixins are literal aliases of their `_lightBG_style`
    # counterparts (no divergence authored for dark backgrounds at all -- same
    # "no genuine darkBG style" situation as luxurygold/playground/oasis). Reusing
    # them verbatim here would reproduce TWO of the exact bugs already fixed in
    # earlier themes:
    #   1. Primary's hover fill is literally `var(--color_dark)` == this scheme's OWN
    #      bg color (#171717) -- invisible on hover, the oasis "brand/bg-on-itself"
    #      collision, just with neutral-boldest instead of a brand hue. Flipped hover
    #      to solid white fill + dark text instead (default fill/text unaffected --
    #      brand red on this bg doesn't collide).
    #   2. Tag's default style is literally `color: var(--color_dark); border: 1px
    #      solid var(--color_dark);` -- dark-on-dark, invisible on this bg. The exact
    #      denim_fw black-on-black Tag bug. Fixed the same way: transparent bg,
    #      neutral-subtlest border+text by default, brand border+text on hover.
    # Secondary/Ghost have no distinct v3 mixin either (same alias situation) --
    # synthesized as an outline of Primary per the denim_fw/luxurygold precedent
    # (transparent fill, white border+text by default; hover flips to solid brand --
    # this hover does NOT collide with the bg, only Primary's did, so no flip needed
    # there).
    "x_supercar": {
        "bgColor": "var(--color-neutral-boldest)",
        "textColor": "var(--color-neutral-subtlest)",
        "textSubtleColor": "var(--color-neutral-subtlest)",
        "titleTextColor": "var(--color-neutral-subtlest)",
        "captionTextColor": "var(--color-neutral-subtlest)",
        "descriptionTextColor": "var(--color-neutral-subtlest)",
        "linkDefaultColor": "var(--color-neutral-subtlest)",
        "linkDefaultHoverColor": "var(--color-brand-subtle)",
        # linkAccent (2026-07-21, refined): pale red default, white on hover
        # -- not a plain white-mirrors-Default like the first draft assumed,
        # and not brand-subtle hover either (an intermediate correction,
        # since superseded) -- hover goes all the way to white so Accent's
        # hover reads as the brightest state, mirroring Default's own
        # default/hover relationship (dark→bright) but inverted for this
        # scheme's dark bg.
        "linkAccentColor": "var(--color-brand-subtlest)",
        "linkAccentHoverColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryFillColor": "var(--color-brand)",
        "buttonPrimaryBorderColor": "transparent",
        "buttonPrimaryTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryBoxShadow": "none",
        "buttonPrimaryBoxShadowColor": "transparent",
        "buttonPrimaryHoverFillColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverBorderColor": "transparent",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-boldest)",
        "buttonPrimaryHoverBoxShadow": "none",
        "buttonPrimaryHoverBoxShadowColor": "transparent",
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryBorderColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryTextColor": "var(--color-neutral-subtlest)",
        # Secondary hover (2026-07-21, live-demo correction): stays an outline
        # (fill transparent throughout, not a solid-brand flip) -- only
        # border+text shift to brand-subtle (light red) on hover.
        "buttonSecondaryHoverFillColor": "transparent",
        "buttonSecondaryHoverBorderColor": "var(--color-brand-subtle)",
        "buttonSecondaryHoverTextColor": "var(--color-brand-subtle)",
        "buttonGhostBorderColor": "var(--color-neutral-subtlest)",
        "buttonGhostTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverFillColor": "var(--color-brand)",
        "buttonGhostHoverBorderColor": "transparent",
        "buttonGhostHoverTextColor": "var(--color-neutral-subtlest)",
        "tagDefaultBgColor": "transparent",
        "tagDefaultBorderColor": "var(--color-neutral-subtlest)",
        "tagDefaultTextColor": "var(--color-neutral-subtlest)",
        # Tag hover (2026-07-21, live-demo correction): brand-subtle (light
        # red), not full brand -- same intensity as Secondary's hover above.
        "tagDefaultHoverBgColor": "transparent",
        "tagDefaultHoverBorderColor": "var(--color-brand-subtle)",
        "tagDefaultHoverTextColor": "var(--color-brand-subtle)",
        "tagAccentBgColor": "transparent",
        "tagAccentBorderColor": "var(--color-neutral-subtlest)",
        "tagAccentTextColor": "var(--color-neutral-subtlest)",
        "tagAccentHoverBgColor": "transparent",
        "tagAccentHoverBorderColor": "var(--color-brand-subtle)",
        "tagAccentHoverTextColor": "var(--color-brand-subtle)"
    },
    # x_bluehorizon (drafted 2026-07-21, NOT yet live-demo QA'd): this is the
    # theme the Header/Footer inverse-scheme gap was ORIGINALLY found on (Session
    # 20/22) -- only the FOOTER needs an inverse entry. Header's `.headerPane`/
    # `.subHeaderPane &.darkMode` CSS exists but v3's own demo has no `isDarkMode`
    # key on header at all (unset) AND the header's non-dark default bg
    # (`var(--color_schemeA_l)`, pale blue `#f8fbfd`) is already a light, correct
    # main-scheme look -- so unlike playground/supercar, no `_FORCE_HEADER_
    # INVERSE` is needed; standard conversion already renders the header
    # correctly as `.color-scheme-main`. Footer's `.footerLayout &.darkMode`
    # (isDarkMode:True in the demo) resolves to bg=`var(--color_schemeA)` (brand
    # blue #6096ba), text=`var(--color_light)` (white) -- both zones would need
    # `.color-scheme-inverse` if header ever needed it too, but since it doesn't,
    # this is footer-only in practice (still built as the normal `_THEME_INVERSE`
    # entry -- v4 has no "footer-only" scheme concept, header just never gets
    # tagged with it here).
    #
    # IMPORTANT: this theme's `_darkBG_style` mixin family (title/subtitle/
    # description/button/tag) is authored around `--background_darkBG_style`'s
    # bg (`schemeA_l`, the PALE blue used for main-2), not the footer's genuinely
    # saturated inverse bg (`schemeA`) -- reusing them here would be wrong twice
    # over: (a) the "wrong bg" lesson from every prior theme, AND (b) several of
    # them literally collide with THIS bg specifically (`subtitle`/`description`
    # both `color: var(--color_schemeA)` == the inverse bg color itself, and
    # `pbutton`/`sbutton` default+hover both cycle through `var(--color_schemeA)`
    # too -- a button that would be invisible in BOTH states, not just on hover
    # like every collision seen so far). Bg/text/title/link are grounded straight
    # from the footer's own literal `&.darkMode` block instead (title/siteTitle
    # explicitly `color: var(--color_light)`; link has no hover color change at
    # all in the source CSS, just an underline-grow animation v4 doesn't have --
    # kept the same white throughout, no flip).
    #
    # Button Primary IS genuinely grounded, just not through the aliased pbutton/
    # sbutton mixins: `--joinButton_darkBG_style` is a real, hand-authored
    # dark-bg button style (unlike every other mixin here, NOT an alias) --
    # white outline default, solid white fill + brand text on hover. Matches the
    # "flip" convention already established elsewhere by coincidence, but here
    # it's directly CSS-confirmed, not inferred. Secondary/Ghost/Tag have zero
    # per-theme signal (aliased or entirely undefined, falling through to
    # x_main's generic base, which itself gives no real color) -- synthesized:
    # white outline by default (matches Primary), hover shifts to brand-alt
    # (schemeB, cream `#fffbf2`) + dark navy text instead of Primary's white-fill
    # hover, so they read as a visually distinct family within this one scheme.
    "x_bluehorizon": {
        "bgColor": "var(--color-brand)",
        "textColor": "var(--color-neutral-subtlest)",
        "textSubtleColor": "var(--color-neutral-subtlest)",
        "titleTextColor": "var(--color-neutral-subtlest)",
        "captionTextColor": "var(--color-neutral-subtlest)",
        "descriptionTextColor": "var(--color-neutral-subtlest)",
        "linkDefaultColor": "var(--color-neutral-subtlest)",
        "linkDefaultHoverColor": "var(--color-neutral-subtlest)",
        "linkAccentColor": "var(--color-neutral-subtlest)",
        "linkAccentHoverColor": "var(--color-neutral-subtlest)",
        # Primary (2026-07-21, live-demo QA confirmed default state unchanged,
        # hover corrected): outline default was already right (transparent
        # fill, white border+text); hover changed from solid-white-fill/brand-
        # text to brand-subtlest-fill (pale blue #f8fbfd)/neutral-boldest-text
        # (dark navy) instead.
        "buttonPrimaryFillColor": "transparent",
        "buttonPrimaryBorderColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryBoxShadow": "none",
        "buttonPrimaryBoxShadowColor": "transparent",
        "buttonPrimaryHoverFillColor": "var(--color-brand-subtlest)",
        "buttonPrimaryHoverBorderColor": "var(--color-brand-subtlest)",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-boldest)",
        "buttonPrimaryHoverBoxShadow": "none",
        "buttonPrimaryHoverBoxShadowColor": "transparent",
        # Secondary (2026-07-21, live-demo correction): solid white fill +
        # brand text (was an outline like Primary, transparent/white/white);
        # hover now matches Primary's hover exactly (was brand-alt cream).
        "buttonSecondaryFillColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryBorderColor": "transparent",
        "buttonSecondaryTextColor": "var(--color-brand)",
        "buttonSecondaryHoverFillColor": "var(--color-brand-subtlest)",
        "buttonSecondaryHoverBorderColor": "var(--color-brand-subtlest)",
        "buttonSecondaryHoverTextColor": "var(--color-neutral-boldest)",
        # Ghost (2026-07-21, live-demo correction): text unchanged (white);
        # hover now matches Primary's hover too (was brand-alt cream).
        "buttonGhostBorderColor": "var(--color-neutral-subtlest)",
        "buttonGhostTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverFillColor": "var(--color-brand-subtlest)",
        "buttonGhostHoverBorderColor": "var(--color-brand-subtlest)",
        "buttonGhostHoverTextColor": "var(--color-neutral-boldest)",
        # Tag (2026-07-21, live-demo correction): border changed from white to
        # brand-subtlest (light blue), fill goes solid brand-subtlest on hover
        # (was an outline hover in brand-alt cream).
        "tagDefaultBgColor": "transparent",
        "tagDefaultBorderColor": "var(--color-brand-subtlest)",
        "tagDefaultTextColor": "var(--color-neutral-subtlest)",
        "tagDefaultHoverBgColor": "var(--color-brand-subtlest)",
        "tagDefaultHoverBorderColor": "var(--color-brand-subtlest)",
        "tagDefaultHoverTextColor": "var(--color-neutral-boldest)",
        "tagAccentBgColor": "transparent",
        "tagAccentBorderColor": "var(--color-brand-subtlest)",
        "tagAccentTextColor": "var(--color-neutral-subtlest)",
        "tagAccentHoverBgColor": "var(--color-brand-subtlest)",
        "tagAccentHoverBorderColor": "var(--color-brand-subtlest)",
        "tagAccentHoverTextColor": "var(--color-neutral-boldest)"
    },
    # x_swift (2026-07-21, live-demo QA'd): the PRIMARY inverse slot, for the
    # header -- removed once, then restored at the user's request (see
    # CSS-QUIRKS.md's "x_swift" entry for the back-and-forth). Kept separate
    # from `_THEME_INVERSE2` (footer, teal) since header's own bg is
    # genuinely different (dark gray, grounded from `.headerPane.darkMode {
    # background-color: var(--color_dark); }`). Button/Link are IDENTICAL in
    # shape to inverse-2's (same rules, just resolving against this scheme's
    # own bg) -- hover text for Primary/Secondary/Ghost is explicitly
    # "whatever this scheme's own bg color is" (user's own words), i.e.
    # neutral-boldest here vs brand-alt in inverse-2. Tag is NOT shared with
    # inverse-2 -- distinct literal values given, confirmed exact matches for
    # existing computed anchors (neutral-bold `#6e7271`, neutral-subtlest
    # `#f6f7eb`, brand-alt-bold `#017d92`, brand-bold `#9f2727`).
    "x_swift": {
        "bgColor": "var(--color-neutral-boldest)",
        "textColor": "var(--color-neutral-subtlest)",
        "textSubtleColor": "var(--color-neutral-subtlest)",
        "titleTextColor": "var(--color-neutral-subtlest)",
        "captionTextColor": "var(--color-neutral-subtlest)",
        "descriptionTextColor": "var(--color-neutral-subtlest)",
        "linkDefaultColor": "var(--color-neutral-subtlest)",
        "linkDefaultHoverColor": "var(--color-neutral-subtlest)",
        "linkAccentColor": "var(--color-neutral-subtlest)",
        "linkAccentHoverColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryFillColor": "var(--color-brand)",
        "buttonPrimaryBorderColor": "transparent",
        "buttonPrimaryTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryBoxShadow": "none",
        "buttonPrimaryBoxShadowColor": "transparent",
        "buttonPrimaryHoverFillColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverBorderColor": "transparent",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-boldest)",
        "buttonPrimaryHoverBoxShadow": "none",
        "buttonPrimaryHoverBoxShadowColor": "transparent",
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryBorderColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverFillColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverBorderColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverTextColor": "var(--color-neutral-boldest)",
        "buttonGhostBorderColor": "transparent",
        "buttonGhostTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverFillColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverBorderColor": "transparent",
        "buttonGhostHoverTextColor": "var(--color-neutral-boldest)",
        "tagDefaultBgColor": "var(--color-neutral-bold)",
        "tagDefaultBorderColor": "transparent",
        "tagDefaultTextColor": "var(--color-neutral-subtlest)",
        "tagDefaultHoverBgColor": "var(--color-brand-alt-bold)",
        "tagDefaultHoverBorderColor": "transparent",
        "tagDefaultHoverTextColor": "var(--color-neutral-subtlest)",
        "tagAccentBgColor": "var(--color-brand-bold)",
        "tagAccentBorderColor": "transparent",
        "tagAccentTextColor": "var(--color-neutral-subtlest)",
        "tagAccentHoverBgColor": "var(--color-brand-bold)",
        "tagAccentHoverBorderColor": "transparent",
        "tagAccentHoverTextColor": "var(--color-neutral-subtlest)"
    },
    # x_elite (2026-08-04): the misclassified main-2 content section, added to
    # `_THEME_SCHEME2_MISCLASSIFIED_DARK` above. Header/Footer isDarkMode are
    # both False in the real v3 demo (checked directly), so this is body
    # content only -- no Header/Footer inverse work needed for this theme yet
    # (the subheader IS unconditionally colored regardless of isDarkMode, but
    # that's handled as a demo-only force in tools/regen_demos.py, see
    # `_FORCE_SUBHEADER_INVERSE` there -- it reuses this exact block, its own
    # colors happen to match bg/text below exactly).
    # bg/text initially CSS-grounded (bg=var(--color_schemeB)=BrandAlt
    # `#4c403b`, text=var(--color_light)=neutral-subtlest `#faf8f7`, both from
    # `--background_darkBG_style`) and confirmed correct by live-demo QA
    # 2026-08-04 -- unchanged from the first draft. Buttons/tag/link were
    # WRONG in the first CSS-only draft and corrected this round from the
    # user's own devtools read of the live demo (exact hex, not derived from
    # the palette CSS, since the CSS-literal guesses -- e.g. the duplicate
    # `--sbutton_darkBG_style` mixin, opacity-based hovers -- didn't match).
    "x_elite": {
        "bgColor": "var(--color-brand-alt)",
        "textColor": "var(--color-neutral-subtlest)",
        "textSubtleColor": "var(--color-neutral-subtlest)",
        "titleTextColor": "var(--color-neutral-subtlest)",
        "captionTextColor": "var(--color-neutral-subtlest)",
        "descriptionTextColor": "var(--color-neutral-subtlest)",
        "linkDefaultColor": "var(--color-neutral-subtle)",
        "linkDefaultHoverColor": "var(--color-neutral-subtle)",
        "linkAccentColor": "var(--color-brand)",
        "linkAccentHoverColor": "var(--color-brand)",
        # Primary: solid white fill/brand-alt text; hover flips to outline
        # (transparent fill, white border+text) -- confirmed correct as-is.
        "buttonPrimaryFillColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryBorderColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryTextColor": "var(--color-brand-alt)",
        "buttonPrimaryHoverFillColor": "transparent",
        "buttonPrimaryHoverBorderColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-subtlest)",
        # Secondary: white border+text default; hover -> transparent fill,
        # border+text flip to brand (tan) -- corrected 2026-08-04 (was
        # guessed as a solid-fill hover from the CSS's opacity overlay).
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryBorderColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverFillColor": "transparent",
        "buttonSecondaryHoverBorderColor": "var(--color-brand)",
        "buttonSecondaryHoverTextColor": "var(--color-brand)",
        "buttonGhostTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverFillColor": "transparent",
        "buttonGhostHoverBorderColor": "transparent",
        "buttonGhostHoverTextColor": "var(--color-neutral-subtlest)",
        # Tag: transparent bg, pale-white border (opacity approximation,
        # unconfirmed), white text; hover -> same as main's hover (brand-alt
        # border, brand fill, white text) -- corrected 2026-08-04, was
        # guessed backwards (border/text swapped, hover fill missing brand).
        "tagDefaultBgColor": "transparent",
        "tagDefaultBorderColor": "#faf8f780",
        "tagDefaultTextColor": "var(--color-neutral-subtlest)",
        "tagDefaultHoverBgColor": "var(--color-brand)",
        "tagDefaultHoverBorderColor": "var(--color-brand-alt)",
        "tagDefaultHoverTextColor": "var(--color-neutral-subtlest)",
        # Accent tag/link: no CSS grounding at all in this theme (no distinct
        # accent-tag mixin) -- mirrors Default tag verbatim as a placeholder,
        # not user-confirmed.
        "tagAccentBgColor": "transparent",
        "tagAccentBorderColor": "#faf8f780",
        "tagAccentTextColor": "var(--color-neutral-subtlest)",
        "tagAccentHoverBgColor": "var(--color-brand)",
        "tagAccentHoverBorderColor": "var(--color-brand-alt)",
        "tagAccentHoverTextColor": "var(--color-neutral-subtlest)",
    },
    # x_mixednuts (2026-08-06, DRAFT -- NOT yet live-demo QA'd): the
    # misclassified main-2 content section, added to
    # `_THEME_SCHEME2_MISCLASSIFIED_DARK` above. Header/Footer/subheader all
    # have proper `.darkMode.X` CSS gates already (the normal pattern) and
    # none is `isDarkMode:true` in the real v3 demo -- out of scope here.
    # bg grounded from `--background_darkBG_style`:
    # `color(var(--color_dark) shade(30%))` -- Stylus's shade(), mix-with-
    # black by N% -- computed `#362215` (color_dark `#4d311e` x 0.7 per
    # channel). No v4 anchor matches this exactly (it's a step darker than
    # the computed neutral-boldest `#4d311e`), so kept as a literal hex, same
    # treatment as other unmappable colors this session. Live-demo confirmed
    # 2026-07-17 (see CSS-QUIRKS.md): white text on this bg -- genuine
    # inverse. text=`var(--color_light100)` (undefined in this theme's own
    # sparse palette, presumably an alias of `--color_light`/white from a
    # shared base stylesheet, matching the live-demo confirmation) -> white
    # -> neutral-subtlest (exact anchor match, `#fff`). No distinct title/
    # subtitle/caption/description mixins at all -- all fall back to the same
    # white. Primary button IS grounded (`--button_darkBG_style`, palette
    # CSS): solid white fill, dark text (neutral-boldest); hover flips to
    # solid brand (green) fill, white text. Secondary is ALSO grounded --
    # found on a second CSS pass (`.darkMode .btn_secondary`, theme CSS, not
    # the palette): default transparent fill + white border/text; hover
    # flips to solid WHITE fill + dark text (neutral-boldest) -- notably NOT
    # a brand-color hover like Primary, an asymmetry confirmed directly in
    # CSS, not guessed. Tag is grounded too (`.btnTag`, theme CSS) -- this
    # one rule is UNCONDITIONAL (no `.darkMode` variant exists, applies as-is
    # regardless of scheme): transparent fill, brand border/text; hover
    # solid brand fill + white text. Ghost/Link have ZERO CSS grounding at
    # all (no `.btn_tertiary`/ghost class, no link-in-dark-content rule).
    # 2026-08-06: user corrected Secondary/Ghost/Link Default/Tag directly
    # (Primary and Link Accent were already right, kept as-is) -- Secondary
    # hover now matches Primary's hover (green fill/white text, not the
    # CSS-literal white-fill/dark-text read); Ghost hover fill is
    # neutral-bold with text UNCHANGED (not brand); Link Default has NO
    # hover color change at all (relies on v4-base's own
    # `linkHoverTextDecoration:underline` default for the visual cue); Tag
    # flipped to a white border/text default (was brand-green) with hover
    # bg neutral-subtle (was brand).
    "x_mixednuts": {
        "bgColor": "#362215",
        "textColor": "var(--color-neutral-subtlest)",
        "textSubtleColor": "var(--color-neutral-subtlest)",
        "titleTextColor": "var(--color-neutral-subtlest)",
        "captionTextColor": "var(--color-neutral-subtlest)",
        "descriptionTextColor": "var(--color-neutral-subtlest)",
        "linkDefaultColor": "var(--color-neutral-subtlest)",
        "linkDefaultHoverColor": "var(--color-neutral-subtlest)",
        "linkAccentColor": "var(--color-brand)",
        "linkAccentHoverColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryFillColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryBorderColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryTextColor": "var(--color-neutral-boldest)",
        "buttonPrimaryHoverFillColor": "var(--color-brand)",
        "buttonPrimaryHoverBorderColor": "var(--color-brand)",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryBorderColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverFillColor": "var(--color-brand)",
        "buttonSecondaryHoverBorderColor": "var(--color-brand)",
        "buttonSecondaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverFillColor": "var(--color-neutral-bold)",
        "buttonGhostHoverBorderColor": "transparent",
        "buttonGhostHoverTextColor": "var(--color-neutral-subtlest)",
        "tagDefaultBgColor": "transparent",
        "tagDefaultBorderColor": "var(--color-neutral-subtlest)",
        "tagDefaultTextColor": "var(--color-neutral-subtlest)",
        "tagDefaultHoverBgColor": "var(--color-neutral-subtle)",
        "tagDefaultHoverBorderColor": "var(--color-neutral-subtlest)",
        # Hover text (2026-08-06, user correction): the pale hover fill needs a
        # dark text, not white -- matches this SCHEME's own bg color (the
        # literal `#362215` this inverse slot is built around, no anchor exists
        # for it -- see the bgColor comment above).
        "tagDefaultHoverTextColor": "#362215",
        # Accent (2026-08-06, user correction): border/text white -> brand-subtlest
        # (pale green) -- now deliberately different from Default, which stays
        # white. Hover border tracks the new default (unchanged-through-hover
        # convention); hover bg/text untouched from the previous round.
        "tagAccentBgColor": "transparent",
        "tagAccentBorderColor": "var(--color-brand-subtlest)",
        "tagAccentTextColor": "var(--color-brand-subtlest)",
        "tagAccentHoverBgColor": "var(--color-neutral-subtle)",
        "tagAccentHoverBorderColor": "var(--color-brand-subtlest)",
        "tagAccentHoverTextColor": "#362215",
    },
    # x_petestate (2026-08-07, DRAFT -- NOT yet live-demo QA'd): the misclassified
    # main-2 content section, added to `_THEME_SCHEME2_MISCLASSIFIED_DARK` above.
    # bg/text grounded from `--background_darkBG_style` (palette CSS): bg=
    # var(--color_dark) -> neutral-boldest `#1d1e4e` (exact anchor match), text=
    # var(--color_light100) (undefined in this theme's own palette, alias of
    # --color_light/white from the shared base stylesheet, same pattern as
    # x_mixednuts) -> neutral-subtlest. No distinct title/subtitle/caption/
    # description mixins exist -- all fall back to the same white, like mixednuts.
    # Footer (`.footer_section`, theme CSS) is UNCONDITIONAL dark with these exact
    # bg/text values, and the real v3 demo already has `isDarkMode:true` set on
    # footer -- so once this theme is in the misclassified set, footer's existing
    # isDarkMode flag already routes it to this inverse block correctly. NO
    # `_FORCE_FOOTER_INVERSE`/`_FORCE_FOOTER_MAIN2` needed (first theme in this
    # thread where the footer just works once the set membership is added).
    # `.subHeaderPane` is ALSO unconditional dark (same bg/text as here, mirrors
    # x_elite's subheader quirk) but the real v3 demo has no subheader content at
    # all (`menuListObjects` has no sub-menu bar built), so there's nothing for
    # `_FORCE_SUBHEADER_INVERSE` to act on in THIS demo -- noted for completeness,
    # not wired.
    # Primary button IS grounded (`--button_darkBG_style`, palette CSS): solid
    # white fill, dark text (border:0); hover flips to solid brand (yellow
    # `--color_schemeA`) fill, text STAYS dark (not white) per the literal CSS.
    # Secondary is ALSO grounded (`.darkMode .btn_secondary`, theme CSS) but is a
    # byte-for-byte duplicate of Primary's colors (same fill/text/hover) -- per
    # this project's standing "primary==secondary solid -> secondary becomes
    # OUTLINE of primary" convention (same call made for x_elite), drafted here as
    # an outline instead of the literal duplicate, for visual distinction.
    # Tag (`.btnTag`, theme CSS) is UNCONDITIONAL -- no `.darkMode` variant at all,
    # applies identically regardless of scheme: transparent fill, brand-alt (teal)
    # border+text; hover solid brand (yellow) fill, dark text. Kept as-is even
    # though teal-on-navy contrast is untested -- flag for live-demo QA.
    # Ghost/Link have ZERO CSS grounding at all (no ghost/tertiary class, no
    # link-in-dark-content rule) -- placeholders following this theme's own
    # "hover flips to brand" pattern from Primary/Tag, unconfirmed.
    "x_petestate": {
        "bgColor": "var(--color-neutral-boldest)",
        "textColor": "var(--color-neutral-subtlest)",
        "textSubtleColor": "var(--color-neutral-subtlest)",
        "titleTextColor": "var(--color-neutral-subtlest)",
        "captionTextColor": "var(--color-neutral-subtlest)",
        "descriptionTextColor": "var(--color-neutral-subtlest)",
        "linkDefaultColor": "var(--color-neutral-subtlest)",
        "linkDefaultHoverColor": "var(--color-neutral-subtlest)",
        "linkAccentColor": "var(--color-brand-alt)",
        "linkAccentHoverColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryFillColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryBorderColor": "transparent",
        "buttonPrimaryTextColor": "var(--color-neutral-boldest)",
        "buttonPrimaryHoverFillColor": "var(--color-brand)",
        "buttonPrimaryHoverBorderColor": "transparent",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-boldest)",
        "buttonSecondaryFillColor": "transparent",
        "buttonSecondaryBorderColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryHoverFillColor": "transparent",
        "buttonSecondaryHoverBorderColor": "var(--color-brand)",
        "buttonSecondaryHoverTextColor": "var(--color-brand)",
        "buttonGhostTextColor": "var(--color-neutral-subtlest)",
        "buttonGhostHoverFillColor": "transparent",
        "buttonGhostHoverBorderColor": "transparent",
        "buttonGhostHoverTextColor": "var(--color-brand)",
        # Tag (2026-08-07, user correction): border/text `brand-alt` (teal, full
        # strength) read too dark against the navy bg -- lightened to
        # `brand-alt-subtle`. Hover unchanged (still flips to solid brand/dark
        # text, already confirmed fine).
        "tagDefaultBgColor": "transparent",
        "tagDefaultBorderColor": "var(--color-brand-alt-subtle)",
        "tagDefaultTextColor": "var(--color-brand-alt-subtle)",
        "tagDefaultHoverBgColor": "var(--color-brand)",
        "tagDefaultHoverBorderColor": "var(--color-brand)",
        "tagDefaultHoverTextColor": "var(--color-neutral-boldest)",
        "tagAccentBgColor": "transparent",
        "tagAccentBorderColor": "var(--color-brand-alt-subtle)",
        "tagAccentTextColor": "var(--color-brand-alt-subtle)",
        "tagAccentHoverBgColor": "var(--color-brand)",
        "tagAccentHoverBorderColor": "var(--color-brand)",
        "tagAccentHoverTextColor": "var(--color-neutral-boldest)",
    },
}



def _same_as_base(key, value):
    """True if `value` for `key` matches the v4-base default. For breakpoint-object
    values, matches when every breakpoint we set equals base's same breakpoint."""
    base = _V4_BASE_ROOT_DEFAULTS.get(key)
    if base is None:
        return False
    if isinstance(value, dict) and isinstance(base, dict):
        return all(base.get(bp) == v for bp, v in value.items())
    return base == value


def _seed_base(root, key, value):
    """Write a v3 base-constant into root only if it is absent AND not already the
    v4-base default."""
    if key not in root and not _same_as_base(key, value):
        root[key] = value

_WHITE = (255, 255, 255)
_BLACK = (0, 0, 0)


def _hex(s):
    """Parse '#rgb' / '#rrggbb' → (r, g, b); None on bad input."""
    if not isinstance(s, str):
        return None
    s = s.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        return None
    try:
        return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def _to_hex(rgb):
    return "#" + "".join("%02x" % max(0, min(255, int(round(c)))) for c in rgb)


def _norm_hex(s):
    """Normalize a hex color to 6-digit lowercase (e.g. '#000' → '#000000').
    Returns the input unchanged (lowercased str) if it isn't a parseable hex."""
    rgb = _hex(s)
    if rgb is None:
        return s.lower() if isinstance(s, str) else s
    return _to_hex(rgb)


def _mix(hexc, target, pct):
    """Mix `hexc` toward `target` rgb by `pct` (0..1). White=tint, black=shade.
    Returns '#rrggbb' or None if `hexc` is unparseable."""
    rgb = _hex(hexc)
    if rgb is None:
        return None
    return _to_hex(tuple(rgb[i] + (target[i] - rgb[i]) * pct for i in range(3)))


def _interp(a, b, t):
    """Linear interpolate between two hex colors at t (0..1). None if either bad."""
    ra, rb = _hex(a), _hex(b)
    if ra is None or rb is None:
        return None
    return _to_hex(tuple(ra[i] + (rb[i] - ra[i]) * t for i in range(3)))


def _fill_color_scale(root):
    """Fill the missing v4 5-step color scales (Subtlest→Boldest) for brand,
    brandAlt and neutral from the anchor colors that currentColors provided.
    Approximate ('close enough'); never overwrites a key already present."""
    def setk(k, v):
        if v and k not in root:
            root[k] = v

    # Brand: have base / Subtle / Bold → extend the two ends.
    b, bs, bb = root.get("colorBrand"), root.get("colorBrandSubtle"), root.get("colorBrandBold")
    if bs:
        setk("colorBrandSubtlest", _mix(bs, _WHITE, 0.5))
    elif b:
        setk("colorBrandSubtle", _mix(b, _WHITE, 0.4))
        setk("colorBrandSubtlest", _mix(b, _WHITE, 0.8))
    if bb:
        setk("colorBrandBoldest", _mix(bb, _BLACK, 0.4))
    elif b:
        setk("colorBrandBold", _mix(b, _BLACK, 0.25))
        setk("colorBrandBoldest", _mix(b, _BLACK, 0.5))

    # BrandAlt: only the base anchor → compute all four steps.
    ba = root.get("colorBrandAlt")
    if ba:
        setk("colorBrandAltSubtle", _mix(ba, _WHITE, 0.4))
        setk("colorBrandAltSubtlest", _mix(ba, _WHITE, 0.8))
        setk("colorBrandAltBold", _mix(ba, _BLACK, 0.25))
        setk("colorBrandAltBoldest", _mix(ba, _BLACK, 0.5))

    # Neutral: have Subtlest + Boldest → interpolate the three middles.
    ns, nb = root.get("colorNeutralSubtlest"), root.get("colorNeutralBoldest")
    if ns and nb:
        setk("colorNeutralSubtle", _interp(ns, nb, 0.12))
        setk("colorNeutral", _interp(ns, nb, 0.30))
        setk("colorNeutralBold", _interp(ns, nb, 0.72))


def _resolve_system_font(name):
    """Map a v3 font name to its canonical v4 system-font name, or return None
    if it is not a system font (i.e. a Google/unknown font). Tolerates case
    differences and minor misspellings (e.g. "Saraban" → "Sarabun")."""
    if not isinstance(name, str) or not name.strip():
        return None
    key = name.strip().lower()
    if key in _SYSTEM_FONTS_LOWER:
        return _SYSTEM_FONTS_LOWER[key]
    close = difflib.get_close_matches(key, list(_SYSTEM_FONTS_LOWER), n=1, cutoff=0.8)
    if not close:
        return None
    ck = close[0]
    # Reject a fuzzy "match" that is really a DISTINCT family one is a substring
    # of (e.g. "ibm plex sans" vs the list's "ibm plex sans thai") — that's a
    # different font, not a typo, and must stay a Google font.
    if key != ck and (key in ck or ck in key):
        return None
    return _SYSTEM_FONTS_LOWER[ck]


# CSS generic font families — valid fallbacks, kept as-is (lowercased) in the
# stack but never registered in fontManifest (they aren't Google fonts).
_GENERIC_FAMILIES = {
    "serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui",
    "ui-serif", "ui-sans-serif", "ui-monospace", "ui-rounded", "math", "emoji",
}


def _resolve_font_family(names, warnings, path, *, keep_google=False):
    """Resolve a v3 font-name list to canonical system fonts. Returns
    `(kept, google)`.

    A non-system, non-generic name is a Google/unknown font:
      - keep_google=False (website default): it is DROPPED + warned, `google` is [].
      - keep_google=True  (theme): it is KEPT in the stack with its ORIGINAL case
        and collected into `google` for fontManifest; a warning notes it was added.
        Original case matters — the Google Fonts API is case-sensitive
        ("IBM Plex Serif" loads, "ibm plex serif" 404s)."""
    kept, google, dropped = [], [], []
    seen = set()  # case-insensitive dedup for the kept stack
    for n in names or []:
        canon = _resolve_system_font(n)
        if canon is not None:
            if canon.lower() not in seen:
                kept.append(canon); seen.add(canon.lower())
            continue
        if not isinstance(n, str) or not n.strip():
            continue
        name = n.strip()
        if name.lower() in _GENERIC_FAMILIES:
            if name.lower() not in seen:
                kept.append(name.lower()); seen.add(name.lower())
        elif keep_google:
            if name.lower() not in seen:
                kept.append(name); seen.add(name.lower())   # keep original case
            if not any(g.lower() == name.lower() for g in google):
                google.append(name)
        else:
            dropped.append(name)
    if dropped and warnings is not None:
        warnings.append({
            "path": path, "kind": "warn",
            "msg": "Google font(s) dropped (not in system list — add manually in v4): "
                   + ", ".join(dropped),
        })
    if google and warnings is not None:
        warnings.append({
            "path": path, "kind": "warn",
            "msg": "Google font(s) added to fontManifest (verify they exist in v4): "
                   + ", ".join(google),
        })
    return kept, google


def _build_theme_root(colors, fonts, theme_id, *, include_colors=True,
                      include_fonts=True, generate_color_scale=True, warnings=None,
                      keep_google=False, manifest=None):
    """Build the v4 style[":root"] override dict from v3 theme inputs.

    Shared by convert_global (website JSON) and convert_theme (theme JSON) so both
    produce identical color/font/typography output. `colors` is the 6-anchor list
    (currentColors / themes.js colors), `fonts` the {heading,text} stacks,
    `theme_id` the v3 theme id used to look up per-theme typography overrides.
    Returns the ordered root dict (color keys sorted first, then fonts/typography);
    only values that differ from v4-base are kept (skip-if-equals-base).

    `keep_google` (theme only) keeps Google fonts in the family stack instead of
    dropping them; when a `manifest` dict is passed, the kept Google fonts are
    recorded as `manifest["google"]` (for theme.info.fontManifest)."""
    root: dict = {}
    if include_colors and isinstance(colors, list):
        for i, key in enumerate(_THEME_COLOR_KEYS):
            if i < len(colors) and isinstance(colors[i], str) and colors[i]:
                root[key] = colors[i].lower()
        if any(k.startswith("color") for k in root) and generate_color_scale:
            # Fill the v4 5-step scales from the anchors (does not overwrite an
            # anchor the theme provided). Status colors are left to v4.
            _fill_color_scale(root)

    if include_fonts and isinstance(fonts, dict):
        # Skip a font-family key entirely when it resolves to an empty list (e.g.
        # every name was a dropped Google font, or the theme inherits Base fonts).
        heading, gh = _resolve_font_family(fonts.get("heading"), warnings,
                                           "$.currentFonts.heading", keep_google=keep_google)
        if heading:
            root["typoHeadingFontFamily"] = heading
        paragraph, gp = _resolve_font_family(fonts.get("text"), warnings,
                                             "$.currentFonts.text", keep_google=keep_google)
        if paragraph:
            root["typoParagraphFontFamily"] = paragraph
        if manifest is not None:
            google = []
            for g in gh + gp:
                if g not in google:
                    google.append(g)
            if google:
                manifest["google"] = google
        # v3 base typography metrics — only when they differ from the v4-base
        # default (else redundant). All three currently equal base → omitted.
        for k, v in _V3_BASE_TYPOGRAPHY.items():
            _seed_base(root, k, v)
        # Per-theme text-base overrides (font-size/weight/line-height), keyed by
        # theme id — emitted only where they differ from v4-base.
        theme_typo = _THEME_TYPOGRAPHY.get(theme_id)
        if theme_typo:
            for k, v in theme_typo.items():
                _seed_base(root, k, v)

    if root:
        # Color keys first, sorted alphabetically; then the rest (fonts/typography)
        # in their existing order.
        color_keys = sorted(k for k in root if k.startswith("color"))
        other_keys = [k for k in root if not k.startswith("color")]
        root = {k: root[k] for k in color_keys + other_keys}
    return root


def _build_free_zone(components: dict) -> dict:
    """Build the free_zone node from `components.ContactWidget`."""
    children: list = []
    cw = components.get("ContactWidget")
    if isinstance(cw, dict) and cw.get("enableContactWidget"):
        children.append(make_node("widget", "WidgetChat", None, {}))
    return make_node("page", "free", "Free", {}, children)


def convert_global(site_json: dict, warnings: list = None, *,
                   include_components: bool = True,
                   include_colors: bool = True,
                   include_fonts: bool = True,
                   generate_color_scale: bool = True) -> dict:
    """Convert v3 site-level `components.*` config to v4 global triplet.

    Returns {"info": {...}, "style": {...}, "free_zone": {...}}.
    Always emits a free_zone wrapper (children may be empty).

    When the v3 input carries theme config (`currentColors` / `currentFonts`),
    they are mapped to `style[":root"]` (brand colors + font families) and
    `info.fontManifest`. Non-system fonts are dropped and reported via the
    optional `warnings` list (see _resolve_font_family).

    The `include_*` flags select which parts to emit (the browser tool exposes
    these as output toggles; all default True so CLI behavior is unchanged):
      - include_components: `components.*` → info/style selectors + free_zone
      - include_colors:     `currentColors` → :root brand colors, plus a computed
                            5-step color scale (status colors left to v4 default)
      - include_fonts:      `currentFonts`  → :root font families + fontManifest,
                            plus per-theme text-base typography (by `currentTheme`,
                            only where it differs from the v4-base default)
      - generate_color_scale: when True, fill the missing v4 5-step color scale from
                            the currentColors anchors; when False, emit only the
                            anchors. (Requires include_colors.)
    """
    components = (site_json.get("components") or {}) if isinstance(site_json, dict) else {}

    info: dict = {}
    style: dict = {}

    if include_components:
        # ── ProductBox → style[".element-card-product"] + info.Element.CardProduct.cardConfig ──
        pb = components.get("ProductBox")
        if isinstance(pb, dict):
            ecp_style: dict = {}
            if "isThumbnailHeight" in pb:
                ecp_style["cardProductThumbnailRatio"] = "3 / 4" if pb["isThumbnailHeight"] else "1 / 1"
            image_type = pb.get("imageType")
            if image_type in _IMAGE_TYPE_TO_OBJECT_FIT:
                ecp_style["cardProductThumbnailObjectFit"] = _IMAGE_TYPE_TO_OBJECT_FIT[image_type]
            font_color = (pb.get("pTitleStyle") or {}).get("fontColor")
            if isinstance(font_color, str) and font_color:
                ecp_style["cardProductNameColor"] = font_color.lower()
            if ecp_style:
                style[".element-card-product"] = ecp_style

            card_config: dict = {}
            if "isUseHoverImage" in pb:
                card_config["isEnableImageTransitionOverlay"] = bool(pb["isUseHoverImage"])
            if pb.get("isShowCode") is True:
                card_config["isShowCode"] = True
            if card_config:
                info.setdefault("Element", {}).setdefault("CardProduct", {})["cardConfig"] = card_config

        # ── ProductList → style[".widget-product-list"] + info.Widget.ProductList ──
        pl = components.get("ProductList")
        if isinstance(pl, dict):
            box_num = pl.get("productBoxNumber")
            if isinstance(box_num, int):
                style[".widget-product-list"] = {"layoutGridCols": {"xs": box_num}}
            limit = pl.get("limit")
            if isinstance(limit, int):
                info.setdefault("Widget", {}).setdefault("ProductList", {})["productNumber"] = limit

        # ── ContactWidget → style[".widget-chat"] (free_zone via _build_free_zone) ──
        cw = components.get("ContactWidget")
        if isinstance(cw, dict):
            chat_btn = cw.get("iconChatButtonStyle") or {}
            if isinstance(chat_btn, dict):
                wc_style: dict = {}
                bg = chat_btn.get("bgColor")
                if isinstance(bg, str) and bg:
                    wc_style["bgColor"] = bg.lower()
                fc = chat_btn.get("fontColor")
                if isinstance(fc, str) and fc:
                    wc_style["textColor"] = fc.lower()
                if wc_style:
                    style[".widget-chat"] = wc_style

    # ── Theme config → style[":root"] (colors + fonts) + info.fontManifest ──
    # Shared with convert_theme via _build_theme_root (same color/font/typography
    # rules); convert_global additionally emits info.fontManifest.
    cfg = site_json if isinstance(site_json, dict) else {}
    root = _build_theme_root(
        cfg.get("currentColors"), cfg.get("currentFonts"), cfg.get("currentTheme"),
        include_colors=include_colors, include_fonts=include_fonts,
        generate_color_scale=generate_color_scale, warnings=warnings)
    if include_fonts and isinstance(cfg.get("currentFonts"), dict):
        # Google fonts are dropped (see _resolve_font_family), so the manifest is
        # always empty; the key is still emitted to match the v4 shape.
        info["fontManifest"] = {}
    if root:
        # :root always sits at the top of style, above any component selectors.
        style = {":root": root, **style}

    free_zone = _build_free_zone(components if include_components else {})

    return {"info": info, "style": style, "free_zone": free_zone}


# Themes whose main-2 is NOT derived from v3 darkMode CSS at all -- a plain "same as
# main, but a different bg" alt scheme, built by copying the theme's OWN already-
# resolved `.color-scheme-main` (_build_main(), including its `_THEME_MAIN_OVERRIDES`)
# verbatim and patching only the given keys. x_elite (2026-08-06, user-requested):
# `.footerLayout` CSS is unconditionally `background-color: #ffffff` (pure white),
# genuinely distinct from the theme's main bg (`var(--color-neutral-subtlest)`,
# `#faf8f7` off-white). `var(--color-white)` is a fixed v4-base constant (`#ffffff`),
# not a per-theme anchor. This bypasses `_theme_scheme2_overrides()`/
# `_THEME_MAIN2_OVERRIDES` entirely -- those are for the CSS-darkMode-derived path,
# not applicable here (x_elite is in `_THEME_SCHEME2_MISCLASSIFIED_DARK`, so that path
# already returns nothing for it).
# Button/link colors (2026-08-06, user-supplied, not CSS-grounded -- white bg needs
# darker text/button contrast than main's own brand-color buttons): Primary solid
# brand-boldest fill/border + white text, hover flips to brand-bold; Secondary
# outline (transparent fill, inherited from main) brand-boldest border/text, hover
# brand-bold; Ghost text brand-boldest, hover brand-bold; Link Default brand-boldest,
# hover brand; Link Accent brand-bold, hover brand. Tag not covered -- inherits
# main's values unchanged (not requested).
_THEME_MAIN2_FROM_MAIN = {
    "x_elite": {
        "bgColor": "var(--color-white)",
        "buttonPrimaryFillColor": "var(--color-brand-boldest)",
        "buttonPrimaryBorderColor": "var(--color-brand-boldest)",
        "buttonPrimaryTextColor": "var(--color-neutral-subtlest)",
        "buttonPrimaryHoverFillColor": "var(--color-brand-bold)",
        "buttonPrimaryHoverBorderColor": "var(--color-brand-bold)",
        "buttonPrimaryHoverTextColor": "var(--color-neutral-subtlest)",
        "buttonSecondaryBorderColor": "var(--color-brand-boldest)",
        "buttonSecondaryTextColor": "var(--color-brand-boldest)",
        "buttonSecondaryHoverBorderColor": "var(--color-brand-bold)",
        "buttonSecondaryHoverTextColor": "var(--color-brand-bold)",
        "buttonGhostTextColor": "var(--color-brand-boldest)",
        "buttonGhostHoverTextColor": "var(--color-brand-bold)",
        "linkAccentColor": "var(--color-brand-bold)",
        "linkAccentHoverColor": "var(--color-brand)",
        "linkDefaultColor": "var(--color-brand-boldest)",
        "linkDefaultHoverColor": "var(--color-brand)",
    },
    # x_mixednuts (2026-08-06, user-requested): `.f_singleproduct { background:
    # var(--color_schemeB); }` (unconditional, theme-x_mixednuts.partial.css) --
    # schemeB is this theme's BrandAlt anchor, resolves to `#f4edd4` (light cream),
    # an exact anchor match (no literal-hex fallback needed, unlike x_elite's white).
    # No text/link/button color overrides exist within `.f_singleproduct` itself --
    # only bg differs from main. Button/tag/link ARE customized for this theme, but
    # via `_THEME_MAIN_OVERRIDES["x_mixednuts"]` (main == main-2 verbatim per the
    # user), picked up automatically here since this dict's source is main's own
    # fully-resolved value (template + `_THEME_MAIN_OVERRIDES`) -- only `bgColor`
    # needs stating again here. Tag hover bg is the one exception (2026-08-06,
    # user correction): main's `var(--color-brand-subtlest)` (pale green) reads
    # fine against main's white bg, but "sinks"/low-contrast against main-2's own
    # cream bg (`var(--color-brand-alt)`, visually close to the pale green) --
    # main-2 gets white instead, text stays brand green from main (still reads
    # fine on white).
    "x_mixednuts": {
        "bgColor": "var(--color-brand-alt)",
        "tagDefaultHoverBgColor": "var(--color-neutral-subtlest)",
        "tagAccentHoverBgColor": "var(--color-neutral-subtlest)",
    },
    # x_petestate (2026-08-07, user-requested): `.f_category { background:
    # var(--color_schemeA_l); }` (unconditional, theme-x_petestate.partial.css)
    # -- schemeA_l is this theme's BrandSubtle anchor, exact match (`#f5f6f8`,
    # light gray). No text/link/button overrides exist within `.f_category`
    # itself -- only bg differs from main, so this picks up main's own
    # button/tag/link colors (`_THEME_MAIN_OVERRIDES["x_petestate"]`)
    # automatically, only `bgColor` needs stating here. Same-family light-gray
    # sections exist elsewhere in this theme's CSS too (`.f_about`, `.f_banner`
    # all use the same `--color_schemeA_l`) but only "1. Default Featured
    # content"/`f_category` has been forced so far -- see
    # `tools/regen_demos.py`'s `_FORCE_SECTION_PROPS_BY_IMAGE`.
    "x_petestate": {
        "bgColor": "var(--color-brand-subtle)",
    },
}


def _build_scheme2(theme_id: str) -> dict:
    """The v4 alternative color scheme `.color-scheme-main-2` for a theme, or `{}` if
    the theme has no v3 darkMode. Only themes with darkMode-derived overrides get the
    block (the full template from _scheme2_template() + those overrides); the rest
    keep only `.color-scheme-main` from Base. Values are palette refs (var(--color-*)),
    so each theme's own :root drives the actual colors. `_THEME_MAIN2_OVERRIDES` layers
    on top last -- a manual per-theme correction for cases the CSS-derived
    `_theme_scheme2_overrides()` gets wrong (e.g. a hover text color that's white with
    no hover fill behind it, reading as blended against main-2's own bg).
    `_THEME_MAIN2_FROM_MAIN` is a separate, simpler path -- see its own comment. Its
    source is the theme's FULLY resolved main (template + `_THEME_MAIN_OVERRIDES`,
    if any -- NOT `_build_main()` directly, which returns `{}` for a theme with no
    main override at all, e.g. x_mixednuts; that's a valid, common case here, not an
    error). Re-keyed from main's own key schema to main-2's (they differ -- see
    _SCHEME2_SCHEMA's docstring: `sectionBorderColor` is main-2-only, mirroring
    main's `borderColor`; main's two slider-input keys don't exist in main-2), the
    same way _scheme2_template() re-keys v4 Base's main."""
    if theme_id in _THEME_MAIN2_FROM_MAIN:
        main = {**_scheme_main_template(), **_THEME_MAIN_OVERRIDES.get(theme_id, {})}
        rekeyed = {k: (main["borderColor"] if k == "sectionBorderColor" else main[k])
                   for k in _SCHEME2_SCHEMA}
        return {**rekeyed, **_THEME_MAIN2_FROM_MAIN[theme_id]}
    override = _theme_scheme2_overrides().get(theme_id)
    if not override:
        return {}
    manual = _THEME_MAIN2_OVERRIDES.get(theme_id, {})
    return {**_scheme2_template(), **override, **manual}


def _build_inverse(theme_id: str) -> dict:
    """The v4 inverse color scheme `.color-scheme-inverse` for a theme, or `{}` if the
    theme has no per-theme inverse override. Only themes whose v3 darkMode is a
    white-text-on-colored (inverse) scheme distinct from their main-2 alt bg get the
    block (full inverse template from _scheme_inverse_template() + those overrides);
    the rest inherit the v4 default inverse. See _THEME_INVERSE."""
    override = _THEME_INVERSE.get(theme_id)
    if not override:
        return {}
    return {**_scheme_inverse_template(), **override}


def _build_inverse2(theme_id: str) -> dict:
    """The v4 SECOND inverse color scheme `.color-scheme-inverse-2` for a theme, or
    `{}` if the theme has no per-theme inverse-2 override. See _THEME_INVERSE2 for
    why this exists (a theme whose header and footer darkMode need genuinely
    different colors, e.g. x_petfriendly)."""
    override = _THEME_INVERSE2.get(theme_id)
    if not override:
        return {}
    return {**_scheme_inverse2_template(), **override}


def _build_main(theme_id: str) -> dict:
    """The v4 main color scheme `.color-scheme-main` for a theme, or `{}` if the theme
    has no per-theme main override. Only themes in `_THEME_MAIN_OVERRIDES` get the
    block (full main template from _scheme_main_template() + those overrides); the
    rest inherit the v4 default main untouched. Scoped, one-off use so far (not the
    general Phase 4 pass) — see `_THEME_MAIN_OVERRIDES`."""
    override = _THEME_MAIN_OVERRIDES.get(theme_id)
    if not override:
        return {}
    return {**_scheme_main_template(), **override}


def convert_theme(theme_id: str, warnings: list = None) -> dict:
    """Convert a v3 theme (by id, from _theme_registry()) → a v4 *theme* JSON.

    The v4 theme is the "Theme" layer that sits on top of Base: it carries only a
    SPARSE :root override (brand/neutral colors, fonts, per-theme typography) —
    every key that differs from Base — plus a theme envelope. Structure shared with
    Base (widget/typo rules, info defaults) is left out; the v4 system merges this
    over Base. `.color-scheme-main` is also left out for nearly every theme (inherits
    Base's default untouched) EXCEPT the few in `_THEME_MAIN_OVERRIDES` — a scoped,
    one-off mechanism, not the general per-theme Phase 4 pass (still not started, see
    `v4-themes/VERIFIED.md`). id is left null (assigned on import).

    Google fonts are KEPT in the family stack (unlike the website converter, which
    drops them) and registered in info.fontManifest = {"google": [...]}; a warning
    notes each so the theme team can verify they exist in v4."""
    registry = _theme_registry()
    entry = registry.get(theme_id)
    if entry is None:
        raise ValueError(
            "Unknown theme id %r. Valid ids: %s"
            % (theme_id, ", ".join(sorted(registry)))
        )
    manifest: dict = {}
    root = _build_theme_root(
        entry.get("colors"), entry.get("fonts"), theme_id, warnings=warnings,
        keep_google=True, manifest=manifest)
    # Normalize anchor hex values to 6-digit lowercase (e.g. "#000" → "#000000");
    # the computed scale is already 6-digit. Theme-only — website is untouched.
    for k in root:
        if k.startswith("color"):
            root[k] = _norm_hex(root[k])
    if theme_id == "x_petfriendly":
        # BrandBold placeholder (2026-07-21, user-requested, explicitly temporary
        # pending manual tuning): this theme's own palette CSS sets schemeA_d ==
        # schemeA (both #f46f43, see COLORS.md) -- so BrandBold rendered pixel-
        # identical to Brand everywhere it was read (see the
        # _THEME_MAIN/_THEME_MAIN2_OVERRIDES link-color repoints above, which move
        # those specific usages onto Brand directly instead). Re-set BrandBold
        # itself to sit visually between Brand and the already-computed
        # BrandBoldest, rather than leaving it == Brand, so it's at least a
        # distinct step until hand-tuned for real.
        b, bb = root.get("colorBrand"), root.get("colorBrandBoldest")
        if b and bb:
            root["colorBrandBold"] = _interp(b, bb, 0.5)
    if theme_id in _THEME_TAG_BORDER_WIDTH:
        root["tagBorderWidth"] = {"value": 1, "unit": "px"}
        root["tagHoverBorderWidth"] = {"value": 1, "unit": "px"}
    if theme_id == "x_supercar":
        # Link hover underline (2026-07-21, user-requested): v4-base's :root
        # default `linkHoverTextDecoration` is "underline" -- this theme wants
        # no underline on any link hover, in every scheme (root-level, so one
        # override covers main/main-2/inverse at once, same as tagBorderWidth
        # above).
        root["linkHoverTextDecoration"] = "none"
    if theme_id == "x_elite":
        # Section bg-overlay color (2026-08-04, user-found on the live demo,
        # section right before the footer, a "Dark Parallax Background"
        # preset): v4-base's :root default `overlayBgColor`/
        # `overlayBgColorOpacity` = black/0.4, but this theme's real overlay
        # is WHITE at 50% opacity -- not derivable from this repo's v3/ CSS
        # (no `.overlay-bg` rule exists in x_elite's own theme partial at
        # all; likely lives in a shared/base stylesheet outside this repo's
        # vendored snapshot, same situation as Bakery's title-color mixin
        # from Session 22). Root-level, so this is a THEME-WIDE default --
        # only one isOverlay:true section exists in the demo currently
        # (checked), so no known collision, but a future overlay section on
        # this theme would inherit it too.
        root["overlayBgColor"] = "#ffffff"
        root["overlayBgColorOpacity"] = 0.5
    if theme_id == "x_bluehorizon":
        # Button border width (2026-07-21, user-found): same class of bug as
        # x_supercar's tagBorderWidth -- v4-base's :root default is
        # `buttonPrimaryBorderWidth`/`buttonPrimaryHoverBorderWidth` = 0px, so
        # Primary's outline (a real border-COLOR, brand blue) renders
        # invisibly. Fixed to 1px. `buttonSecondaryBorderWidth`/
        # `buttonSecondaryHoverBorderWidth` default to 1px in v4-base, the
        # OPPOSITE problem -- Secondary here is a solid-fill button with a
        # transparent border, so explicitly zeroed for cleanliness. Root-level,
        # covers every scheme (main/main-2/inverse) at once.
        root["buttonPrimaryBorderWidth"] = {"value": 1, "unit": "px"}
        root["buttonPrimaryHoverBorderWidth"] = {"value": 1, "unit": "px"}
        root["buttonSecondaryBorderWidth"] = {"value": 0, "unit": "px"}
        root["buttonSecondaryHoverBorderWidth"] = {"value": 0, "unit": "px"}
        # BrandSubtle/BrandSubtlest re-pointed (2026-07-21, user request): this
        # theme's CSS-provided schemeA_l anchor (`#f8fbfd`) is so pale it's
        # nearly indistinguishable from the auto-computed BrandSubtlest
        # (`#fcfdfe`, 80%-white mix of Brand) -- two tokens for one shade.
        # User's fix: keep `#f8fbfd` as BrandSubtlest (it WAS the near-white
        # end already), and give BrandSubtle a new, actually-distinct value --
        # an 80%-white mix of Brand (tried 60%-white first, `#a0c0d6`; user
        # said too dark, wanted lighter -- 80% keeps it clearly readable as a
        # step but still airy), computed from this theme's real Brand
        # (`#6096ba`) instead of the too-pale CSS anchor. Every existing
        # `var(--color-brand-subtle)` reference in this theme's overrides was
        # repointed to `var(--color-brand-subtlest)` EXCEPT Secondary's
        # background fill (_THEME_MAIN_OVERRIDES/_THEME_MAIN2_
        # OVERRIDES["x_bluehorizon"]), which keeps `brand-subtle` — now
        # resolving to the new, more distinct blue, exactly where the user
        # wants it visible.
        root["colorBrandSubtlest"] = "#f8fbfd"
        root["colorBrandSubtle"] = _mix(root.get("colorBrand", "#6096ba"), _WHITE, 0.8)
    if theme_id == "x_mixednuts":
        # BrandSubtle/Bold(est) re-derived from the REAL Brand green (2026-08-06,
        # user request + investigation): this theme's registry anchors for those two
        # slots (`colors[4]`/`colors[5]` in themes.js) are literally `'#fff'` --
        # not a real color choice, just the v3 admin's unset/placeholder swatch
        # value (confirmed: `themes.js` has the exact same `'#fff'` hardcoded at
        # both indices). `_fill_color_scale()` can't tell "placeholder white" from
        # "the designer really wants white here" -- it took the anchor at face
        # value, computing BrandSubtlest as mix(white, white, 0.5) = white, and
        # BrandBoldest as mix(white, BLACK, 0.4) = a plain GREY (`#999999`-ish) --
        # the grey the user flagged as clearly wrong (should relate to the green
        # Brand, not be an unrelated grey). Re-derived all 4 steps straight from
        # the real Brand anchor (`#849940`) using the same mix ratios
        # `_fill_color_scale()`'s own `elif b:` branch would have used had the
        # anchors genuinely been empty:
        b = root.get("colorBrand", "#849940")
        root["colorBrandSubtle"] = _mix(b, _WHITE, 0.4)
        root["colorBrandSubtlest"] = _mix(b, _WHITE, 0.8)
        root["colorBrandBold"] = _mix(b, _BLACK, 0.25)
        root["colorBrandBoldest"] = _mix(b, _BLACK, 0.5)
    style: dict = {}
    if root:
        style[":root"] = root
    # Key order: main, main-2, inverse, inverse-2 (2026-07-21, user-requested) --
    # light-to-dark reading order, not build order.
    main = _build_main(theme_id)
    if main:
        style[".color-scheme-main"] = main
    scheme2 = _build_scheme2(theme_id)
    if scheme2:
        style[".color-scheme-main-2"] = scheme2
    inverse = _build_inverse(theme_id)
    if inverse:
        style[".color-scheme-inverse"] = inverse
    inverse2 = _build_inverse2(theme_id)
    if inverse2:
        style[".color-scheme-inverse-2"] = inverse2
    for selector, override in _THEME_WIDGET_STYLE_OVERRIDES.get(theme_id, {}).items():
        style[selector] = override
    return {
        "id": None,                 # assigned by the target system on import
        "theme_key": theme_id,
        "name": entry.get("title", theme_id),
        "description": "",
        "images": None,
        "thumbnail": None,
        "status": "public",
        "style": style,
        # Only fontManifest (Google fonts to load); else {} — no overrides on Base.
        "info": {"fontManifest": manifest} if manifest else {},
        "preset": None,
    }


def list_themes() -> list:
    """Return the selectable themes as [{"id","title"}], sorted by title — for the
    batch generator and any caller listing what `theme` mode accepts."""
    return sorted(
        ({"id": tid, "title": e.get("title", tid)} for tid, e in _theme_registry().items()),
        key=lambda t: t["title"].lower(),
    )


def generate_all_themes(outdir: str) -> list:
    """Write a v4 theme JSON for every selectable theme into `outdir`, one file per
    theme (`<theme_id>.json`), plus a CHECKLIST.md for eyeball verification.

    Theme conversion is a one-time batch (the selectable set is fixed), so this is
    the primary entry point — not a long-lived UI. Returns summary rows
    [{"id","name","root","google"}] (google = Google fonts kept in fontManifest, to
    verify exist in v4)."""
    os.makedirs(outdir, exist_ok=True)
    rows = []
    for t in list_themes():
        warns: list = []
        res = convert_theme(t["id"], warns)
        _write(res, os.path.join(outdir, t["id"] + ".json"))
        google = sorted((res.get("info", {}).get("fontManifest", {}) or {}).get("google", []))
        rows.append({"id": t["id"], "name": res["name"],
                     "demo": _theme_registry()[t["id"]].get("demo", ""),
                     "root": len(res["style"].get(":root", {})),
                     "alt": ".color-scheme-main-2" in res["style"],
                     "google": google})
    _write_theme_checklist(outdir, rows)
    return rows


def _write_theme_checklist(outdir: str, rows: list) -> None:
    """Render CHECKLIST.md as an interactive task list (so `- [ ]` renders as a real
    checkbox in a Markdown preview and toggles with editor shortcuts like Alt+C)."""
    lines = [
        "# v4 Theme Conversion — Checklist",
        "",
        f"{len(rows)} **published** v3 themes → v4 theme JSON "
        "(`python3 converter.py theme all <dir>`).",
        "Scope = themes that are **live/in real use** on v3: both `isActive` **and** "
        "`isSelectable` true in `themes.js`. Excluded: `isSelectable:false` (private "
        "designs), `isActive:false` (unfinished — e.g. `x_futuristic`, `x_soda`), and "
        "`x_cozy_fw`/`x_orderly` (published, but already built by hand directly in v4 "
        "by the design team — see `_THEME_ALREADY_DESIGNED`).",
        "Each output is a **sparse `:root` override** on top of Base "
        "(colors + fonts + typography). Google fonts are kept in the stack and listed "
        "in `info.fontManifest` — **verify each exists in v4**.",
        "Themes with a v3 darkMode also emit an **alternative color scheme** "
        "(`.color-scheme-main-2`, marked `alt` below) — check its bg/text in "
        "REVIEW-GUIDE's alt-scheme table too.",
        "See **REVIEW-GUIDE.md** for what to spot-check per theme (font/color conflicts).",
        "Tick a theme (`- [ ]` → `- [x]`) after eyeballing its JSON against the live v3 demo.",
        "",
    ]
    for r in rows:
        demo = f"[demo]({r['demo']})" if r.get("demo") else "demo??"
        google = f" · google: {', '.join(r['google'])}" if r["google"] else ""
        alt = " · **alt**" if r.get("alt") else ""
        lines.append(
            f"- [ ] **{r['name']}** `{r['id']}` — {demo} · `:root` {r['root']}{alt}{google}"
        )
    lines.append("")
    with open(os.path.join(outdir, "CHECKLIST.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def convert_zones(site_json: dict) -> dict:
    """Extract global zones from a v3 site JSON.

    Returns {"header_zone": {...}|None, "footer_zone": {...}|None, "free_zone": {...}}.
    free_zone is built from `components.ContactWidget` (see _build_free_zone).
    """
    result: dict = {
        "header_zone": None,
        "footer_zone": None,
        "free_zone": None,
    }
    header = site_json.get("header")
    if isinstance(header, dict) and "HeaderSection" in header:
        result["header_zone"] = convert_header(header)
    footer = site_json.get("footer")
    if isinstance(footer, dict) and "FooterSection" in footer:
        result["footer_zone"] = convert_footer(footer)
    components = (site_json.get("components") or {}) if isinstance(site_json, dict) else {}
    result["free_zone"] = _build_free_zone(components)
    return result


# ---------------------------------------------------------------------------
# Dispatcher — register new section types here
# ---------------------------------------------------------------------------

def _customhtml_nickname(props: dict) -> str:
    """Nickname for a CustomHtml section/widget: the v3 `title` if set, else a
    generic label so the block is identifiable in the v4 editor."""
    title = (props.get("title") or "").strip()
    return title or "Custom HTML"


def build_customhtml_section(props: dict) -> dict:
    """CustomHtmlSection → a section holding an EMPTY WidgetCustomHtml
    (renderMode "inline"). The v3 `customHtml` string is intentionally NOT
    embedded — v4 stores custom HTML in the shop's manage area, so the designer
    must paste it there (convert_section emits a warning saying so)."""
    nickname = _customhtml_nickname(props)
    widget = make_node("widget", "WidgetCustomHtml", nickname, {"renderMode": "inline"})
    section = _simple_section([widget])
    section["nickname"] = nickname
    return section


SECTION_BUILDERS = {
    "ParagraphSection": build_paragraph_section,
    "Headline":         build_headline_section,
    "SlideShowSection": build_slideshow_section,
    "BannerSlick":      build_bannerslick_section,
    "FeatureSection":   build_featuresection_section,
    "ProductSection":   build_productsection_section,
    "ProductTab":       build_producttab_section,
    "GallerySection":      build_gallerysection_section,
    "SlideTextSection":    build_slidetextsection_section,
    "BlogSection":         build_blog_section,
    "TopicSection":        build_topicsection_section,
    "BannerSection":       build_bannersection_section,
    "PromotionSlick":      build_promotionslick_section,
    "CouponSlick":         build_couponslick_section,
    "ContactusSection":    build_contactussection_section,
    "FaqsSection":         build_faqssection_section,
    "CustomHtmlSection":   build_customhtml_section,
}


def convert_section(old_json: dict, warnings: list = None) -> dict:
    name    = old_json.get("name", "")
    props   = old_json.get("props", {})
    builder = SECTION_BUILDERS.get(name)
    if not builder:
        raise ValueError(
            f"Unknown section type: '{name}'. "
            "Add a builder function and register it in SECTION_BUILDERS."
        )
    result = builder(props)
    # CustomHtml: the widget is empty by design — the v3 HTML is not embedded
    # (v4 keeps custom HTML in the shop's manage area). Warn so the designer
    # knows to paste it there.
    if name == "CustomHtmlSection" and warnings is not None:
        nickname = (result or {}).get("nickname") or "Custom HTML"
        cls  = (props.get("className") or "").strip()
        hint = f" (class: {cls})" if cls else ""
        warnings.append({
            "path": None, "kind": "warn",
            "msg": f"Custom HTML “{nickname}”{hint}: สร้าง widget ว่างให้แล้ว — "
                   "ต้องนำโค้ด HTML เดิมไปวางเองใน manage ของร้าน "
                   "(v4 เก็บ custom HTML แยกจากโครงหน้า)",
        })
    # --- Global section-level props (apply to most section types) ---
    # BannerSlick handles its own dark mode (no colorScheme mapping)
    if result is not None and props.get("isDarkMode") and name != "BannerSlick":
        result["info"]["colorScheme"] = "color-scheme-inverse"
    return result


# ---------------------------------------------------------------------------
# Page-level converter
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# System page default sections
#
# Each builder receives the v3 page dict and returns a list of section nodes
# that are prepended to the page's children before any converted v3 layouts.
# Keyed by default_key (= v3_key for pages that have one, or a custom string).
# ---------------------------------------------------------------------------

_IMAGE_TYPE_TO_OBJECT_FIT: dict = {
    "resize": "cover",
    "max":    "contain",
}

_SORT_PRICE_FILTERS: list = [
    {
        "id": "sort", "name": "จัดเรียงตาม", "type": "radio", "enabled": True,
        "values": [
            {"name": "ยอดนิยม",      "id": "most_popular",      "enabled": True},
            {"name": "เวลามาใหม่",    "id": "newest",            "enabled": True},
            {"name": "ราคาต่ำไปสูง", "id": "price_low_to_high", "enabled": True},
            {"name": "ราคาสูงไปต่ำ", "id": "price_high_to_low", "enabled": True},
        ],
    },
    {
        "id": "f-price", "name": "Price", "type": "radio", "enabled": True,
        "values": [
            {"name": "THB0 - 499",       "id": "PRICE_0_500",                   "enabled": True},
            {"name": "THB500 - 999",     "id": "PRICE_500_1000",                "enabled": True},
            {"name": "THB1,000 - 1,999", "id": "PRICE_1000_2000",               "enabled": True},
            {"name": "THB2,000 - 4,999", "id": "PRICE_2000_5000",               "enabled": True},
            {"name": "THB5,000+",        "id": "PRICE_5000_9223372036854775807", "enabled": True},
        ],
    },
]


def _px(lg, xs=None, md=None) -> dict:
    """Build a breakpoint size dict {lg:{value,unit}, xs?:..., md?:...}."""
    r: dict = {"lg": {"value": lg, "unit": "px"}}
    if xs is not None:
        r["xs"] = {"value": xs, "unit": "px"}
    if md is not None:
        r["md"] = {"value": md, "unit": "px"}
    return r


def _simple_col(widgets: list, col_info: dict = None) -> dict:
    return make_node("col", None, None, col_info or {}, widgets)


def _simple_section(widgets: list, section_info: dict = None,
                    section_kind=None, col_info: dict = None) -> dict:
    col = _simple_col(widgets, col_info)
    row = make_node("row", None, None, {}, [col])
    return make_node("section", section_kind, None, section_info or {}, [row])


# ── /blog ────────────────────────────────────────────────────────────────────

def _default_blog_list_sections(v3_page: dict) -> list:
    cfg = v3_page.get("BlogAllSection")
    if cfg is None:
        # Fresh default: no BlogAllSection configured
        blog_info = {
            "isShowDate": True, "isShowTag": True,
            "mediaObjectFit": "contain", "mediaRatio": "1 / 1",
        }
        return [_simple_section([make_node("widget", "WidgetBlogList", None, blog_info)])]

    # BlogAllSection present → map its fields + add heading
    blog_info: dict = {
        "isShowDate": cfg.get("isShowDate", True),
        "isShowTag":  cfg.get("isShowTag",  True),
    }
    image_type = cfg.get("imageType")
    if image_type and image_type in _IMAGE_TYPE_TO_OBJECT_FIT:
        blog_info["mediaObjectFit"] = _IMAGE_TYPE_TO_OBJECT_FIT[image_type]
    if cfg.get("isCropImage"):
        blog_info["mediaRatio"] = "1 / 1"

    heading    = make_node("widget", "WidgetHeading", None, {"title": {"text": "บทความทั้งหมด"}})
    blog_widget = make_node("widget", "WidgetBlogList", None, blog_info)
    col     = make_node("col",  None, None, {}, [heading, blog_widget])
    row     = make_node("row",  None, None, {}, [col])
    section = make_node("section", None, "BlogList", {}, [row])
    return [section]


# ── /blog/* ───────────────────────────────────────────────────────────────────

def _default_blog_detail_sections(_v3_page: dict) -> list:
    return [_simple_section([make_node("widget", "WidgetBlogDetail", None, {})])]


# ── /category/* ───────────────────────────────────────────────────────────────

def _default_category_sections(_v3_page: dict) -> list:
    s1 = _simple_section([
        make_node("widget", "WidgetBreadcrumb", None, {}),
        make_node("widget", "WidgetCategoryDetail", None, {
            "category_id": "{{PAGE_CATEGORY_ID}}",
            "layoutCard": {"variant": "fit-image"},
            "mediaWidth": {"lg": {"value": 300, "unit": "px"}},
        }),
    ], {
        "paddingTop":    {"lg": {"value": 20, "unit": "px"}, "xs": {"value": 12, "unit": "px"}},
        "paddingBottom": {"xs": {"value":  0, "unit": "px"}, "lg": {"value":  0, "unit": "px"}},
    })

    s2 = _simple_section([
        make_node("widget", "WidgetCategoryList", None, {"category_id": "{{PAGE_CATEGORY_ID}}"}),
    ], {
        "paddingTop":          {"lg": {"value": 20, "unit": "px"}, "xs": {"value": 12, "unit": "px"}},
        "paddingBottom":       {"xs": {"value": 12, "unit": "px"}, "lg": {"value": 20, "unit": "px"}},
        "isHideWhenNoContent": True,
    })

    s3 = _simple_section([
        make_node("widget", "WidgetSearchFilter", None, {
            "dataSetPrefix": None,
            "filters": _SORT_PRICE_FILTERS,
        }),
        make_node("widget", "WidgetProductList", None, {
            "isShowPagination": True,
            "dataSetPrefix": None,
            "productNumber": 20,
            "apiOptions": {"options": [], "filters": {"parent_category_id": "{{PAGE_CATEGORY_ID}}"}},
        }),
    ], {"paddingTop": {"xs": {"value": 20, "unit": "px"}, "lg": {"value": 40, "unit": "px"}}})

    return [s1, s2, s3]


# ── /product/* ────────────────────────────────────────────────────────────────

def _default_product_sections(_v3_page: dict) -> list:
    s1 = _simple_section(
        [make_node("widget", "WidgetBreadcrumb", None, {})],
        {"paddingTop": _px(20, xs=20), "paddingBottom": _px(20, xs=20)},
        section_kind="Accordion",
    )

    gallery_col = make_node("col", None, None, {
        "verticalAlign": "start",
        "span": {"xs": 12, "md": 8, "lg": 8},
    }, [make_node("widget", "WidgetProductGallery", None, {"layout": "highlight-grid"})])

    info_col = make_node("col", None, None, {
        "position": "sticky",
        "top": {"lg": {"value": 20, "unit": "px"}},
        "height": {"lg": "fit-content"},
        "verticalAlign": "start",
        "gap": {"xs": {"value": 25, "unit": "px"}, "lg": {"value": 25, "unit": "px"}},
        "span": {"xs": 12, "md": 4, "lg": 4},
    }, [
        make_node("widget", "WidgetProductSummary", None, {}),
        make_node("widget", "WidgetProductDescription", None, {
            "items": [
                {"id": "product-detail",    "title": {"text": "รายละเอียด"}},
                {"id": "product-how-to-buy", "title": {"text": "วิธีสั่งซื้อ"}},
            ],
            "isShowHilight": False,
        }),
    ])
    s2 = make_node("section", None, None,
                   {"paddingTop": _px(60, xs=20)},
                   [make_node("row", None, None, {}, [gallery_col, info_col])])

    s3 = _simple_section([
        make_node("widget", "WidgetRelatedProductList", None, {"productNumber": 5}),
    ], col_info={"span": {"xs": 12, "md": 12, "lg": 12}})

    return [s1, s2, s3]


# ── /promotion ────────────────────────────────────────────────────────────────

def _default_promotion_list_sections(_v3_page: dict) -> list:
    return [_simple_section([
        make_node("widget", "WidgetHeading", None, {
            "title": {"as": "h2", "text": "โปรโมชั่นทั้งหมด"},
        }),
        make_node("widget", "WidgetPromotionList", None, {}),
    ])]


# ── /search ───────────────────────────────────────────────────────────────────

def _default_search_sections(_v3_page: dict) -> list:
    s1 = _simple_section([
        make_node("widget", "WidgetSearchResultHeading", None, {
            "productsDataSetPrefix": None,
            "blogsDataSetPrefix": "b",
        }),
    ], {
        "paddingTop":    {"xs": {"value": 20, "unit": "px"}, "lg": {"value": 40, "unit": "px"}},
        "paddingBottom": {"xs": {"value": 20, "unit": "px"}, "lg": {"value": 40, "unit": "px"}},
    })

    product_filter_col = _simple_col([
        make_node("widget", "WidgetHeading", None, {
            "alignment": "left",
            "title": {"text": "สินค้าที่เกี่ยวข้อง", "as": "h2",
                      "typoStyle": "typo_heading_small_bold"},
        }),
        make_node("widget", "WidgetSearchFilter", None, {
            "dataSetPrefix": None,
            "filters": _SORT_PRICE_FILTERS,
        }),
    ], {"gap": {"xs": {"value": 20, "unit": "px"}, "lg": {"value": 28, "unit": "px"}}})

    product_list_col = _simple_col([
        make_node("widget", "WidgetProductList", None, {
            "dataSetPrefix": None, "isShowPagination": True, "productNumber": 10,
        }),
    ])
    s2 = make_node("section", None, None, {
        "id": "result-product-list-anchor",
        "paddingTop":    {"xs": {"value": 20, "unit": "px"}, "lg": {"value": 40, "unit": "px"}},
        "paddingBottom": {"xs": {"value": 20, "unit": "px"}, "lg": {"value": 40, "unit": "px"}},
    }, [
        make_node("row", None, None, {}, [product_filter_col]),
        make_node("row", None, None, {}, [product_list_col]),
    ])

    blog_heading_col = _simple_col([
        make_node("widget", "WidgetHeading", None, {
            "alignment": "left",
            "title": {"text": "บทความที่เกี่ยวข้อง", "as": "h2",
                      "typoStyle": "typo_heading_small_bold"},
        }),
    ])
    blog_list_col = _simple_col([
        make_node("widget", "WidgetBlogList", None, {
            "dataSetPrefix": "b", "dataSetPrefixForTag": None,
            "isShowPagination": True, "blogNumber": 3,
        }),
    ])
    s3 = make_node("section", None, None, {
        "id": "result-blog-list-anchor",
        "paddingTop":    {"lg": {"value": 40, "unit": "px"}},
        "paddingBottom": {"lg": {"value": 40, "unit": "px"}},
    }, [
        make_node("row", None, None, {}, [blog_heading_col]),
        make_node("row", None, None, {}, [blog_list_col]),
    ])

    return [s1, s2, s3]


SYSTEM_PAGE_DEFAULTS: dict = {
    "blog":             _default_blog_list_sections,
    "blogdetail":       _default_blog_detail_sections,
    "search":           _default_category_sections,
    "product":          _default_product_sections,
    "promotion":        _default_promotion_list_sections,
    "blogsearch":       _default_search_sections,
}


def convert_page(
    page_json: dict,
    layouts: list = None,
    path: str = None,
    nickname: str = None,
    module=None,
    modules: list = None,
    component_kind: str = None,
    default_key: str = None,
    warnings: list = None,
) -> dict:
    """Convert a page object to the v4 page envelope format.

    Keyword args override whatever is inside page_json.
    Pass layouts= directly for pages where they live at a non-standard path.
    Pass modules= (list) for pages with multiple modules; it is emitted as a
    separate 'modules' key and 'module' is set to null.
    Pass default_key= (v3_key string) so that SYSTEM_PAGE_DEFAULTS sections are
    prepended before any converted v3 layouts.
    """
    if layouts is None:
        layouts = page_json.get("layouts") or []

    children = []

    # Prepend hardcoded default section(s) for this system page type
    if default_key and default_key in SYSTEM_PAGE_DEFAULTS:
        children.extend(SYSTEM_PAGE_DEFAULTS[default_key](page_json))

    for i, section in enumerate(layouts):
        try:
            converted = convert_section(section, warnings)
            if converted is not None:
                children.append(converted)
        except ValueError as e:
            print(f"⚠️  Skipping section {i} ({section.get('name', '?')}): {e}")

    page_component = make_node("page", component_kind, None, {}, children)

    result = {
        "path":      path     or page_json.get("path"),
        "config_id": None,
        "nickname":  nickname or page_json.get("title"),
        "module":    None if modules else module,
        "hide":      False,
        "component": page_component,
    }
    if modules:
        result["modules"] = modules
    return result


# ---------------------------------------------------------------------------
# V4 page table  (single source of truth for all system pages)
#
# Ordered list — defines the output page order for site mode.
# Each entry fields:
#   path, nickname, module, component_kind  — v4 metadata
#   modules     (list)   — when a page belongs to multiple modules;
#                          emits as 'modules' key with module: null
#   v3_key      (str)    — key in the v3 site JSON that provides layouts;
#                          None = v4-only page (no v3 source)
#   skip_if_empty (bool) — omit the page entirely when its v3 layouts are empty
#                          (or v3_key is None); v4 auto-creates these pages
# ---------------------------------------------------------------------------
V4_PAGES: list = [
    # v3 source          v4 path           v4 nickname              module           kind                     skip_if_empty
    {"v3_key": "frontpage",  "path": "/",           "nickname": "Home",              "module": "core",       "component_kind": None},
    {"v3_key": None,         "path": "/404",         "nickname": "Not Found",         "module": "core",       "component_kind": None,                                                                             "skip_if_empty": True},
    {"v3_key": "blog",       "path": "/blog",        "nickname": "Blog List : blog",  "module": "blog",       "component_kind": "PageBlogList",                                                                   "skip_if_empty": True},
    {"v3_key": "blogdetail", "path": "/blog/*",      "nickname": "Blog Detail : blog","module": "blog",       "component_kind": "PageBlogDetail",                                                                   "skip_if_empty": True},
    {"v3_key": "search",     "path": "/category/*",  "nickname": "Category",          "module": "ecommerce",  "component_kind": "PageEcommerceCategory",                                                          "skip_if_empty": True},
    {"v3_key": None,         "path": "/close",       "nickname": "Close",             "module": "ecommerce",  "component_kind": None,                                                                             "skip_if_empty": True},
    {"v3_key": "contactus",  "path": "/contactus",   "nickname": "ContactUs",         "module": None,         "component_kind": None},
    {"v3_key": None,         "path": "/coupon",      "nickname": "Coupon List",       "module": "ecommerce",  "component_kind": None,                                                                             "skip_if_empty": True},
    {"v3_key": None,         "path": "/coupon/*",    "nickname": "Coupon Detail",     "module": "ecommerce",  "component_kind": None,                                                                             "skip_if_empty": True},
    {"v3_key": "product",    "path": "/product/*",   "nickname": "Product",           "module": "ecommerce",  "component_kind": "PageEcommerceProduct",                                                           "skip_if_empty": True},
    {"v3_key": "promotion",  "path": "/promotion",   "nickname": "Promotion List",    "module": "ecommerce",  "component_kind": None,                                                                             "skip_if_empty": True},
    {"v3_key": None,         "path": "/promotion/*", "nickname": "Promotion Detail",  "module": "ecommerce",  "component_kind": None,                                                                             "skip_if_empty": True},
    {"v3_key": "blogsearch", "path": "/search",      "nickname": "Search",            "module": None,         "component_kind": "PageSearch",      "modules": ["blog", "ecommerce"],                                      "skip_if_empty": True},
]

# v3 keys that have no v4 system page — convert as custom pages (module: null, kind: null)
SYSTEM_PAGES_AS_CUSTOM: set = {"help"}

# All v3_key values claimed by V4_PAGES (fast lookup)
_V4_CLAIMED_KEYS: set = {e["v3_key"] for e in V4_PAGES if e["v3_key"]}


def _get_layouts_from_v3(page_json: dict) -> list:
    return page_json.get("layouts") or []


def _make_unique_path(base: str, used: set) -> str:
    """Return base if not in used, else base-1, base-2, …"""
    if base not in used:
        return base
    i = 1
    while f"{base}-{i}" in used:
        i += 1
    return f"{base}-{i}"


def _path_from_title(title: str) -> str:
    """Derive a URL path slug from a page title."""
    slug = re.sub(r"[^\w\s-]", "", title.lower()).strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    return f"/{slug}" if slug else "/page"


def convert_site(site_json: dict, warnings: list = None) -> list:
    """Convert a full site JSON containing multiple pages.

    Returns an ordered list of v4 page objects:
      1. All V4_PAGES entries in table order (system pages + v4-only pages).
      2. Any v3 system keys in SYSTEM_PAGES_AS_CUSTOM (e.g. "help").
      3. All entries in customRoutes.
    """
    results = []

    # ── 1. System pages (V4_PAGES table order) ───────────────────────────
    for entry in V4_PAGES:
        v3_key      = entry["v3_key"]
        v3_value    = site_json.get(v3_key) if v3_key else None
        layouts     = _get_layouts_from_v3(v3_value) if v3_value else []
        if entry.get("skip_if_empty") and not layouts:
            continue
        results.append(convert_page(
            v3_value or {},
            layouts=layouts,
            path=entry["path"],
            nickname=entry["nickname"],
            module=entry.get("module"),
            modules=entry.get("modules"),
            component_kind=entry.get("component_kind"),
            default_key=v3_key,
            warnings=warnings,
        ))

    # ── 2. v3 keys treated as custom (e.g. "help") ───────────────────────
    for key in SYSTEM_PAGES_AS_CUSTOM:
        value = site_json.get(key)
        if not isinstance(value, dict):
            continue
        layouts = value.get("layouts") or []
        if not layouts:
            continue
        results.append(convert_page(
            value,
            layouts=layouts,
            path=f"/{key}",
            nickname=key.capitalize(),
            warnings=warnings,
        ))

    # ── 3. customRoutes ──────────────────────────────────────────────────
    # Reserve every system path (incl. skipped ones, which v4 auto-creates) so a
    # v3 custom page that collides gets a unique '-N' suffix instead of clashing.
    used_paths: set = {entry["path"] for entry in V4_PAGES}
    used_paths.update(p["path"] for p in results)
    for page in site_json.get("customRoutes") or []:
        if not (isinstance(page, dict) and "layouts" in page):
            continue
        raw_path = (page.get("path") or "").replace(" ", "-")
        if raw_path:
            path = _make_unique_path(raw_path, used_paths)
        else:
            title = page.get("title") or ""
            path = _make_unique_path(_path_from_title(title), used_paths)
        used_paths.add(path)
        results.append(convert_page(page, path=path, warnings=warnings))

    # ── unknown v3 keys with layouts → custom page (skip if layouts empty) ─
    skip = _V4_CLAIMED_KEYS | SYSTEM_PAGES_AS_CUSTOM | {"customRoutes"}
    for key, value in site_json.items():
        if key in skip or not isinstance(value, dict):
            continue
        layouts = value.get("layouts") or []
        if not layouts:
            continue
        path = _make_unique_path(f"/{key}", used_paths)
        used_paths.add(path)
        results.append(convert_page(
            value,
            layouts=layouts,
            path=path,
            nickname=key.capitalize(),
            warnings=warnings,
        ))

    return results

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _is_page_value(v) -> bool:
    """True if a dict looks like a v3 page (has layouts, or layoutsByCondition array)."""
    if not isinstance(v, dict):
        return False
    if "layouts" in v:
        return True
    lbc = v.get("layoutsByCondition")
    return isinstance(lbc, list) and bool(lbc)


def _detect_mode(data) -> str:
    """Infer conversion mode from the shape of the parsed input."""
    if isinstance(data, list):
        # list of page objects (e.g. a standalone customRoutes array)
        if data and isinstance(data[0], dict) and "layouts" in data[0]:
            return "pages"
        return "sections"
    if isinstance(data, dict):
        if "layouts" in data:
            return "page"
        if "name" in data and "props" in data:
            return "sections"
        if "customRoutes" in data or any(_is_page_value(v) for v in data.values()):
            return "site"
    return "sections"


_USAGE = """\
Usage:
  python3 converter.py sections <input.json> [output.json]
      Convert one or more sections (JSON array or single object).

  python3 converter.py page <input.json> [output.json]
      Convert a single custom-route page  (must have "layouts" array).

  python3 converter.py site <input.json> [output.json]
      Convert a full site JSON. Output is a single JSON object with keys:
        "pages"        — ordered list of v4 page objects
        "footer_zone"  — v4 footer zone (null when absent)
        "header_zone"  — stub, null (pending)
        "free_zone"    — stub, null (pending)

  python3 converter.py zones <input.json> [output.json]
      Extract only the global zones (header_zone, footer_zone, free_zone)
      without converting pages.

  python3 converter.py global <input.json> [output.json]
      Convert global components (ProductBox, ProductList, ContactWidget) to
      the v4 triplet {info, style, free_zone}.

  python3 converter.py theme <theme_id> [output.json]
      Convert a v3 theme (by id, e.g. x_bakery) → a v4 theme JSON. Output is a
      sparse :root override (colors/fonts/typography) on top of Base, with a
      theme envelope. theme_id must be a published theme in v3/themes.js
      (isActive && isSelectable).

  python3 converter.py theme all [outdir]
      Batch-convert ALL selectable themes into outdir/<theme_id>.json (default
      outdir: v4-themes/) plus a CHECKLIST.md for eyeball verification.

  python3 converter.py <input.json> [output.json]
      Legacy auto-detect (sections or single page).
"""


def _load_json(path: str):
    """Read and parse a JSON file; also accepts bare comma-separated objects.
    Replaces [..] placeholder stubs (used in example files) with [].
    """
    import re as _re
    with open(path, encoding="utf-8") as f:
        raw = f.read().strip()
    raw = _re.sub(r'\[\s*\.\.\s*\]', '[]', raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        try:
            return json.loads(f"[{raw}]")
        except json.JSONDecodeError as e:
            print(f"❌  Could not parse {path}: {e}")
            sys.exit(1)


def _write(data, path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _section_count(page_result: dict) -> int:
    return len((page_result.get("component") or {}).get("children") or [])


def main():
    args = sys.argv[1:]
    MODES = {"sections", "page", "pages", "site", "zones", "global", "theme"}

    if args and args[0] in MODES:
        mode, args = args[0], args[1:]
    else:
        mode = None  # auto-detect after loading

    if not args:
        print(_USAGE)
        sys.exit(1)

    # ── theme ────────────────────────────────────────────────────────────────
    # Input is a theme id (from _theme_registry()), NOT a JSON file — handle
    # before the _load_json path below.
    if mode == "theme":
        # Batch: `theme all [outdir]` writes every selectable theme + CHECKLIST.md.
        if args[0] == "all":
            outdir = args[1] if len(args) > 1 else "v4-themes"
            rows = generate_all_themes(outdir)
            print(f"✅  Generated {len(rows)} theme(s) → {outdir}/  (+ CHECKLIST.md)")
            for r in rows:
                g = f"  ⚑ google: {', '.join(r['google'])}" if r["google"] else ""
                print(f"   {r['id']:18s} {r['name']:20s} :root {r['root']:2d}{g}")
            return
        theme_id    = args[0]
        output_path = args[1] if len(args) > 1 else None
        theme_warnings: list = []
        try:
            result = convert_theme(theme_id, theme_warnings)
        except ValueError as e:
            print(f"❌  {e}")
            sys.exit(1)
        if output_path:
            _write(result, output_path)
            n_root = len(result["style"].get(":root", {}))
            print(f"✅  Converted theme {theme_id} ({result['name']}) → {output_path}"
                  f" (:root: {n_root} override(s))")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        for w in theme_warnings:
            print(f"⚠️   {w['msg']}", file=sys.stderr)
        return

    input_path  = args[0]
    output_path = args[1] if len(args) > 1 else None
    data        = _load_json(input_path)

    if mode is None:
        mode = _detect_mode(data)
        print(f"ℹ️   Auto-detected mode: {mode}")

    # ── site ───────────────────────────────────────────────────────────────
    if mode == "site":
        if not isinstance(data, dict):
            print("❌  site mode expects a JSON object at the top level.")
            sys.exit(1)
        theme_warnings: list = []
        pages  = convert_site(data, theme_warnings)
        zones  = convert_zones(data)
        globals_ = convert_global(data, theme_warnings)
        result = {
            "nickname":    "Imported",
            "theme_key":   "base",
            "info":        globals_["info"],
            "style":       globals_["style"],
            "css":         None,
            "header_zone": zones["header_zone"],
            "footer_zone": zones["footer_zone"],
            "free_zone":   zones["free_zone"],
            "pages":       pages,
            "unuse_configs": [],
        }
        if output_path:
            _write(result, output_path)
            total = sum(_section_count(p) for p in pages)
            has_footer = zones.get("footer_zone") is not None
            print(f"✅  Converted {len(pages)} page(s), {total} total section(s) → {output_path}"
                  f" (footer_zone: {'✓' if has_footer else '✗'})")
            for p in pages:
                n = _section_count(p)
                print(f"   {p['path']:25s} {p['nickname'] or '':30s} ({n} sections)")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        for w in theme_warnings:
            print(f"⚠️   {w['msg']}", file=sys.stderr)
        return

    # ── global ─────────────────────────────────────────────────────────────
    if mode == "global":
        if not isinstance(data, dict):
            print("❌  global mode expects a JSON object at the top level.")
            sys.exit(1)
        theme_warnings: list = []
        result = convert_global(data, theme_warnings)
        if output_path:
            _write(result, output_path)
            n_children = len(result["free_zone"].get("children", []))
            n_info = len(result["info"])
            n_style = len(result["style"])
            print(f"✅  Converted global config → {output_path}"
                  f" (info: {n_info} branch(es), style: {n_style} selector(s), "
                  f"free_zone children: {n_children})")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        for w in theme_warnings:
            print(f"⚠️   {w['msg']}", file=sys.stderr)
        return

    # ── zones ──────────────────────────────────────────────────────────────
    if mode == "zones":
        if not isinstance(data, dict):
            print("❌  zones mode expects a JSON object at the top level.")
            sys.exit(1)
        zones = convert_zones(data)
        if output_path:
            _write(zones, output_path)
            has_footer = zones.get("footer_zone") is not None
            print(f"✅  Converted zones → {output_path}"
                  f" (footer_zone: {'✓' if has_footer else '✗'}, "
                  f"header_zone: ✗ (pending), free_zone: ✗ (pending))")
        else:
            print(json.dumps(zones, indent=2, ensure_ascii=False))
        return

    # ── pages (list of page objects, e.g. customRoutes) ───────────────────
    if mode == "pages":
        if not isinstance(data, list):
            print("❌  pages mode expects a JSON array of page objects.")
            sys.exit(1)
        result = [convert_page(p) for p in data
                  if isinstance(p, dict) and "layouts" in p]
        if output_path:
            _write(result, output_path)
            total = sum(_section_count(p) for p in result)
            print(f"✅  Converted {len(result)} page(s), {total} total section(s) → {output_path}")
            for p in result:
                n = _section_count(p)
                print(f"   {p.get('path', '?'):25s} {p.get('nickname') or '':30s} ({n} sections)")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # ── page ───────────────────────────────────────────────────────────────
    if mode == "page":
        if not (isinstance(data, dict) and "layouts" in data):
            print("❌  page mode expects a JSON object with a 'layouts' key.")
            sys.exit(1)
        sec_warnings: list = []
        result = convert_page(data, warnings=sec_warnings)
        if output_path:
            _write(result, output_path)
            print(f"✅  Converted page with {_section_count(result)} section(s) → {output_path}")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        for w in sec_warnings:
            print(f"⚠️   {w['msg']}", file=sys.stderr)
        return

    # ── sections ───────────────────────────────────────────────────────────
    sec_warnings = []
    if isinstance(data, list):
        result = []
        for i, section in enumerate(data):
            try:
                result.append(convert_section(section, sec_warnings))
            except ValueError as e:
                print(f"⚠️  Skipping section {i} ({section.get('name', '?')}): {e}")
    else:
        result = convert_section(data, sec_warnings)

    if output_path:
        _write(result, output_path)
        count = len(result) if isinstance(result, list) else 1
        print(f"✅  Converted {count} section(s) → {output_path}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    for w in sec_warnings:
        print(f"⚠️   {w['msg']}", file=sys.stderr)


if __name__ == "__main__":
    main()