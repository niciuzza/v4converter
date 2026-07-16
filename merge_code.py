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
  - Top-level envelope: kept from v4 (slot `id`, `last_revision_id`, `theme_key`,
    `nickname`, `css`, `unuse_configs`, …), EXCEPT `info` + `style` which are
    deep-merged with v3's (v3 wins on conflicting keys, with a warning) —
    unaffected by `mode`.
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

Usage:
    python3 merge_code.py <v3_out.json> <v4_base.json> <merged.json> [--mode=append|replace|migrate]
    python3 merge_code.py <v3_out.json> <v4_base.json> [--mode=append|replace|migrate]   # → stdout
"""
import sys
import json
import copy
import re

MERGE_VERSION = "1.4"
MERGE_LAST_UPDATED = "2026-07-16"

MERGE_CHANGELOG = [
    {"version": "1.4", "date": "2026-07-16", "items": [
        "เพิ่มโหมด <b>ย้ายร้าน (migrate)</b> — ใช้ตอนย้ายเนื้อหาจาก v4 ร้านหนึ่งไปอีกร้านหนึ่ง (ไม่ใช่โค้ดจาก converter) "
        "เพราะโค้ดต้นทางแบบนี้จะติด id/ukey ของร้านเดิมมาทุกระดับ (page/zone/section/แถว/คอลัมน์/widget) — "
        "โหมดนี้ตัด id/ukey เดิมออกทั้งหมดก่อน แล้วใช้เนื้อหานั้นแทนที่ของร้านปลายทาง โดยยังคง id ของร้านปลายทางไว้ (หน้า/zone ที่จับคู่ path ได้)",
    ]},
    {"version": "1.3", "date": "2026-07-16", "items": [
        "เพิ่มโหมด <b>แทนที่ (replace)</b> — หน้า/zone ที่มีทั้งใน v3 และ v4 จะใช้เนื้อหาจาก v3 "
        "เท่านั้น (ตัดของ v4 ทิ้ง) แทนการต่อท้าย · หน้าที่มีเฉพาะใน v4 (ไม่มีใน v3) ยังคงอยู่ครบ "
        "ไม่ว่าโหมดไหน · ค่าเริ่มต้นยังเป็น <b>ต่อท้าย (append)</b> เหมือนเดิม",
    ]},
    {"version": "1.2", "date": "2026-07-13", "items": [
        "รวม top-level <code>info</code> + <code>style</code> ของ v3 เข้ากับ v4 ด้วย (deep merge — <code>:root</code> รวมทีละ key) · key ที่ซ้ำใช้ค่าของ v3 ทับ + ขึ้น warning",
    ]},
    {"version": "1.1", "date": "2026-07-13", "items": [
        "ไม่ append section/block ที่เนื้อหาซ้ำกับ v4 base แล้ว (เทียบเนื้อหาโดยตัด id/ukey ออก) — กัน section ซ้ำตอนรวม",
    ]},
    {"version": "1.0", "date": "2026-07-13", "items": [
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


def _strip_ids(node):
    """Deep copy of `node` with auto-assigned `id`/`ukey` removed at every level,
    so two nodes can be compared by CONTENT (v4 base carries ids, the converter
    output does not — a raw compare would never match)."""
    if isinstance(node, list):
        return [_strip_ids(x) for x in node]
    if isinstance(node, dict):
        return {k: _strip_ids(v) for k, v in node.items() if k not in ("id", "ukey")}
    return node


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


def _append_deduped(kids: list, new_children: list):
    """Append `new_children` onto `kids`, skipping any whose content already
    exists in `kids` (compared ids-stripped). Returns (added, skipped)."""
    seen = {_content_key(c) for c in kids}
    added = skipped = 0
    for c in new_children:
        key = _content_key(c)
        if key in seen:
            skipped += 1
            continue
        kids.append(copy.deepcopy(c))
        seen.add(key)
        added += 1
    return added, skipped


def merge_v3_into_v4(v3: dict, v4: dict, mode: str = "append"):
    """Graft v3 content onto a deep copy of the v4 base. Returns (merged, warnings).

    v4 is the skeleton (all ids/envelope kept); v3 supplies content.
    `mode`:
      - "append" (default) — v3 content is appended after v4's existing
        content, content-deduped (matches historical behavior).
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
        v3 = _strip_ids(v3)
        mode = "replace"
        warnings.append("โหมดย้ายร้าน: ตัด id/ukey เดิมของโค้ดต้นทางออกทั้งหมดก่อนรวม "
                        "(ทุกระดับ — page/zone/section/แถว/คอลัมน์/widget)")
    result = copy.deepcopy(v4)

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
            v4comp = v4pg.get("component")
            if not isinstance(v4comp, dict):
                # v4 page has no component wrapper — take v3's whole component
                v4pg["component"] = copy.deepcopy(pg.get("component") or {"children": []})
                warnings.append("⚠ หน้า %r ใน v4 ไม่มี component — ใช้ของ v3 แทน" % path)
            elif mode == "replace":
                old_n = len(v4comp.get("children") or [])
                v4comp["children"] = copy.deepcopy(v3_children)
                warnings.append("หน้า %r: แทนที่เนื้อหาเดิม %d section ด้วย %d section จาก v3 (คง id หน้าเดิม)"
                                % (path, old_n, len(v3_children)))
            else:
                kids = v4comp.get("children")
                if not isinstance(kids, list):
                    kids = []
                    v4comp["children"] = kids
                added, skipped = _append_deduped(kids, v3_children)
                msg = "หน้า %r: เพิ่ม %d section ต่อท้าย (คง id เดิม)" % (path, added)
                if skipped:
                    msg += " · ข้าม %d section ที่เนื้อหาซ้ำกับ v4" % skipped
                warnings.append(msg)
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
            if mode == "replace":
                old_kids = v4zone.get("children")
                old_n = len(old_kids) if isinstance(old_kids, list) else 0
                v4zone["children"] = copy.deepcopy(v3_zchildren)
                warnings.append("%s: แทนที่เนื้อหาเดิม %d block ด้วย %d block จาก v3 (คง id zone เดิม)"
                                % (zk, old_n, len(v3_zchildren)))
            else:
                kids = v4zone.get("children")
                if not isinstance(kids, list):
                    kids = []
                    v4zone["children"] = kids
                added, skipped = _append_deduped(kids, v3_zchildren)
                msg = "%s: เพิ่ม %d block ต่อท้าย (คง id เดิม)" % (zk, added)
                if skipped:
                    msg += " · ข้าม %d block ที่เนื้อหาซ้ำกับ v4" % skipped
                warnings.append(msg)
        else:
            result[zk] = copy.deepcopy(v3zone)
            warnings.append("⚠ v4 ไม่มี %s — คัดลอกจาก v3 (id/ukey = null)" % zk)

    return result, warnings


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
    merged, warnings = merge_v3_into_v4(v3, v4, mode=mode)
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
