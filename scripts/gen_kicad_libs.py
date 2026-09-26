#!/usr/bin/env python3
"""
Build KiCad symbol libraries for the LHRS standard parts list.

Pulls the parts database from Notion (API version 2025-09-03), writes it to a
CSV, then splits the rows by their "Component" column and generates one symbol
library per component class from a hand-made template library:

    Component = Resistors   ->  lhrs_resistors_template.kicad_sym
                                    -> lhrs_resistors.kicad_sym
    Component = Capacitors  ->  lhrs_capacitors_template.kicad_sym
                                    -> lhrs_capacitors.kicad_sym

Every other component class in the database is ignored for now (adding one is
a matter of appending an entry to COMPONENT_CLASSES below).

Each template library holds two symbols -- e.g. "R_TEMPLATE" and
"R_Small_TEMPLATE" -- which define the graphics, pins and field placement.
Each database row becomes a clone of both, named R_<value>[_<special>] and
R_<value>[_<special>]_Small (C_... for capacitors), with Value, Footprint,
P/N, LCSC P/N and Datasheet filled in.  The optional Special column is a free
text tag appended to the symbol name, so two parts that share a value can
coexist: a 100 V 100 nF part with Special = "100V" becomes C_100n_100V.  Template files are only ever read; output
libraries are regenerated from scratch on every run.

Usage:
    export NOTION_TOKEN="ntn_..."
    python3 gen_kicad_libs.py <database_id_or_url>
    python3 gen_kicad_libs.py <database_id_or_url> --out-dir ~/kicad/libraries
    python3 gen_kicad_libs.py <database_id_or_url> --save-csv parts.csv
    python3 gen_kicad_libs.py --csv parts.csv                # skip the fetch
    python3 gen_kicad_libs.py --csv parts.csv --only resistor --dry-run

The fetched database is held in memory and discarded when the run ends; pass
--save-csv to keep a copy, then --csv to replay it later without the network.

Templates are looked for beside this script, then in the current directory;
--template-dir and --out-dir override either end, so the libraries can live in
a KiCad project or a shared library folder well away from the script.  Setting
DEFAULT_OUT_DIR below makes that permanent.

Fetching from Notion needs `pip install requests`; working from a CSV does not.

Database columns (matched case-insensitively, aliases accepted):
    Component    Resistors / Capacitors / ...   (selects the library)
    Resistance   the value: 0, 10, 1k, 4k7, 0.1u, 90p, 22u, 0.1uF
    Package      0402 / 0603 / 0805 / 1206 ... or a full "Lib:Footprint"
                 (hand-solder footprints by default; --reflow-footprints for
                 the plain IPC land patterns)
    Mfg. P/N     -> "P/N" field
    LCSC P/N     -> "LCSC P/N" field
    Datasheet    -> "Datasheet" field (optional)
    Special      free text appended to the symbol name, e.g. 100V, X7R (optional)
Anything else (JLC Type, Notes, ...) is carried through the CSV but unused.

Note on SI prefixes: parsing is case-sensitive where it matters -- "m" is
milli, "M" is mega.  "k"/"K" and "r"/"R" are interchangeable.
"""

from __future__ import annotations

import argparse
import copy
import csv
import math
import os
import re
import sys
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

TEMPLATE_SUFFIX = "_TEMPLATE"          # symbols ending in this are templates

# Where templates are read from and libraries are written, when no flag says
# otherwise.  Set DEFAULT_OUT_DIR to a path (e.g. "~/kicad/libraries" or
# "$HOME/projects/lhrs/lib") to send generated libraries somewhere else every
# run without typing --out-dir.  None means "beside the templates".
DEFAULT_TEMPLATE_DIR = None            # None -> next to this script, else the cwd
DEFAULT_OUT_DIR = None                 # None -> same directory as the template
SIG_FIGS = 6

# SI prefixes used when formatting.  "u" instead of "µ" keeps names ASCII.
ENG_PREFIXES = {-12: "p", -9: "n", -6: "u", -3: "m", 0: "", 3: "k", 6: "M", 9: "G"}

# Metric package code -> imperial, for CSVs that say e.g. "1608Metric".
METRIC_TO_IMPERIAL = {
    "0603": "0201", "1005": "0402", "1608": "0603", "2012": "0805",
    "3216": "1206", "3225": "1210", "3246": "1218", "4532": "1812",
    "5025": "2010", "5650": "2220", "6332": "2512",
}

# Imperial code -> (reflow footprint, hand-solder footprint).  Hand-solder
# variants have elongated pads; names are those of the official KiCad
# footprint libraries (kicad.github.io/footprints, checked September 2026).
RESISTOR_FOOTPRINTS = {
    "0201": ("R_0201_0603Metric", "R_0201_0603Metric_Pad0.64x0.40mm_HandSolder"),
    "0402": ("R_0402_1005Metric", "R_0402_1005Metric_Pad0.72x0.64mm_HandSolder"),
    "0603": ("R_0603_1608Metric", "R_0603_1608Metric_Pad0.98x0.95mm_HandSolder"),
    "0805": ("R_0805_2012Metric", "R_0805_2012Metric_Pad1.20x1.40mm_HandSolder"),
    "1206": ("R_1206_3216Metric", "R_1206_3216Metric_Pad1.30x1.75mm_HandSolder"),
    "1210": ("R_1210_3225Metric", "R_1210_3225Metric_Pad1.30x2.65mm_HandSolder"),
    "1218": ("R_1218_3246Metric", "R_1218_3246Metric_Pad1.22x4.75mm_HandSolder"),
    "1812": ("R_1812_4532Metric", "R_1812_4532Metric_Pad1.30x3.40mm_HandSolder"),
    "2010": ("R_2010_5025Metric", "R_2010_5025Metric_Pad1.40x2.65mm_HandSolder"),
    "2512": ("R_2512_6332Metric", "R_2512_6332Metric_Pad1.40x3.35mm_HandSolder"),
}

CAPACITOR_FOOTPRINTS = {
    "0201": ("C_0201_0603Metric", "C_0201_0603Metric_Pad0.64x0.40mm_HandSolder"),
    "0402": ("C_0402_1005Metric", "C_0402_1005Metric_Pad0.74x0.62mm_HandSolder"),
    "0603": ("C_0603_1608Metric", "C_0603_1608Metric_Pad1.08x0.95mm_HandSolder"),
    "0805": ("C_0805_2012Metric", "C_0805_2012Metric_Pad1.18x1.45mm_HandSolder"),
    "1206": ("C_1206_3216Metric", "C_1206_3216Metric_Pad1.33x1.80mm_HandSolder"),
    "1210": ("C_1210_3225Metric", "C_1210_3225Metric_Pad1.33x2.70mm_HandSolder"),
    "1812": ("C_1812_4532Metric", "C_1812_4532Metric_Pad1.57x3.40mm_HandSolder"),
    "2220": ("C_2220_5650Metric", "C_2220_5650Metric_Pad1.97x5.40mm_HandSolder"),
}


@dataclass(frozen=True)
class ComponentClass:
    key: str                 # --only name
    label: str               # human-readable plural
    ref: str                 # "R" / "C", also the symbol-name prefix
    template_file: str
    templates: tuple         # (full-size template symbol, small template symbol)
    footprint_lib: str
    footprints: dict
    aliases: frozenset       # accepted values of the Component column
    unit_re: str             # unit words stripped while parsing ("ohm", "F", ...)
    unit_display: str        # appended after the value in Description
    noun: str                # used in Description
    value_suffix: str = ""   # appended to the Value field, e.g. "F" for caps
    bare_number_ok: bool = True   # False -> warn when a value has no SI prefix
    keywords: tuple = ()

    @property
    def name_patterns(self):
        return ((self.templates[0], self.ref + "_{stem}"),
                (self.templates[1], self.ref + "_{stem}_Small"))


COMPONENT_CLASSES = [
    ComponentClass(
        key="resistor", label="Resistors", ref="R",
        template_file="lhrs_resistors_template.kicad_sym",
        templates=("R_TEMPLATE", "R_Small_TEMPLATE"),
        footprint_lib="Resistor_SMD", footprints=RESISTOR_FOOTPRINTS,
        aliases=frozenset({"resistor", "resistors", "res", "r"}),
        unit_re=r"ohms?|Ω|ω", unit_display=" ohm", noun="resistor",
        keywords=("R", "res", "resistor"),
    ),
    ComponentClass(
        key="capacitor", label="Capacitors", ref="C",
        template_file="lhrs_capacitors_template.kicad_sym",
        templates=("C_TEMPLATE", "C_Small_TEMPLATE"),
        footprint_lib="Capacitor_SMD", footprints=CAPACITOR_FOOTPRINTS,
        aliases=frozenset({"capacitor", "capacitors", "cap", "caps", "c"}),
        unit_re=r"farads?|f", unit_display="F", noun="capacitor",
        # set value_suffix="F" if you would rather see "100nF" in the Value field
        value_suffix="", bare_number_ok=False,
        keywords=("C", "cap", "capacitor"),
    ),
]

# Column header aliases (lower-cased, punctuation stripped).
COLUMN_ALIASES = {
    "component": ("component", "component type", "type", "category", "class"),
    "value": ("resistance", "capacitance", "value", "ohms", "farads", "name"),
    "package": ("package", "size", "case", "package size"),
    "mpn": ("mfg pn", "mfg part number", "mpn", "manufacturer part number",
            "part number", "pn", "mfr pn"),
    "lcsc": ("lcsc pn", "lcsc", "lcsc part number", "lcsc part"),
    "datasheet": ("datasheet", "data sheet", "datasheet url"),
    "special": ("special", "variant", "suffix", "special suffix"),
}

# --------------------------------------------------------------------------
# Notion export (API version 2025-09-03)
# --------------------------------------------------------------------------

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2025-09-03"


def _notion_session(token: str):
    try:
        import requests
    except ImportError:
        raise SystemExit(
            "error: fetching from Notion needs the requests package\n"
            "       pip install requests   (or use --csv to work from a file)"
        )
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    })
    return session


def _notion_request(session, method: str, path: str, **kwargs):
    """Call the API, retrying politely on rate limits (HTTP 429)."""
    while True:
        response = session.request(method, f"{NOTION_API}{path}", timeout=30, **kwargs)
        if response.status_code == 429:
            time.sleep(float(response.headers.get("Retry-After", 1)))
            continue
        if not response.ok:
            raise SystemExit(f"error: Notion API {response.status_code}: {response.text}")
        return response.json()


def extract_database_id(value: str) -> str:
    """Accept a raw ID or a full Notion URL and return the 32-char ID."""
    match = re.search(r"([0-9a-f]{32})", value.replace("-", ""))
    if not match:
        raise SystemExit(f"error: couldn't find a database ID in: {value}")
    return match.group(1)


def _plain_text(rich) -> str:
    return "".join(part.get("plain_text", "") for part in rich or [])


def format_notion_value(prop) -> str:
    """Flatten a Notion property value into a CSV cell."""
    t = prop.get("type")
    v = prop.get(t)
    if v is None:
        return ""
    if t in ("title", "rich_text"):
        return _plain_text(v)
    if t in ("number", "checkbox", "url", "email", "phone_number",
             "created_time", "last_edited_time"):
        return str(v)
    if t in ("select", "status"):
        return v.get("name", "")
    if t == "multi_select":
        return ", ".join(o["name"] for o in v)
    if t == "date":
        return f"{v['start']} - {v['end']}" if v.get("end") else v.get("start", "")
    if t == "people":
        return ", ".join(p.get("name") or p.get("id", "") for p in v)
    if t in ("created_by", "last_edited_by"):
        return v.get("name") or v.get("id", "")
    if t == "relation":
        return ", ".join(r["id"] for r in v)
    if t == "files":
        return ", ".join(f.get("name", "") for f in v)
    if t == "unique_id":
        prefix = v.get("prefix") or ""
        return f"{prefix}{'-' if prefix else ''}{v.get('number')}"
    if t == "formula":
        return format_notion_value(v)
    if t == "rollup":
        if v.get("type") == "array":
            return ", ".join(format_notion_value(item) for item in v["array"])
        return format_notion_value(v)
    return str(v)


def fetch_notion_rows(database_ref: str, token: str):
    """Return (columns, rows) for the first data source of a Notion database."""
    session = _notion_session(token)
    database_id = extract_database_id(database_ref)

    # A database is a container; its rows live in one or more data sources.
    database = _notion_request(session, "GET", f"/databases/{database_id}")
    sources = database.get("data_sources", [])
    if not sources:
        raise SystemExit(
            "error: no data sources found -- is the database shared with your integration?"
        )
    if len(sources) > 1:
        print(f"note: database has {len(sources)} data sources; "
              f"using the first ({sources[0].get('name')})")
    source_id = sources[0]["id"]

    schema = _notion_request(session, "GET", f"/data_sources/{source_id}")["properties"]
    columns = sorted(schema, key=lambda name: schema[name]["type"] != "title")

    rows, cursor = [], None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data = _notion_request(session, "POST", f"/data_sources/{source_id}/query", json=body)
        for page in data["results"]:
            props = page.get("properties", {})
            rows.append({c: format_notion_value(props[c]) if c in props else ""
                         for c in columns})
        if not data.get("has_more"):
            break
        cursor = data["next_cursor"]
    return columns, rows


def write_csv(path: Path, columns, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


# --------------------------------------------------------------------------
# Minimal s-expression reader / writer for .kicad_sym files
# --------------------------------------------------------------------------

class Bare(str):
    """An unquoted s-expression atom (e.g. `yes`, `1.27`, `property`)."""
    __slots__ = ()


def parse_sexpr(text: str):
    """Parse a .kicad_sym file into nested lists.

    Quoted strings come back as plain `str`, bare atoms as `Bare`, so the
    writer can reproduce the original quoting.
    """
    pos, n = 0, len(text)

    def skip_ws():
        nonlocal pos
        while pos < n and text[pos] in " \t\r\n":
            pos += 1

    def parse_node():
        nonlocal pos
        skip_ws()
        if pos >= n:
            raise ValueError("unexpected end of file")
        ch = text[pos]
        if ch == "(":
            pos += 1
            items = []
            while True:
                skip_ws()
                if pos >= n:
                    raise ValueError("unterminated list")
                if text[pos] == ")":
                    pos += 1
                    return items
                items.append(parse_node())
        if ch == ")":
            raise ValueError(f"unexpected ')' at offset {pos}")
        if ch == '"':
            pos += 1
            out = []
            while pos < n:
                c = text[pos]
                if c == "\\":
                    pos += 1
                    out.append({"n": "\n", "t": "\t", "r": "\r"}.get(text[pos], text[pos]))
                    pos += 1
                elif c == '"':
                    pos += 1
                    return "".join(out)
                else:
                    out.append(c)
                    pos += 1
            raise ValueError("unterminated string")
        start = pos
        while pos < n and text[pos] not in ' \t\r\n()"':
            pos += 1
        return Bare(text[start:pos])

    node = parse_node()
    skip_ws()
    if pos != n:
        raise ValueError("trailing data after top-level expression")
    return node


def _quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _atom(node) -> str:
    return str(node) if isinstance(node, Bare) else _quote(node)


def write_sexpr(node, indent: int = 0) -> str:
    """Render nested lists back out in KiCad's own formatting style."""
    tab = "\t" * indent
    if not isinstance(node, list):
        return tab + _atom(node)

    head, i = [], 0
    while i < len(node) and not isinstance(node[i], list):
        head.append(_atom(node[i]))
        i += 1
    children = node[i:]
    opener = f"{tab}({' '.join(head)}" if head else f"{tab}("
    if not children:
        return opener + ")"
    # KiCad keeps the coordinate pairs of a (pts ...) node on one line.
    if head and head[0] == "pts":
        inner = " ".join(write_sexpr(c).strip() for c in children)
        return f"{opener}\n{tab}\t{inner}\n{tab})"
    body = "\n".join(write_sexpr(c, indent + 1) for c in children)
    return f"{opener}\n{body}\n{tab})"


# --- helpers for working with the parsed tree -----------------------------

def is_node(node, name: str) -> bool:
    return isinstance(node, list) and node and isinstance(node[0], Bare) and node[0] == name


def symbol_name(sym) -> str:
    return sym[1] if len(sym) > 1 and isinstance(sym[1], str) else ""


def find_property(sym, key: str):
    for child in sym:
        if is_node(child, "property") and len(child) > 1 and child[1] == key:
            return child
    return None


def get_property(sym, key: str, default: str = "") -> str:
    prop = find_property(sym, key)
    return prop[2] if prop is not None and len(prop) > 2 else default


def set_property(sym, key: str, value: str) -> None:
    """Set a property's value, creating a hidden property if it is missing."""
    prop = find_property(sym, key)
    if prop is not None:
        prop[2] = value
        return
    new = [
        Bare("property"), key, value,
        [Bare("at"), Bare("0"), Bare("0"), Bare("0")],
        [Bare("show_name"), Bare("no")],
        [Bare("do_not_autoplace"), Bare("no")],
        [Bare("hide"), Bare("yes")],
        [Bare("effects"), [Bare("font"), [Bare("size"), Bare("1.27"), Bare("1.27")]]],
    ]
    last = max((i for i, c in enumerate(sym) if is_node(c, "property")), default=len(sym) - 1)
    sym.insert(last + 1, new)


# --------------------------------------------------------------------------
# Value parsing / formatting
# --------------------------------------------------------------------------

_MULTIPLIERS = {
    "p": -12, "P": -12,
    "n": -9, "N": -9,
    "u": -6, "U": -6, "µ": -6, "μ": -6,
    "m": -3,                       # milli (lower case only)
    "r": 0, "R": 0, "e": 0, "E": 0,
    "k": 3, "K": 3,
    "M": 6,                        # mega (upper case only)
    "g": 9, "G": 9,
}
_PREFIX_CHARS = "".join(sorted(set(_MULTIPLIERS)))
_RKM_RE = re.compile(rf"^(\d+)([{_PREFIX_CHARS}])(\d+)$")
_PLAIN_RE = re.compile(rf"^(\d+(?:\.\d+)?|\.\d+)\s*([{_PREFIX_CHARS}])?$")
_NOISE_RE = re.compile(r"\b(cap|caps|capacitor|resistor|res|smd|ceramic|mlcc)\b",
                       re.IGNORECASE)


class ParseError(ValueError):
    pass


def parse_value(raw: str, comp: ComponentClass) -> tuple[Decimal, bool]:
    """Parse '1k', '4k7', '10R', '0.1u', '90p', '0.1uF cap' -> (magnitude, had_prefix)."""
    s = raw.strip().replace(",", "").replace("\u00a0", " ")
    s = _NOISE_RE.sub("", s)
    s = re.sub(rf"\s*({comp.unit_re})\s*$", "", s, flags=re.IGNORECASE).strip()
    if not s:
        raise ParseError(f"no value in {raw!r}")

    m = _RKM_RE.match(s)                       # 4k7, 1R5, 4u7
    if m:
        whole, prefix, frac = m.groups()
        try:
            mant = Decimal(f"{whole}.{frac}")
        except InvalidOperation:
            raise ParseError(f"cannot parse {raw!r}")
        return mant.scaleb(_MULTIPLIERS[prefix]), True

    m = _PLAIN_RE.match(s)                     # 1k, 0.1u, 470, 22
    if m:
        number, prefix = m.groups()
        try:
            mant = Decimal(number)
        except InvalidOperation:
            raise ParseError(f"cannot parse {raw!r}")
        if prefix:
            return mant.scaleb(_MULTIPLIERS[prefix]), True
        return mant, False

    raise ParseError(f"cannot parse value {raw!r}")


def _round_sig(d: Decimal, sig: int) -> Decimal:
    if d == 0:
        return Decimal(0)
    return d.quantize(Decimal(1).scaleb(d.adjusted() - sig + 1), rounding=ROUND_HALF_UP)


def format_eng(magnitude: Decimal) -> str:
    """Engineering notation: 0, 4.7, 470, 1k, 1.5k, 1M, 100n, 22u, 90p."""
    if magnitude == 0:
        return "0"
    if magnitude < 0:
        raise ParseError("negative value")
    magnitude = _round_sig(magnitude, SIG_FIGS)
    group = math.floor(magnitude.adjusted() / 3) * 3
    group = max(min(group, max(ENG_PREFIXES)), min(ENG_PREFIXES))
    mant = _round_sig(magnitude.scaleb(-group), SIG_FIGS).normalize()
    if mant == mant.to_integral_value():
        mant = mant.to_integral_value()
    return f"{mant:f}{ENG_PREFIXES[group]}"


def resolve_footprint(package: str, comp: ComponentClass,
                      hand_solder: bool = True) -> tuple[str, str | None]:
    """Return (footprint, warning).  Accepts '0603', '1608Metric', 'Lib:FP'."""
    pkg = package.strip()
    if not pkg:
        return "", "no package given"
    if ":" in pkg:
        return pkg, None
    key = re.sub(r"[^0-9a-z]", "", pkg.lower())
    if key.endswith("metric"):
        stripped = key[: -len("metric")]
        key = METRIC_TO_IMPERIAL.get(stripped, stripped)
    if key[:1] in ("r", "c") and key[1:].isdigit():
        key = key[1:]
    if key.isdigit():
        key = key.zfill(4)
    if key in comp.footprints:
        reflow, handsolder = comp.footprints[key]
        return f"{comp.footprint_lib}:{handsolder if hand_solder else reflow}", None
    return "", f"unknown package {package!r} (footprint left blank)"


# --------------------------------------------------------------------------
# Row -> part
# --------------------------------------------------------------------------

_SPECIAL_BAD_RE = re.compile(r"""[\s:/\\'"(){}\[\]<>?*|=,;`]+""")


def sanitize_special(raw: str) -> str:
    """Make the Special tag safe to paste into a KiCad symbol name.

    Only characters KiCad dislikes in a symbol name -- whitespace, the library
    separator and shell/path punctuation -- are replaced, each run becoming one
    underscore: "100 V" -> "100_V", "X7R / 50V" -> "X7R_50V".  Tags like
    "0.1%", "±1%" or "AEC-Q200" survive intact.
    """
    return _SPECIAL_BAD_RE.sub("_", raw.strip()).strip("_")


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (h or "").strip().lower()).strip()


def map_columns(fieldnames) -> dict:
    normalized = {_norm_header(f): f for f in fieldnames or []}
    found = {}
    for key, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                found[key] = normalized[alias]
                break
    return found


def classify(row, cols, classes):
    """Return the ComponentClass for a row, or None."""
    raw = (row.get(cols.get("component", ""), "") or "").strip().lower()
    for comp in classes:
        if raw in comp.aliases:
            return comp
    return None


def collect_parts(rows, cols, comp: ComponentClass, warn, hand_solder=True):
    """Turn the rows of one component class into sorted part dicts."""
    parts, seen = [], {}
    for lineno, row in rows:
        raw_value = (row.get(cols.get("value", ""), "") or "").strip()
        package = (row.get(cols.get("package", ""), "") or "").strip()
        mpn = (row.get(cols.get("mpn", ""), "") or "").strip()
        lcsc = (row.get(cols.get("lcsc", ""), "") or "").strip()
        datasheet = (row.get(cols.get("datasheet", ""), "") or "").strip()
        raw_special = (row.get(cols.get("special", ""), "") or "").strip()

        if not mpn and not lcsc:
            warn(f"row {lineno}: {raw_value or '(blank)'} has no part numbers, skipped")
            continue
        try:
            magnitude, had_prefix = parse_value(raw_value, comp)
            value = format_eng(magnitude)
        except ParseError as exc:
            warn(f"row {lineno}: {exc}, skipped")
            continue
        if not had_prefix and not comp.bare_number_ok and magnitude != 0:
            warn(f"row {lineno}: {raw_value!r} has no SI prefix, reading it as "
                 f"{value} farads -- write e.g. '{raw_value}p' if that is wrong")

        footprint, footprint_warning = resolve_footprint(package, comp, hand_solder)
        if footprint_warning:
            warn(f"row {lineno} ({value}): {footprint_warning}")

        special = sanitize_special(raw_special)
        if raw_special and special != raw_special:
            warn(f"row {lineno} ({value}): Special {raw_special!r} is not usable in a "
                 f"symbol name, using {special!r}")
        stem = f"{value}_{special}" if special else value

        if stem in seen:
            warn(f"row {lineno}: duplicate symbol {comp.ref}_{stem} "
                 f"(already taken by row {seen[stem]}), skipped -- give one of them a "
                 f"Special value to keep both")
            continue
        seen[stem] = lineno

        parts.append({
            "magnitude": magnitude, "value": value, "special": special,
            "stem": stem, "package": package, "footprint": footprint,
            "mpn": mpn, "lcsc": lcsc, "datasheet": datasheet,
        })
    parts.sort(key=lambda p: (p["magnitude"], p["special"]))
    return parts


# --------------------------------------------------------------------------
# Symbol generation
# --------------------------------------------------------------------------

def make_symbol(template, new_name: str, part: dict, comp: ComponentClass, small: bool):
    sym = copy.deepcopy(template)
    old_name = symbol_name(template)
    sym[1] = new_name

    # Sub-units are named "<symbol>_0_1" / "<symbol>_1_1" and must follow.
    for child in sym:
        if is_node(child, "symbol") and len(child) > 1 and isinstance(child[1], str):
            if child[1].startswith(old_name):
                child[1] = new_name + child[1][len(old_name):]

    description = f"{part['value']}{comp.unit_display} {comp.noun}"
    if part["package"]:
        description += f", {part['package']}"
    if part["special"]:
        description += f", {part['special']}"
    if small:
        description += ", small symbol"

    set_property(sym, "Reference", comp.ref)
    set_property(sym, "Value", part["value"] + comp.value_suffix)
    set_property(sym, "Footprint", part["footprint"])
    set_property(sym, "Description", description)
    set_property(sym, "P/N", part["mpn"])
    set_property(sym, "LCSC P/N", part["lcsc"])
    if part["datasheet"]:
        set_property(sym, "Datasheet", part["datasheet"])

    words = get_property(sym, "ki_keywords", " ".join(comp.keywords)).split()
    words += [w for w in (part["value"], part["special"], part["package"],
                          part["lcsc"]) if w]
    seen, ordered = set(), []
    for w in words:
        if w not in seen:
            seen.add(w)
            ordered.append(w)
    set_property(sym, "ki_keywords", " ".join(ordered))
    return sym


def build_library(lib_tree, parts, comp: ComponentClass, keep_templates=False):
    if not is_node(lib_tree, "kicad_symbol_lib"):
        raise SystemExit("error: file does not look like a .kicad_sym library")

    symbols = {symbol_name(c): c for c in lib_tree if is_node(c, "symbol")}
    templates = []
    for template_name, pattern in comp.name_patterns:
        if template_name not in symbols:
            raise SystemExit(
                f"error: template symbol {template_name!r} not found in "
                f"{comp.template_file}\n"
                f"       symbols present: {', '.join(symbols) or '(none)'}"
            )
        templates.append((symbols[template_name], pattern))

    header = [c for c in lib_tree if not is_node(c, "symbol")]
    kept = []
    if keep_templates:
        kept = [c for c in lib_tree if is_node(c, "symbol")
                and symbol_name(c).endswith(TEMPLATE_SUFFIX)]

    generated = []
    for part in parts:
        for template, pattern in templates:
            new_name = pattern.format(stem=part["stem"])
            small = new_name.endswith("_Small")
            generated.append(make_symbol(template, new_name, part, comp, small))

    return header + kept + generated, len(kept), len(generated)


def expand_path(value) -> Path:
    """Expand ~ and $VARS so --out-dir ~/kicad/libs behaves as typed."""
    return Path(os.path.expanduser(os.path.expandvars(str(value))))


def find_template(directory: Path, filename: str):
    """The template in `directory`, matched exactly or ignoring case."""
    exact = directory / filename
    if exact.is_file():
        return exact
    try:
        entries = list(directory.iterdir())
    except OSError:
        return None
    wanted = filename.lower()
    for entry in entries:
        if entry.is_file() and entry.name.lower() == wanted:
            return entry
    return None


def default_template_dir(classes) -> Path:
    """Look beside the script first, then in the current directory.

    Whichever holds more of the templates wins, so a checkout where the script
    and the templates sit together behaves the same as one where the script is
    installed elsewhere and you run it from the library folder.
    """
    if DEFAULT_TEMPLATE_DIR:
        return expand_path(DEFAULT_TEMPLATE_DIR)
    here = Path(__file__).resolve().parent
    cwd = Path.cwd()

    def found(directory):
        return sum(find_template(directory, c.template_file) is not None
                   for c in classes)

    return cwd if found(cwd) > found(here) else here


def default_output(template_path: Path) -> Path:
    """lhrs_resistors_template.kicad_sym -> lhrs_resistors.kicad_sym"""
    stem = template_path.stem
    for suffix in ("_Template", "_template", "_TEMPLATE", "-template", "-Template"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    else:
        stem += "_Generated"
    return template_path.with_name(stem + template_path.suffix)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def generate_library(comp, rows, cols, args) -> bool:
    """Build one library.  Returns True if a file was written."""
    template_path = find_template(args.template_dir, comp.template_file)
    print(f"\n{comp.label}: {len(rows)} row(s)")
    if template_path is None:
        print(f"  skipped: no {comp.template_file} in {args.template_dir}",
              file=sys.stderr)
        return False

    def warn(message):
        print(f"  {message}", file=sys.stderr)

    parts = collect_parts(rows, cols, comp, warn, not args.reflow_footprints)
    if not parts:
        print("  skipped: no usable rows", file=sys.stderr)
        return False

    out_name = default_output(Path(comp.template_file)).name
    target = (args.out_dir or template_path.parent) / out_name
    if target.resolve() == template_path.resolve():
        raise SystemExit(f"error: output would overwrite the template ({target})")

    try:
        lib_tree = parse_sexpr(template_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(f"error: could not parse {template_path}: {exc}")

    new_tree, n_kept, n_new = build_library(lib_tree, parts, comp, args.keep_templates)
    text = write_sexpr(new_tree) + "\n"

    for part in parts:
        print(f"  {comp.ref + '_' + part['stem']:<16} "
              f"{part['footprint'] or '(no footprint)':<34} "
              f"{part['mpn']:<22} {part['lcsc']}")
    kept_note = f", {n_kept} template symbol(s) copied" if n_kept else ""
    print(f"  {len(parts)} values -> {n_new} symbols{kept_note}")

    if args.dry_run:
        print(f"  dry run: would write {target}")
        return False

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)
    print(f"  wrote {target}  (template {template_path.name} unchanged)")
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Pull the LHRS parts database from Notion and generate "
                    "KiCad symbol libraries.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Template libraries are read-only; output libraries are regenerated.",
    )
    ap.add_argument("database", nargs="?",
                    help="Notion database ID or URL (omit when using --csv)")
    ap.add_argument("--token", default=os.environ.get("NOTION_TOKEN"),
                    help="Notion integration token (default: $NOTION_TOKEN)")
    ap.add_argument("--csv", type=expand_path,
                    help="read this CSV instead of fetching from Notion")
    ap.add_argument("--save-csv", type=expand_path, nargs="?", metavar="FILE",
                    const=Path("notion_export.csv"),
                    help="keep the fetched database as a CSV; the fetch is "
                         "discarded after the run unless this is given "
                         "(bare flag saves notion_export.csv)")
    ap.add_argument("--template-dir", type=expand_path,
                    help="directory holding the *_template.kicad_sym files "
                         "(default: beside this script, else the current directory)")
    ap.add_argument("--out-dir", type=expand_path,
                    help="directory for the generated libraries "
                         "(default: alongside the templates)")
    ap.add_argument("--only", action="append", metavar="CLASS",
                    choices=[c.key for c in COMPONENT_CLASSES],
                    help="build only this component class (repeatable): "
                         + ", ".join(c.key for c in COMPONENT_CLASSES))
    ap.add_argument("--reflow-footprints", action="store_true",
                    help="use the plain IPC footprints instead of the "
                         "hand-solder variants with elongated pads")
    ap.add_argument("--keep-templates", action="store_true",
                    help="also copy the *_TEMPLATE symbols into the output libraries")
    ap.add_argument("-n", "--dry-run", action="store_true",
                    help="report what would be generated, write nothing")
    args = ap.parse_args(argv)

    if bool(args.database) == bool(args.csv):
        raise SystemExit("error: give either a Notion database ID/URL or --csv FILE")

    # 1. Get the rows, from Notion or from a previous export.
    if args.csv:
        if not args.csv.is_file():
            raise SystemExit(f"error: no such CSV: {args.csv}")
        columns, rows = read_csv(args.csv)
        print(f"read {len(rows)} rows from {args.csv}")
    else:
        if not args.token:
            raise SystemExit("error: set NOTION_TOKEN or pass --token")
        columns, rows = fetch_notion_rows(args.database, args.token)
        print(f"fetched {len(rows)} rows from Notion")
        if args.save_csv and not args.dry_run:
            write_csv(args.save_csv, columns, rows)
            print(f"saved {args.save_csv}")

    cols = map_columns(columns)
    missing = [k for k in ("value", "package") if k not in cols]
    if missing:
        raise SystemExit(
            f"error: database is missing required column(s): {', '.join(missing)}\n"
            f"       columns found: {', '.join(columns)}"
        )

    classes = [c for c in COMPONENT_CLASSES if not args.only or c.key in args.only]
    if args.template_dir is None:
        args.template_dir = default_template_dir(classes)
    if args.out_dir is None and DEFAULT_OUT_DIR:
        args.out_dir = expand_path(DEFAULT_OUT_DIR)

    # 2. Split the rows by component class.
    buckets = {c.key: [] for c in classes}
    other = {}
    if "component" not in cols:
        if len(classes) == 1:
            print("note: no Component column; treating every row as "
                  f"{classes[0].label.lower()}")
            buckets[classes[0].key] = list(enumerate(rows, start=2))
        else:
            raise SystemExit(
                "error: no Component column found, so rows cannot be split by type\n"
                "       pass --only resistor (or --only capacitor) to build one library"
            )
    else:
        for lineno, row in enumerate(rows, start=2):
            comp = classify(row, cols, classes)
            if comp:
                buckets[comp.key].append((lineno, row))
            else:
                label = (row.get(cols["component"], "") or "(blank)").strip() or "(blank)"
                other[label] = other.get(label, 0) + 1
        if other:
            print("ignored: " + ", ".join(f"{k} x{v}" for k, v in sorted(other.items())))

    # 3. Generate one library per class.
    written = 0
    for comp in classes:
        written += generate_library(comp, buckets[comp.key], cols, args)

    if not written and not args.dry_run:
        raise SystemExit("\nerror: nothing was written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
