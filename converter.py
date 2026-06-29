"""
JSON Converter: Old Section Format → New Component-Based Format
Usage:
    python converter.py <input.json> [output.json]
    If output.json is omitted, result is printed to stdout.
"""

import difflib
import json
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

__version__ = "1.8"
LAST_UPDATED = "2026-06-29"

# Short summary of what the converter handles — shown in the browser popup.
# Plain strings; inline HTML (e.g. <code>) is allowed for rendering there.
CAPABILITIES = [
    "แปลงโค้ด JSON หน้าร้าน LNW Shop จาก <code>v3</code> เป็น <code>v4</code>",
    "ตรวจชนิดข้อมูลอัตโนมัติ: section เดี่ยว, ทั้งเว็บ (<code>site</code>), zone, หรือ global component",
    "รองรับครบ 16 content section + Header/Footer zone + Global component",
    "จัดระเบียบ HTML ในเนื้อหาอัตโนมัติ (ปิด tag เช่น <code>&lt;br&gt;</code>) และเตือนเมื่อพบ tag ที่ไม่ได้ปิด",
]

# Backend changelog, newest first. Add an entry + bump __version__ whenever
# conversion behavior changes.
CHANGELOG = [
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

HTMLFIX_VERSION = "1.101"
HTMLFIX_LAST_UPDATED = "2026-06-29"

HTMLFIX_CHANGELOG = [
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
      - crossed nesting (`<b><i>x</b></i>`) is left as-is but WARNED — the matched
        open is dropped from the stack so no spurious close is appended
      - genuinely-unclosed tags get their close appended at the end
    """
    fixed: list = []
    warns: list = []
    stack: list = []
    parts: list = []  # rebuilt string, dropping orphan close tags
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
            # crossed nesting — drop the nearest matching open, don't rewrite
            warns.append(f"Improper nesting: </{tag}> closed out of order")
            for i in range(len(stack) - 1, -1, -1):
                if stack[i] == tag:
                    del stack[i]
                    break
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

    # Padding — includes md breakpoint
    padding = section_style.get("padding") or {}
    sm_pad  = padding.get("sm") or {}
    xl_pad  = padding.get("xl") or {}
    md_pad  = padding.get("md") or {}
    pt, pb  = {}, {}
    for src, bp in ((sm_pad, "xs"), (xl_pad, "lg"), (md_pad, "md")):
        if "top"    in src: pt[bp] = parse_size(src["top"])
        if "bottom" in src: pb[bp] = parse_size(src["bottom"])
    if pt: section_info["paddingTop"]    = pt
    if pb: section_info["paddingBottom"] = pb

    # --- Build columns ---
    if bg_media_type == "imageAlignBg" and column == 2:
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
            cols = [
                make_node("col", None, None, content_col_info, _headline_content_widgets(props, include_media=False)),
                make_node("col", None, None, image_col_info,   image_col_children),
            ]
        else:
            # Image col DOM-first (appears left), content col DOM-second (right)
            image_col_info["order"] = {"xs": "1"}
            content_col_info        = {"order": {"xs": "2"}}
            cols = [
                make_node("col", None, None, image_col_info,   image_col_children),
                make_node("col", None, None, content_col_info, _headline_content_widgets(props, include_media=False)),
            ]

    elif column == 2:
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
        if "top"    in src: pt[bp] = parse_size(src["top"])
        if "bottom" in src: pb[bp] = parse_size(src["bottom"])
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

    info = {
        "variant":        "fit-image",
        "features":       features,
        "layoutGridCols": {"lg": lg_cols, "xs": xs_cols},
    }

    if any(obj.get("isCropImage") for obj in feat_objects):
        info["mediaRatio"] = "1 / 1"

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


def _feat_heading_widget(props: dict) -> dict:
    title_style = props.get("titleStyle") or {}
    desc_style  = props.get("descriptionStyle") or {}
    title_text  = props.get("title") or ""
    desc_text   = props.get("description") or ""

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
        if "top"    in src: pt[bp] = parse_size(src["top"])
        if "bottom" in src: pb[bp] = parse_size(src["bottom"])
    if pt: section_info["paddingTop"]    = pt
    if pb: section_info["paddingBottom"] = pb

    heading_widget = _feat_heading_widget(props)
    feature_widget = _feat_list_widget(props)
    button_widget  = _feat_button_widget(props)

    if "direction-column" in class_tokens and "left" in class_tokens:
        col1_children = [heading_widget]
        if button_widget:
            col1_children.append(button_widget)
        col1 = make_node("col", None, None, {"span": {"lg": "4"}}, col1_children)
        col2 = make_node("col", None, None, {"span": {"lg": "8"}}, [feature_widget])
        row  = make_node("row", None, None, {}, [col1, col2])
    else:
        col_children = [heading_widget, feature_widget]
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


def _product_slide_config(props: dict, layout_type: str) -> dict:
    config = {}

    slides_per_view = props.get("productSlidesToShow") or props.get("productBoxNumber") or 5
    config["slidesPerView"] = slides_per_view

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
            config["autoplaySpeed"] = autoplay_speed

    slides_to_scroll = props.get("slidesToScroll")
    if slides_to_scroll is not None:
        config["slidesPerGroup"] = slides_to_scroll

    if layout_type == "imageAlignBg":
        config["arrowsPosition"] = "bottom"
    else:
        arrows_pos = props.get("arrowsPosition") or ""
        if arrows_pos in ("arrowsOutside", "arrowsBottomInside"):
            config["arrowsPosition"] = "bottom"

    slide_speed = props.get("slideSpeed")
    if slide_speed is not None:
        config["speed"] = slide_speed

    return config


def _product_widget_heading(props: dict) -> dict:
    title_text = props.get("title", "")
    desc_text  = props.get("description", "")
    info = {"title": {"text": title_text}}
    if desc_text:
        info["description"] = {"text": desc_text}
    return make_node("widget", "WidgetHeading", None, info)


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


def _product_widget_product_list(props: dict, layout_type: str) -> dict:
    is_slick    = props.get("isUseSlick", False)
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
        "productNumber":  props.get("productNumber") or 0,
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
    layout_type = props.get("layoutType") or "none"
    is_slick    = props.get("isUseSlick", False)

    section_info = {}
    if layout_type == "imageAlignBg":
        section_info["paddingTop"] = {
            "xs": {"value": 70, "unit": "px"},
            "lg": {"value": 100, "unit": "px"},
        }
        section_info["isFullwidth"] = True

    heading      = _product_widget_heading(props)
    product_list = _product_widget_product_list(props, layout_type)
    button       = _product_widget_button(props)

    if layout_type == "none":
        col_widgets = [heading, product_list]
        if button:
            col_widgets.append(button)
        rows = [make_node("row", None, None, {},
                    [make_node("col", None, None, {}, col_widgets)])]

    elif layout_type == "bannerImage":
        media_banner = _product_widget_media_banner(props)
        if not is_slick:
            heading_row = make_node("row", None, None, {},
                [make_node("col", None, None, {}, [heading])])
            banner_col  = make_node("col", None, None,
                {"span": {"lg": "4"}, "verticalAlign": {"lg": "flex-start"}}, [media_banner])
            product_col = make_node("col", None, None,
                {"span": {"lg": "8"}}, [product_list])
            rows = [heading_row, make_node("row", None, None, {}, [banner_col, product_col])]
        else:
            col_widgets = [heading, product_list]
            if button:
                col_widgets.append(button)
            banner_col  = make_node("col", None, None, {}, [media_banner])
            product_col = make_node("col", None, None, {}, col_widgets)
            rows = [make_node("row", None, None, {}, [banner_col, product_col])]

    elif layout_type == "imageAlignBg":
        image_align_config = props.get("imageAlignConfig") or {}
        image_align        = image_align_config.get("imageAlign") or ""
        col_widgets = [heading, product_list]
        if button:
            col_widgets.append(button)
        content_col = make_node("col", None, None, {}, col_widgets)
        bg_col      = make_node("col", None, None, _product_bg_col_info(image_align_config), [])
        cols = [content_col, bg_col] if image_align == "imageRight" else [bg_col, content_col]
        rows = [make_node("row", None, None, {}, cols)]

    else:
        col_widgets = [heading, product_list]
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
    return make_node("section", "Products", nick, {}, [row])


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
    return make_node("section", section_kind, nickname, {}, [row])


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
    return _SYSTEM_FONTS_LOWER[close[0]] if close else None


def _resolve_font_family(names, warnings, path):
    """Resolve a v3 font-name list to canonical system fonts, dropping (and
    warning about) any non-system Google fonts. Returns the kept list."""
    kept, dropped = [], []
    for n in names or []:
        canon = _resolve_system_font(n)
        if canon is not None:
            if canon not in kept:
                kept.append(canon)
        elif isinstance(n, str) and n.strip():
            dropped.append(n.strip())
    if dropped and warnings is not None:
        warnings.append({
            "path": path,
            "kind": "warn",
            "msg": "Google font(s) dropped (not in system list — add manually in v4): "
                   + ", ".join(dropped),
        })
    return kept


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
    root: dict = {}
    if include_colors:
        colors = site_json.get("currentColors") if isinstance(site_json, dict) else None
        colors_emitted = False
        if isinstance(colors, list):
            for i, key in enumerate(_THEME_COLOR_KEYS):
                if i < len(colors) and isinstance(colors[i], str) and colors[i]:
                    root[key] = colors[i].lower()
                    colors_emitted = True
        if colors_emitted and generate_color_scale:
            # Fill the v4 5-step scales from the anchors (does not overwrite a value
            # the user's currentColors provided). Status colors are left to v4.
            _fill_color_scale(root)

    if include_fonts:
        fonts = site_json.get("currentFonts") if isinstance(site_json, dict) else None
        if isinstance(fonts, dict):
            # Skip a font-family key entirely when it resolves to an empty list
            # (e.g. every name was a dropped Google font) — no empty arrays in :root.
            heading = _resolve_font_family(fonts.get("heading"), warnings, "$.currentFonts.heading")
            if heading:
                root["typoHeadingFontFamily"] = heading
            paragraph = _resolve_font_family(fonts.get("text"), warnings, "$.currentFonts.text")
            if paragraph:
                root["typoParagraphFontFamily"] = paragraph
            # Google fonts are dropped (see _resolve_font_family), so the manifest
            # is always empty; the key is still emitted to match the v4 shape.
            info["fontManifest"] = {}
            # v3 base typography metrics — only when they differ from the v4-base
            # default (else redundant). All three currently equal base → omitted.
            for k, v in _V3_BASE_TYPOGRAPHY.items():
                _seed_base(root, k, v)
            # Per-theme text-base overrides (font-size/weight/line-height), keyed
            # by currentTheme — emitted only where they differ from v4-base.
            theme_typo = _THEME_TYPOGRAPHY.get(
                site_json.get("currentTheme") if isinstance(site_json, dict) else None)
            if theme_typo:
                for k, v in theme_typo.items():
                    _seed_base(root, k, v)

    if root:
        # Color keys first, sorted alphabetically; then the rest (fonts/typography)
        # in their existing order.
        color_keys = sorted(k for k in root if k.startswith("color"))
        other_keys = [k for k in root if not k.startswith("color")]
        root = {k: root[k] for k in color_keys + other_keys}
        # :root always sits at the top of style, above any component selectors.
        style = {":root": root, **style}

    free_zone = _build_free_zone(components if include_components else {})

    return {"info": info, "style": style, "free_zone": free_zone}


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
}


def convert_section(old_json: dict) -> dict:
    name    = old_json.get("name", "")
    props   = old_json.get("props", {})
    builder = SECTION_BUILDERS.get(name)
    if not builder:
        raise ValueError(
            f"Unknown section type: '{name}'. "
            "Add a builder function and register it in SECTION_BUILDERS."
        )
    result = builder(props)
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
            converted = convert_section(section)
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


def convert_site(site_json: dict) -> list:
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
        results.append(convert_page(page, path=path))

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
    MODES = {"sections", "page", "pages", "site", "zones", "global"}

    if args and args[0] in MODES:
        mode, args = args[0], args[1:]
    else:
        mode = None  # auto-detect after loading

    if not args:
        print(_USAGE)
        sys.exit(1)

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
        pages  = convert_site(data)
        zones  = convert_zones(data)
        theme_warnings: list = []
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
        result = convert_page(data)
        if output_path:
            _write(result, output_path)
            print(f"✅  Converted page with {_section_count(result)} section(s) → {output_path}")
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # ── sections ───────────────────────────────────────────────────────────
    if isinstance(data, list):
        result = []
        for i, section in enumerate(data):
            try:
                result.append(convert_section(section))
            except ValueError as e:
                print(f"⚠️  Skipping section {i} ({section.get('name', '?')}): {e}")
    else:
        result = convert_section(data)

    if output_path:
        _write(result, output_path)
        count = len(result) if isinstance(result, list) else 1
        print(f"✅  Converted {count} section(s) → {output_path}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()