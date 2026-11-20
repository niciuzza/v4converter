#!/usr/bin/env python3
"""Merge v3-converter content into a v4 base JSON, keeping v4's ids.

Why: v4's import/save REJECTS a paste when an existing page's `id` changes or
goes null. The v3→v4 converter intentionally emits no `id`/`ukey` (the target
system assigns them on import), so pasted converter output can't be saved →
theme render-testing is blocked.

This stopgap merges two JSONs into one:
  1. converter output (v3→v4) — has the real v3 *content* but no ids.
  2. a v4 base JSON copied from v4 (a blank slot OR a real shop export) — has the
     real id/ukey v4 needs to accept the save.

Result = the v4 base with v3 content grafted in — either APPENDED (default —
the designer prunes duplicates in the v4 editor) or, for pages/zones that
exist in both, REPLACING the v4 side's content outright — so it saves and
renders either way.

**Separate from the production converter on purpose** — this does NOT import or
modify `converter.py`; it has its own version/changelog and its own web page
(`mergecode.html`). No `__version__` bump, no reuse of the designer converter.

Merge model (v4 = skeleton, v3 = content), controlled by `mode`:
  - Top-level envelope: kept from v4 (slot `id`, `last_revision_id`,
    `nickname`, `unuse_configs`, …), EXCEPT `info` + `style`, which are
    deep-merged with v3's (v3 wins on conflicting keys, with a warning), and
    `theme_key`, which is taken from v3 outright when v3 carries one, and
    `css`, where v3's is appended after the slot's (not twice). All four
    are unaffected by `mode`. The theme goes with the content: `info`/`style`
    are written against whatever theme the conversion targeted, so keeping the
    slot's `theme_key` would pair v3's colours with another theme's defaults.
  - Pages matched by top-level `path`:
      * match in v4, mode="append" (default) → append v3 page's
        `component.children` after v4's (content-deduped); keep v4 page
        id/ukey/metadata + v4 component id/ukey.
      * match in v4, mode="replace" → v4's `component.children` are REPLACED
        wholesale by v3's; v4 page id/ukey/metadata + v4 component id/ukey are
        still kept (that's the whole point — v4 needs them to save).
      * match in v4, mode="migrate" → same as "replace", but first the ENTIRE
        source (`v3`) has every `id`/`ukey` stripped, recursively, at every
        level (page/zone/section/row/col/widget) — see below.
      * v3-only path → append whole v3 page as a NEW page (id/ukey = null),
        same in all modes (nothing in v4 to replace).
      * v4-only path → untouched, same in all modes (nothing in v3 to graft).
  - Zones (header/footer/free) hold content at `children` directly → same
    append/replace/migrate choice as pages, keyed on whether v3 supplies
    content for that zone; v4 zone id/ukey/metadata always kept.
  - Deep child nodes stay null-id in append/replace (only page/zone ids are the
    blocker — the source is assumed to be plain converter output, which never
    has ids to begin with).
  - `mode="migrate"` exists for a DIFFERENT scenario: `v3` isn't converter
    output — it's a real v4 export from ANOTHER shop (e.g. moving content shop
    A → shop B), so every node already carries shop A's real ids. Those ids
    are foreign to shop B and must not leak in, so this mode deep-strips
    `id`/`ukey` from the whole source first (turning it back into id-less
    content, same shape as converter output), then runs "replace": the target
    keeps its own page/zone/component ids wherever paths match, and every bit
    of grafted-in content — matched-page replacements, brand-new pages, zone
    content — ends up null-id, ready for the target to assign on import.

Levels (merge 1.9) — each box may hold a whole site, several pages, one page,
or sections; the level is read from the shape (`_detect_level`) and **the v4
box decides the level of the result**, so what comes out can be pasted back
where the v4 code was copied from. The modes mean the same at every level.
  - v4 = site / pages → v3 may be a site, pages or one page; pages are matched
    by path as above. Sections are refused: there is no page to put them in.
  - v4 = one page → v3 may be sections (merged into it), a page (merged even
    when the paths differ, with a warning — the user paired them), or a
    site/pages (the page with v4's path, or the only one). The page's own id,
    ukey and component id stay v4's.
  - v4 = sections → v3 may be sections or one page (its sections). The result
    is the v4 list with v3's merged in; v4's matched sections keep their ids.

Usage:
    python3 merge_code.py <v3_out.json> <v4_base.json> <merged.json> [--mode=append|replace|migrate]
    python3 merge_code.py <v3_out.json> <v4_base.json> [--mode=append|replace|migrate]   # → stdout
    python3 merge_code.py --clear <v4_export.json> [cleared.json]   # clear_ids only, no v4 base

Clear ids (`clear_ids`, merge 1.9) — one input, no merge: strips what belongs
to the source shop (structural id/ukey, `formId`, `config_id`, revision ids)
so the code can be pasted into another shop. Settings are left alone, `id`s
inside `info` included. Migrate mode runs the same function on its source.
"""
import sys
import json
import collections
import copy
import re

MERGE_VERSION = "1.9"
MERGE_LAST_UPDATED = "2026-11-20"

MERGE_CHANGELOG = [
    {"version": "1.9", "type": "feat", "date": "2026-11-20", "items": [
        "<b>รวมได้ทั้งระดับหน้าและระดับ section</b> — ไม่ต้องเป็นโค้ดทั้งเว็บแล้ว · "
        "เครื่องมือดูเองว่าแต่ละช่องเป็นทั้งเว็บ, หลายหน้า, หน้าเดียว หรือ section",
        "<b>ผลลัพธ์เป็นระดับเดียวกับช่อง v4</b> — คัดลอกหน้ามาจาก v4 ก็ได้หน้ากลับไป วางกลับที่เดิมได้เลย · "
        "หน้าเดียว: ใส่ section หรือหน้าจาก v3 เข้าไป คง id หน้าเดิม · "
        "section: รวมรายการ section สองชุดเข้าด้วยกัน",
        "ทั้งสามโหมด (ต่อท้าย / แทนที่ / ย้ายร้าน) ทำงานเหมือนเดิมในทุกระดับ · "
        "บันทึกการรวมบอกว่าแต่ละช่องอ่านได้เป็นระดับไหน",
        "<b>โหมดใหม่: ล้าง id</b> — ใช้ช่องเดียว ไม่ต้องมีโค้ด v4 · ล้าง id/ukey, <code>formId</code> "
        "และค่าที่ผูกกับร้านเดิม ให้เอาไปวางร้านใหม่ได้ · id หมวดหมู่จริงยังเก็บไว้และบอกในบันทึก",
        "<b>แก้โหมดย้ายร้าน: ตัวกรองสินค้าไม่เสียแล้ว</b> — เดิมลบ <code>id</code> ทุกตัวรวมถึงที่อยู่ในการตั้งค่า "
        "ตัวเลือกจัดเรียง/ช่วงราคาในหน้าหมวดหมู่และหน้าค้นหาจึงไม่มี id · ตอนนี้ลบเฉพาะ id ของโครง",
    ]},
    {"version": "1.8", "type": "fix", "date": "2026-10-19", "items": [
        "<b>โหมดต่อท้าย: section ที่แปลงมาอยู่ตามลำดับเดิม</b> — เดิมเอา section ใหม่ไปต่อท้ายหน้าเสมอ "
        "หัวข้อที่ v3 วางไว้บนสุดของหน้าระบบ (ติดต่อเรา, หมวดสินค้า ฯลฯ) จึงไปอยู่ใต้ส่วนที่ร้านปลายทางมีอยู่แล้ว",
        "ตอนนี้ section ใหม่วางรอบ ๆ section ที่จับคู่กับของร้านปลายทางได้ ตามลำดับในโค้ดที่แปลงมา · "
        "ถ้าไม่มีอันไหนจับคู่ได้ ยังต่อท้ายเหมือนเดิม",
    ]},
    {"version": "1.7", "type": "fix", "date": "2026-10-09", "items": [
        "<b>รวม <code>css</code> ของ site ด้วย</b> — เดิมใช้ของร้านปลายทางอย่างเดียว css ที่ converter ใส่มาจึงหายไป "
        "(เช่นกฎที่ทำให้วิดีโอ YouTube เต็มพื้นหลังบนมือถือ)",
        "css ของร้านปลายทางยังอยู่ครบ ของที่แปลงมาต่อท้าย · ถ้ามีอยู่แล้วจะไม่ใส่ซ้ำ · ทำเหมือนกันทุกโหมด",
    ]},
    {"version": "1.6", "type": "fix", "date": "2026-09-23", "items": [
        "<b>โหมดต่อท้าย: section ที่เป็นอันเดียวกับของร้านปลายทาง จะใช้ของร้านปลายทาง</b> — converter ใส่ section เริ่มต้นของ v4 "
        "มาให้ในทุกหน้าระบบ (ฟอร์มติดต่อ, รายการบล็อก, หน้าสินค้า ฯลฯ) พอเอามารวมจึงซ้ำกับของที่ร้านมีอยู่แล้ว · "
        "เดิมเทียบแบบเนื้อหาตรงกันทุกตัวอักษร ซึ่งไม่มีทางตรงเพราะของร้านมี id จริงอยู่ (เช่น <code>formId</code>) "
        "ฟอร์มติดต่อจึงออกมาสองอัน",
        "ตอนนี้ดูที่<b>โครงสร้าง</b>แทน — ชนิด section เดียวกันและมี widget ชุดเดียวกันเรียงเหมือนกัน ถือว่าเป็น section เดียวกัน "
        "และ<b>เก็บของร้านปลายทางไว้</b> เพราะเป็นตัวที่มี id จริง",
        "จับคู่แบบ <b>หนึ่งต่อหนึ่ง</b> — section ของร้านปลายทาง 1 อันดูดของที่เข้ามาได้แค่ 1 อัน ถ้าร้านมีหลาย section "
        "ที่โครงเหมือนกัน จะไม่ถูกตัดทิ้งยกชุด",
        "โหมดแทนที่และย้ายร้านไม่เกี่ยว — สองโหมดนั้นทิ้งของร้านปลายทางอยู่แล้ว",
    ]},
    {"version": "1.5", "type": "fix", "date": "2026-09-23", "items": [
        "<b>ใช้ธีมจากโค้ดที่แปลงมา ไม่ใช่ธีมของร้านปลายทาง</b> — <code>theme_key</code> เดิมเก็บของร้านปลายทางไว้ "
        "ทั้งที่ <code>info</code>/<code>style</code> ด้านล่างมาจากโค้ดที่แปลงแล้ว ผลคือสีและ token ของ v3 "
        "ไปจับคู่กับค่าเริ่มต้นของธีมอื่น · ตอนนี้ธีมไปพร้อมกับเนื้อหา",
        "ถ้าโค้ดที่แปลงมาไม่ได้ระบุธีม (ว่างหรือไม่มี) จะไม่ไปแตะของร้านปลายทาง",
    ]},
    {"version": "1.4", "type": "feat", "date": "2026-07-16", "items": [
        "เพิ่มโหมด <b>ย้ายร้าน (migrate)</b> — ใช้ตอนย้ายเนื้อหาจาก v4 ร้านหนึ่งไปอีกร้านหนึ่ง (ไม่ใช่โค้ดจาก converter) "
        "เพราะโค้ดต้นทางแบบนี้จะติด id/ukey ของร้านเดิมมาทุกระดับ (page/zone/section/แถว/คอลัมน์/widget) — "
        "โหมดนี้ตัด id/ukey เดิมออกทั้งหมดก่อน แล้วใช้เนื้อหานั้นแทนที่ของร้านปลายทาง โดยยังคง id ของร้านปลายทางไว้ (หน้า/zone ที่จับคู่ path ได้)",
    ]},
    {"version": "1.3", "type": "feat", "date": "2026-07-16", "items": [
        "เพิ่มโหมด <b>แทนที่ (replace)</b> — หน้า/zone ที่มีทั้งใน v3 และ v4 จะใช้เนื้อหาจาก v3 "
        "เท่านั้น (ตัดของ v4 ทิ้ง) แทนการต่อท้าย · หน้าที่มีเฉพาะใน v4 (ไม่มีใน v3) ยังคงอยู่ครบ "
        "ไม่ว่าโหมดไหน · ค่าเริ่มต้นยังเป็น <b>ต่อท้าย (append)</b> เหมือนเดิม",
    ]},
    {"version": "1.2", "type": "feat", "date": "2026-07-13", "items": [
        "รวม top-level <code>info</code> + <code>style</code> ของ v3 เข้ากับ v4 ด้วย (deep merge — <code>:root</code> รวมทีละ key) · key ที่ซ้ำใช้ค่าของ v3 ทับ + ขึ้น warning",
    ]},
    {"version": "1.1", "type": "fix", "date": "2026-07-13", "items": [
        "ไม่ append section/block ที่เนื้อหาซ้ำกับ v4 base แล้ว (เทียบเนื้อหาโดยตัด id/ukey ออก) — กัน section ซ้ำตอนรวม",
    ]},
    {"version": "1.0", "type": "feat", "date": "2026-07-13", "items": [
        "เครื่องมือรวมโค้ดเวอร์ชันแรก — เอาเนื้อหาจาก converter (v3→v4) ยัดลงในโค้ด v4 เดิมโดยคง id/ukey ของ v4 ไว้ (แก้ปัญหา v4 ไม่ยอมบันทึกเมื่อ page id หาย)",
        "จับคู่หน้าด้วย <code>path</code> — หน้าที่มีใน v4 อยู่แล้ว จะเอาเนื้อหา v3 ต่อท้าย (ไม่ทับ), หน้าที่มีเฉพาะใน v3 เพิ่มเป็นหน้าใหม่ (id/ukey = null)",
        "รวมเนื้อหา zone (header/footer/free) จาก v3 ต่อท้าย v4 ด้วย",
    ]},
]

ZONE_KEYS = ("header_zone", "footer_zone", "free_zone")


def _norm_path(p):
    """Normalize a page path for near-miss detection: drop trailing slash,
    lowercase. Root '/' stays '/'."""
    if not isinstance(p, str):
        return p
    s = p.rstrip("/").lower()
    return s or "/"


# Keys whose subtree is a node's SETTINGS, not more nodes. An `id` in there is
# content: a filter's option (`sort`, `newest`, `PRICE_0_500`) or a section's
# anchor (`result-product-list-anchor`). Stripping those broke the category
# and search filters of every page moved in migrate mode (merge 1.9).
_SETTINGS_KEYS = ("info", "style", "_LANG_", "css")


def _strip_ids(node):
    """Deep copy of `node` with the auto-assigned `id`/`ukey` of the
    STRUCTURE removed — site, page, component, zone, section, row, col,
    widget — at every level. Never inside a node's settings (`info`,
    `style`, …): an `id` there is content (see `_SETTINGS_KEYS`)."""
    if isinstance(node, list):
        return [_strip_ids(x) for x in node]
    if isinstance(node, dict):
        return {k: (copy.deepcopy(v) if k in _SETTINGS_KEYS else _strip_ids(v))
                for k, v in node.items() if k not in ("id", "ukey")}
    return node


# A real category id (not v4's `{{PAGE_CATEGORY_ID}}` template) names one row
# of the source shop's catalogue.
_CATALOG_KEYS = ("category_id", "parent_category_id", "coupon_id", "promotion_id")


def clear_ids(data):
    """Make a v4 export safe to paste into ANOTHER shop. Returns (cleared, notes).

    Works at any level (site, pages, page, sections). Removes what belongs to
    the source shop and would be wrong anywhere else:
      - `id`/`ukey` of the structure (`_strip_ids`) — v4 assigns new ones;
      - `formId` in a widget's settings — minted per shop; a foreign one points
        the form at the other shop's form (the converter omits it too);
      - page `config_id` and the site's `last_revision_id` /
        `publish_revision_id` → null.
    Keeps every other setting, including the filter and anchor ids above.
    A real `category_id` & co. is kept but reported: the content is the
    merchant's choice, and only they know which category it maps to here."""
    notes = []
    counts = collections.Counter()
    catalog = []

    def walk(n, settings=False):
        if isinstance(n, list):
            return [walk(x, settings) for x in n]
        if not isinstance(n, dict):
            return n
        out = {}
        for k, v in n.items():
            if not settings and k in ("id", "ukey"):
                if v is not None:
                    counts[k] += 1
                continue
            if settings and k == "formId":
                counts[k] += 1
                continue
            if not settings and k in ("config_id", "last_revision_id", "publish_revision_id"):
                if v is not None:
                    counts[k] += 1
                out[k] = None
                continue
            if settings and k in _CATALOG_KEYS and v not in (None, "") \
                    and not (isinstance(v, str) and v.startswith("{{")):
                catalog.append("%s=%s" % (k, v))
            out[k] = walk(v, settings or k in _SETTINGS_KEYS)
        return out

    cleared = walk(data)
    removed = " · ".join("%s %d" % (k, counts[k]) for k in
                         ("id", "ukey", "formId", "config_id",
                          "last_revision_id", "publish_revision_id") if counts[k])
    notes.append("ล้างค่าของร้านเดิม: %s" % (removed or "ไม่มีให้ล้าง"))
    if counts["formId"]:
        notes.append("ตัด formId ของฟอร์ม %d อัน — ฟอร์มต้องผูกกับร้านใหม่ใน v4 editor"
                     % counts["formId"])
    if catalog:
        shown = ", ".join(catalog[:6]) + (" …" if len(catalog) > 6 else "")
        notes.append("⚠ ยังมี id หมวดหมู่/คูปอง/โปรโมชันของร้านเดิม %d จุด (%s) — "
                     "เก็บไว้ตามเดิม ร้านใหม่ต้องมีหมวดเดียวกัน หรือเลือกใหม่ใน v4 editor"
                     % (len(catalog), shown))
    return cleared, notes


def _content_key(node) -> str:
    """Stable content signature (ids stripped) used to skip appending a v3 section
    whose content already exists in the v4 base."""
    return json.dumps(_strip_ids(node), sort_keys=True, ensure_ascii=False)


def _merge_info_style(v4_obj: dict, v3_obj: dict, warnings: list, path: str):
    """Deep-merge `v3_obj` into `v4_obj` IN PLACE (used for the top-level `info`
    and `style`). Keys only in v3 are added; nested dicts on both sides recurse;
    a leaf that differs is OVERRIDDEN by v3 (with a warning). Keys only in v4 are
    kept. Identical values are left as-is (no warning)."""
    for k, v3v in v3_obj.items():
        sub = "%s.%s" % (path, k)
        if k not in v4_obj:
            v4_obj[k] = copy.deepcopy(v3v)
            continue
        v4v = v4_obj[k]
        if isinstance(v4v, dict) and isinstance(v3v, dict):
            _merge_info_style(v4v, v3v, warnings, sub)
        elif v4v != v3v:
            v4_obj[k] = copy.deepcopy(v3v)
            warnings.append("⚠ %s: ใช้ค่าจาก v3 ทับของ v4 base" % sub)


def _shape_key(node) -> str:
    """A section's shape: its `kind` plus the kinds of every widget inside, in
    order. Two sections with the same shape are the same section as far as the
    merge is concerned, even when their settings differ."""
    kinds = []

    def walk(n):
        if isinstance(n, list):
            for x in n:
                walk(x)
        elif isinstance(n, dict):
            if n.get("type") == "widget":
                kinds.append(n.get("kind"))
            for v in n.values():
                walk(v)

    walk(node)
    return json.dumps([node.get("kind") if isinstance(node, dict) else None, kinds],
                      ensure_ascii=False)


def _append_deduped(kids: list, new_children: list):
    """Add `new_children` to `kids`, skipping duplicates. Returns
    (added, same_content, same_shape).

    A new section keeps its place relative to the ones it matched: those
    before the first match go before that slot section, the rest go after the
    latest match. Only when nothing matches are they simply appended.

    Two passes, both keeping what the v4 slot already has:

    1. **Identical content** (ids stripped) — the original rule.
    2. **The same shape** — same section `kind`, same widget kinds in the same
       order. The converter *prepends v4's own default sections* to every
       system page (`SYSTEM_PAGE_DEFAULTS`), so a converted `/contactus`
       carries a reproduction of the very form the slot already has. Those are
       never byte-identical — the slot's copy has the shop's real `formId`, the
       blog list its own `isShowDate`/`mediaRatio`, the product page fewer tab
       labels — so pass 1 missed all of them and the form came out twice
       (user, 2026-09-23). **The slot's copy wins: it is the one carrying the
       real ids.**

    Shape matching is **one-to-one**: each existing section can absorb at most
    one incoming section. Without that, a page whose v4 side has a single
    `(Standard, [WidgetHeading])` would swallow every heading-only section the
    shop wrote.
    """
    seen = {}                           # content key -> the slot's section
    for c in kids:
        seen.setdefault(_content_key(c), c)
    by_shape = collections.defaultdict(list)   # shape -> slot sections, unconsumed
    for c in kids:
        by_shape[_shape_key(c)].append(c)
    added = same_content = same_shape = 0
    lead, after = [], {}                # new sections before the first match / after a match
    first = prev = None                 # the first slot section matched / the latest
    for c in new_children:
        key = _content_key(c)
        match = seen.get(key)
        if match is not None:
            same_content += 1
        else:
            free = by_shape.get(_shape_key(c))
            if free:
                match = free.pop(0)     # consumed; one-to-one
                same_shape += 1
        if match is not None:
            if match is not True:       # True: a duplicate of a section added here
                prev = match
                if first is None:
                    first = match
            continue
        new = copy.deepcopy(c)
        (lead if prev is None else after.setdefault(id(prev), [])).append(new)
        seen[key] = True
        added += 1
    if prev is None:                    # nothing matched: plain append
        kids.extend(lead)
        return added, same_content, same_shape
    # Matched sections stay where the slot has them; the new ones keep their
    # place around them, as the input ordered them. Appending them all broke
    # the converter's own order: a v3 heading above a system page's built-in
    # part came out under it, because that part is what the slot already has.
    out = []
    for c in kids:
        if c is first:
            out.extend(lead)
        out.append(c)
        out.extend(after.get(id(c), []))
    kids[:] = out
    return added, same_content, same_shape


def _graft(owner: dict, v3_children: list, mode: str, warnings: list,
           label: str, unit: str, kept: str):
    """Put `v3_children` into `owner["children"]` per `mode` — the one step
    every level shares: a page's component, a zone, and the bare container a
    section-level merge builds. `owner` keeps its own id/ukey either way."""
    if mode == "replace":
        old = owner.get("children")
        old_n = len(old) if isinstance(old, list) else 0
        owner["children"] = copy.deepcopy(v3_children)
        warnings.append("%s: แทนที่เนื้อหาเดิม %d %s ด้วย %d %s จาก v3 (คง%s)"
                        % (label, old_n, unit, len(v3_children), unit, kept))
        return
    kids = owner.get("children")
    if not isinstance(kids, list):
        kids = []
        owner["children"] = kids
    added, same_content, same_shape = _append_deduped(kids, v3_children)
    msg = "%s: เพิ่ม %d %s ตามลำดับของ v3 (คง id เดิม)" % (label, added, unit)
    if same_content:
        msg += " · ข้าม %d %s ที่เนื้อหาซ้ำกับ v4" % (same_content, unit)
    if same_shape:
        msg += (" · ข้าม %d %s ที่เป็น %s เดียวกับของ v4 "
                "(โครงเหมือนกัน ตั้งค่าต่างกัน) — ใช้ของ v4 เพราะมี id จริง"
                % (same_shape, unit, unit))
    warnings.append(msg)


# ---------------------------------------------------------------------------
# Levels — what each box holds. The v4 box decides the level of the result.
# ---------------------------------------------------------------------------

LEVEL_NAMES = {"site": "ทั้งเว็บ (site)", "pages": "หลายหน้า (pages)",
               "page": "หน้าเดียว (page)", "sections": "section"}


def _is_page(d) -> bool:
    return isinstance(d, dict) and isinstance(d.get("component"), dict)


def _detect_level(data) -> str:
    """'site' | 'pages' | 'page' | 'sections', from the shape alone.

    - site: an object with `pages` or a zone key (a whole-site export).
    - pages: an array of page objects (each with a `component`).
    - page: one page object (`component` holding the sections), or a bare
      container — a page's `component` or a zone copied on its own
      (`type: "page"` with `children`).
    - sections: one section object, or an array of them (what the converter's
      section mode prints)."""
    if isinstance(data, list):
        if data and all(_is_page(x) for x in data):
            return "pages"
        if all(isinstance(x, dict) for x in data):
            return "sections"
    elif isinstance(data, dict):
        if "pages" in data or any(k in data for k in ZONE_KEYS):
            return "site"
        if _is_page(data):
            return "page"
        if data.get("type") == "page" and isinstance(data.get("children"), list):
            return "page"
        if data.get("type") == "section" or "children" in data or "kind" in data:
            return "sections"
    raise ValueError("ไม่รู้ว่า JSON นี้เป็นระดับไหน — ต้องเป็น site (มี pages/zone), "
                     "page (มี component), หรือ section (type: section)")


def _container(page: dict) -> dict:
    """The dict that holds a page-level value's sections."""
    return page["component"] if _is_page(page) else page


def _pick_page(v3, level: str, path, warnings: list) -> dict:
    """One page out of a site/pages-level source, for a page-level target:
    the one with the target's path, or the only one there is."""
    pages = [p for p in (v3.get("pages") if level == "site" else v3) or [] if _is_page(p)]
    for p in pages:
        if p.get("path") == path:
            return p
    if len(pages) == 1:
        warnings.append("⚠ ใช้หน้า %r จาก v3 (path ไม่ตรงกับ %r ของ v4)"
                        % (pages[0].get("path"), path))
        return pages[0]
    raise ValueError("v3 ไม่มีหน้า path %r ให้รวมเข้าหน้า v4 นี้ — วางเฉพาะหน้านั้นในช่อง v3 แทน"
                     % (path,))


def _merge_page(v3, level: str, result: dict, mode: str, warnings: list):
    """Page-level target: graft into this one page, keeping its ids."""
    owner = _container(result)
    path = result.get("path") if _is_page(result) else None
    label = "หน้า %r" % path if path is not None else "หน้านี้"
    if level == "sections":
        v3_children = v3 if isinstance(v3, list) else [v3]
    else:
        if level in ("site", "pages"):
            v3 = _pick_page(v3, level, path, warnings)
            if level == "site":
                warnings.append("⚠ v3 เป็นทั้งเว็บ แต่ v4 เป็นหน้าเดียว — ใช้แค่หน้านั้น "
                                "(info/style/css/zone ของ v3 ไม่ได้รวม)")
        elif _is_page(v3) and path is not None and v3.get("path") not in (None, path):
            warnings.append("⚠ path ไม่ตรงกัน: v3 %r · v4 %r — รวมเข้าหน้าของ v4 ตามที่วาง"
                            % (v3.get("path"), path))
        v3_children = _container(v3).get("children") or []
    if not v3_children:
        warnings.append("%s: v3 ไม่มีเนื้อหาให้เพิ่ม (ข้าม)" % label)
        return
    _graft(owner, v3_children, mode, warnings, label, "section", "id หน้าเดิม")


def _merge_sections(v3, level: str, v4, mode: str, warnings: list):
    """Section-level target: the result is the v4 section list with v3's
    sections merged in. A single v4 section stays a single object only when
    the merge leaves exactly one."""
    if level == "sections":
        v3_children = v3 if isinstance(v3, list) else [v3]
    elif level == "page":
        v3_children = _container(v3).get("children") or []
    else:
        raise ValueError("v4 เป็น section แต่ v3 เป็น%s — ไม่รู้ว่าจะเอาหน้าไหน "
                         "วาง section (หรือหน้าเดียว) ในช่อง v3 แทน" % LEVEL_NAMES[level])
    box = {"children": copy.deepcopy(v4) if isinstance(v4, list) else [copy.deepcopy(v4)]}
    _graft(box, v3_children, mode, warnings, "section", "section", " id ของ v4 ที่ใช้ซ้ำ")
    out = box["children"]
    if isinstance(v4, dict) and len(out) == 1:
        return out[0]
    if isinstance(v4, dict):
        warnings.append("ผลลัพธ์มี %d section — ออกมาเป็น array" % len(out))
    return out


def merge_v3_into_v4(v3: dict, v4: dict, mode: str = "append"):
    """Graft v3 content onto a deep copy of the v4 base. Returns (merged, warnings).

    v4 is the skeleton (all ids/envelope kept); v3 supplies content.
    `mode`:
      - "append" (default) — v3 content is appended after v4's existing
        content, deduped two ways: identical content (ids stripped), and the
        same SHAPE (same section kind + same widget kinds in order). The slot's
        copy wins both times, because it is the one carrying the real ids.
        Shape matching is one-to-one.
      - "replace" — for any page/zone that exists in BOTH v3 and v4, v4's
        existing children are discarded and replaced with v3's. Pages/zones
        that only exist in v4 (not in v3) are left untouched either way —
        there's nothing in v3 to replace them with.
      - "migrate" — for shop-to-shop content migration, where `v3` is itself a
        real v4 export (another shop's site JSON) and therefore carries THAT
        shop's real id/ukey on every node. Those ids are foreign to the target
        and must not leak in, so this strips id/ukey from the entire source
        first (recursively, every level), then behaves exactly like "replace".
    Never mutates the inputs.
    """
    if mode not in ("append", "replace", "migrate"):
        raise ValueError("mode must be 'append', 'replace', or 'migrate', got %r" % (mode,))
    warnings = []
    if mode == "migrate":
        v3, notes = clear_ids(v3)
        mode = "replace"
        warnings.append("โหมดย้ายร้าน: ตัด id/ukey เดิมของโค้ดต้นทางออกทั้งหมดก่อนรวม "
                        "(ทุกระดับ — page/zone/section/แถว/คอลัมน์/widget)")
        warnings.extend(notes)
    v3_level, v4_level = _detect_level(v3), _detect_level(v4)
    warnings.append("ระดับ: v3 = %s · v4 = %s → ผลลัพธ์เป็น%s"
                    % (LEVEL_NAMES[v3_level], LEVEL_NAMES[v4_level], LEVEL_NAMES[v4_level]))
    if v4_level == "sections":
        return _merge_sections(v3, v3_level, v4, mode, warnings), warnings
    result = copy.deepcopy(v4)
    if v4_level == "page":
        _merge_page(v3, v3_level, result, mode, warnings)
        return result, warnings
    if v4_level == "pages":
        site = {"pages": result}
        _merge_site(_as_site(v3, v3_level, v4_level), site, mode, warnings)
        dropped = [k for k in ("theme_key", "info", "style", "css") + ZONE_KEYS
                   if k in site and site[k] not in (None, "", {}, [])]
        if dropped:
            warnings.append("⚠ v4 เป็นหลายหน้า — %s ของ v3 ไม่ได้รวม" % "/".join(dropped))
        return site["pages"], warnings
    _merge_site(_as_site(v3, v3_level, v4_level), result, mode, warnings)
    return result, warnings


def _as_site(v3, level: str, target: str) -> dict:
    """A page- or pages-level source, as a site holding only those pages;
    pages are matched by `path` exactly as in a whole-site merge."""
    if level == "site":
        return v3
    if level == "pages":
        return {"pages": v3}
    if level == "page" and _is_page(v3):
        return {"pages": [v3]}
    raise ValueError("v4 เป็น%s แต่ v3 เป็น%s — ไม่รู้ว่าจะใส่หน้าไหน "
                     "วางหน้าปลายทางหน้าเดียวในช่อง v4 แทน"
                     % (LEVEL_NAMES[target],
                        " section" if level == "sections" else "หน้าที่ไม่มี path"))


def _merge_site(v3: dict, result: dict, mode: str, warnings: list):
    """Site- (or pages-) level target, edited in place: envelope, pages by
    path, zones."""
    # ---- theme_key: take the converted v3's, not the v4 slot's ------------
    # The rest of the envelope stays v4's, but the theme is the one thing the
    # CONTENT depends on: `info` and `style` below are merged from v3 with v3
    # winning, and those are written against whatever theme the conversion
    # targeted. Leaving the slot's `theme_key` in place pairs v3's colours and
    # tokens with a different theme's defaults (user, 2026-09-23).
    #
    # Only when v3 actually carries one -- an empty or missing key is not a
    # theme choice, and must not wipe the slot's.
    v3_theme = v3.get("theme_key")
    if isinstance(v3_theme, str) and v3_theme.strip():
        v4_theme = result.get("theme_key")
        result["theme_key"] = v3_theme
        if v4_theme != v3_theme:
            warnings.append("⚠ theme_key: ใช้ “%s” จากโค้ดที่แปลงมา แทน “%s” ของร้านปลายทาง "
                            "— เพราะ info/style ด้านล่างก็มาจากโค้ดที่แปลงเหมือนกัน "
                            "ถ้าคงธีมเดิมไว้ สีกับ token จะไม่เข้ากัน"
                            % (v3_theme, v4_theme))

    # ---- Top-level info + style: merge v3's parent settings in (v3 wins) ----
    for key in ("info", "style"):
        v3_obj = v3.get(key)
        if not isinstance(v3_obj, dict) or not v3_obj:
            continue
        v4_obj = result.get(key)
        if isinstance(v4_obj, dict):
            _merge_info_style(v4_obj, v3_obj, warnings, key)
        else:
            result[key] = copy.deepcopy(v3_obj)

    # ---- Top-level css: add v3's after the slot's ---------------------------
    # The converter puts here the rules its content needs and v4 does not ship
    # (the YouTube background class, converter 1.78) -- leaving it behind
    # breaks that content. The slot's own CSS is the shop's, so it is kept and
    # v3's goes after it. Same in every mode, like info/style. Text already in
    # the slot's CSS is not added twice, so merging again is harmless.
    v3_css = v3.get("css")
    if isinstance(v3_css, str) and v3_css.strip():
        v4_css = result.get("css")
        if not isinstance(v4_css, str) or not v4_css.strip():
            result["css"] = v3_css
        elif v3_css.strip() not in v4_css:
            result["css"] = v4_css.rstrip() + "\n\n" + v3_css
            warnings.append("css: ต่อ css จากโค้ดที่แปลงมาไว้ท้าย css เดิมของร้านปลายทาง")

    # ---- Pages: index v4 by path, then graft/append per v3 page -------------
    v4_pages = result.get("pages")
    if not isinstance(v4_pages, list):
        v4_pages = []
        result["pages"] = v4_pages

    index = {}          # path -> v4 page (first occurrence wins)
    norm_index = {}     # normalized path -> real v4 path
    for pg in v4_pages:
        if not isinstance(pg, dict):
            continue
        path = pg.get("path")
        if path in index:
            warnings.append("⚠ v4 มี path ซ้ำ: %r (ใช้หน้าแรก)" % path)
            continue
        index[path] = pg
        norm_index.setdefault(_norm_path(path), path)

    seen_v3_paths = set()
    for pg in (v3.get("pages") or []):
        if not isinstance(pg, dict):
            continue
        path = pg.get("path")
        if path in seen_v3_paths:
            warnings.append("⚠ v3 มีหลายหน้า path ซ้ำ: %r (รวมต่อท้ายทั้งหมด)" % path)
        seen_v3_paths.add(path)

        v3_children = ((pg.get("component") or {}).get("children")) or []

        if path in index:
            # matched → keep v4 page ids/component, graft v3 content in per `mode`
            if not v3_children:
                warnings.append("หน้า %r: v3 ไม่มีเนื้อหาให้เพิ่ม (ข้าม)" % path)
                continue
            v4pg = index[path]
            if not isinstance(v4pg.get("component"), dict):
                # v4 page has no component wrapper — take v3's whole component
                v4pg["component"] = copy.deepcopy(pg.get("component") or {"children": []})
                warnings.append("⚠ หน้า %r ใน v4 ไม่มี component — ใช้ของ v3 แทน" % path)
            else:
                _graft(v4pg["component"], v3_children, mode, warnings,
                       "หน้า %r" % path, "section", "id หน้าเดิม")
        else:
            # v3-only → append as a NEW page (id/ukey = null)
            near = norm_index.get(_norm_path(path))
            if near is not None and near != path:
                warnings.append("⚠ หน้า %r คล้ายกับ %r ใน v4 — เพิ่มเป็นหน้าใหม่ (path ไม่ตรงเป๊ะ)"
                                % (path, near))
            new_pg = copy.deepcopy(pg)
            new_pg.setdefault("id", None)
            new_pg.setdefault("ukey", None)
            v4_pages.append(new_pg)
            warnings.append("หน้าใหม่ %r: เพิ่มเข้า v4 (id/ukey = null)" % path)

    # ---- Zones: append v3 zone children after v4's --------------------------
    for zk in ZONE_KEYS:
        v3zone = v3.get(zk)
        v3_zchildren = (v3zone or {}).get("children") or []
        if not v3_zchildren:
            continue
        v4zone = result.get(zk)
        if isinstance(v4zone, dict):
            _graft(v4zone, v3_zchildren, mode, warnings, zk, "block", "id zone เดิม")
        else:
            result[zk] = copy.deepcopy(v3zone)
            warnings.append("⚠ v4 ไม่มี %s — คัดลอกจาก v3 (id/ukey = null)" % zk)


# ---------------------------------------------------------------------------
# Text wrappers (Pyodide + CLI)
# ---------------------------------------------------------------------------

def _lenient_loads(text: str):
    """Parse JSON text; also accept bare comma-separated objects + [..] stubs
    (mirrors converter._load_json)."""
    raw = re.sub(r'\[\s*\.\.\s*\]', '[]', text.strip())
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return json.loads("[%s]" % raw)


def merge_text(v3_text: str, v4_text: str, mode: str = "append"):
    """String → string wrapper for the web page. Returns (out_text, warnings)."""
    v3 = _lenient_loads(v3_text)
    v4 = _lenient_loads(v4_text)
    merged, warnings = merge_v3_into_v4(v3, v4, mode=mode)
    out_text = json.dumps(merged, indent=2, ensure_ascii=False)
    return out_text, warnings


def main(argv) -> int:
    if argv[:1] == ["--clear"] and len(argv) >= 2:
        data = _lenient_loads(open(argv[1], encoding="utf-8").read())
        cleared, notes = clear_ids(data)
        out_text = json.dumps(cleared, indent=2, ensure_ascii=False)
        if len(argv) > 2:
            with open(argv[2], "w", encoding="utf-8") as f:
                f.write(out_text)
        else:
            sys.stdout.write(out_text)
        for w in notes:
            print(w, file=sys.stderr)
        return 0
    if not argv or argv[0] in ("-h", "--help") or len(argv) < 2:
        print(__doc__)
        return 0 if argv[:1] in (["-h"], ["--help"]) else 1
    mode = "append"
    positional = []
    for a in argv:
        if a.startswith("--mode="):
            mode = a.split("=", 1)[1]
        else:
            positional.append(a)
    if len(positional) < 2:
        print(__doc__)
        return 1
    v3 = _lenient_loads(open(positional[0], encoding="utf-8").read())
    v4 = _lenient_loads(open(positional[1], encoding="utf-8").read())
    try:
        merged, warnings = merge_v3_into_v4(v3, v4, mode=mode)
    except ValueError as e:
        print("❌  %s" % e, file=sys.stderr)
        return 1
    out_text = json.dumps(merged, indent=2, ensure_ascii=False)
    if len(positional) > 2:
        with open(positional[2], "w", encoding="utf-8") as f:
            f.write(out_text)
        dest = positional[2]
    else:
        sys.stdout.write(out_text)
        dest = "(stdout)"
    for w in warnings:
        print(w, file=sys.stderr)
    print("✅  Merged %s + %s → %s  [mode=%s]  (%d ข้อความ)" % (positional[0], positional[1], dest, mode, len(warnings)),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
