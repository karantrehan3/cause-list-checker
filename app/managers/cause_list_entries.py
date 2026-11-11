"""Find search terms in cause-list text and cut out the entry each hit belongs to.

Cause lists are a sequence of numbered entries ("404 ** RSA-4610-2011 ...")
grouped under bench headers ("HON'BLE MR. JUSTICE ..."). For every hit we
return the whole entry plus its bench and court room, so the email shows
the exact listing instead of just a page number.
"""

import re
from bisect import bisect_right
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

# "404 ** RSA-..", "406.1 WITH RSA-..", "501 ***", "218 *", "141 V FARIDKOT", "732 II (ON BAIL)"
ENTRY_START = re.compile(r"^(\d+(?:\.\d+)?)\s+(?:\*{1,3}|WITH|[IVX]{1,4})(?=\s|$)")
# Upper-case only, so notice text like "Hon'ble the Chief Justice has ordered" is skipped.
BENCH_HEADER = re.compile(r"^HON[’']?BLE\s.*\b(?:JUSTICE|BENCH)\b")
LIST_TITLE = re.compile(r"\bDATED\s+\d{1,2}/\d{1,2}/\d{4}")
COURT_ROOM = re.compile(r"\bCR\s*NO\.?\s*(\w+)", re.I)
CASE_NO = re.compile(r"\b[A-Z][A-Z.()]*(?:-[A-Z]+)*-\d+(?:-[A-Z]+)?-\d{4}\b")
HAS_DIGIT = re.compile(r"\d")

MAX_ENTRY_LINES = 30
CONTEXT_LINES = 3
COURT_ROOM_LOOKBACK = 4
# Columns start at fixed x positions; lines inside one column differ by < ~30pt.
COLUMN_GAP = 40
MIN_COLUMNS = 3

# A page is plain text, or (x, text) per line in PDF reading order.
Page = Union[str, Sequence[Tuple[float, str]]]
Line = Tuple[int, str, Optional[float]]  # (1-based page, collapsed text, x or None)


@dataclass(frozen=True)
class ListedBench:
    """The bench a case is listed before, as printed in a cause-list PDF."""

    name: str
    source: str
    is_regular_list: bool = False


def compile_term(term: str) -> "re.Pattern[str]":
    """Case numbers (any digit) match as substrings; names match whole words.

    Words may be split across lines in the PDF, so any whitespace run matches.
    """
    if HAS_DIGIT.search(term):
        # Lists wrap case numbers at hyphens ("FAO-6127-⏎2026", "WITH FAO-⏎6130-2026").
        parts = re.split(r"\s*-\s*", term.strip())
        body = r"\s*-\s*".join(
            r"\s+".join(re.escape(word) for word in part.split()) for part in parts
        )
        return re.compile(body, re.I)
    body = r"\s+".join(re.escape(word) for word in term.split())
    return re.compile(rf"(?<!\w){body}(?!\w)", re.I)


def find_entries(
    pages: List[Page], terms: List[str]
) -> Tuple[Dict[str, List[int]], List[Dict[str, Any]]]:
    """Return ({term: [pages]}, [matched rows]) for one cause-list PDF."""
    lines = _clean_lines(pages)
    text = "\n".join(line for _, line, _ in lines)
    line_starts = _line_offsets(lines)

    found_pages: Dict[str, List[int]] = {}
    hits: Dict[Tuple[int, int], set] = {}
    for term in terms:
        pages = set()
        for match in compile_term(term).finditer(text):
            line_idx = bisect_right(line_starts, match.start()) - 1
            pages.add(lines[line_idx][0])
            hits.setdefault(_row_span(lines, line_idx), set()).add(term)
        found_pages[term] = sorted(pages)

    rows = [
        _build_row(lines, span, [t for t in terms if t in matched])
        for span, matched in hits.items()
    ]
    rows.sort(key=lambda row: (-len(row["terms"]), row["_start"]))
    for row in rows:
        del row["_start"]
    return found_pages, rows


def listed_bench_for_case(
    results: List[Dict[str, Any]], case_id: str
) -> Optional[ListedBench]:
    """Bench of the first matched entry whose case number is `case_id`."""
    for result in results:
        for row in result.get("matches", []):
            same_case = (row.get("case_no") or "").upper() == case_id.upper()
            if row.get("is_entry") and same_case and row.get("bench"):
                return ListedBench(
                    name=row["bench"][0],
                    source=f"{result['pdf_name']}, item {row['item_no']}, p. {row['page']}",
                    is_regular_list=result["pdf_name"].lower().startswith("regular"),
                )
    return None


def _clean_lines(pages: List[Page]) -> List[Line]:
    lines: List[Line] = []
    for page_no, page in enumerate(pages, start=1):
        raw_lines = (
            [(None, raw) for raw in page.split("\n")] if isinstance(page, str) else page
        )
        lines += [
            (page_no, " ".join(raw.split()), x) for x, raw in raw_lines if raw.strip()
        ]
    return lines


def _line_offsets(lines: List[Line]) -> List[int]:
    offsets, position = [], 0
    for _, line, _ in lines:
        offsets.append(position)
        position += len(line) + 1
    return offsets


def _is_boundary(line: str) -> bool:
    return bool(BENCH_HEADER.match(line) or LIST_TITLE.search(line))


def _row_span(lines: List[Line], hit_idx: int) -> Tuple[int, int]:
    """[start, end) of the entry holding the hit, or a ±3-line window outside entries."""
    start = _entry_start(lines, hit_idx)
    if start is None:
        return (
            max(0, hit_idx - CONTEXT_LINES),
            min(len(lines), hit_idx + CONTEXT_LINES + 1),
        )
    end = start + 1
    while end < len(lines):
        line = lines[end][1]
        if ENTRY_START.match(line) or _is_boundary(line):
            break
        end += 1
    return start, end


def _entry_start(lines: List[Line], hit_idx: int) -> Optional[int]:
    for idx in range(hit_idx, -1, -1):
        line = lines[idx][1]
        if ENTRY_START.match(line):
            return idx
        if _is_boundary(line):
            return None
    return None


def _build_row(
    lines: List[Line], span: Tuple[int, int], terms: List[str]
) -> Dict[str, Any]:
    start, end = span
    entry_match = ENTRY_START.match(lines[start][1])
    is_entry = bool(entry_match) and _row_span(lines, start) == span
    row_lines = [line for _, line, _ in lines[start:end]]
    bench, court_room = _bench_for(lines, start) if is_entry else ([], None)
    return {
        "terms": terms,
        "is_entry": is_entry,
        "item_no": entry_match.group(1) if is_entry else None,
        "case_no": _first_case_no(row_lines) if is_entry else None,
        "page": lines[start][0],
        "last_page": lines[end - 1][0],
        "bench": bench,
        "court_room": court_room,
        "columns": _split_columns(lines[start:end]) if is_entry else None,
        "lines": row_lines[:MAX_ENTRY_LINES],
        "truncated": len(row_lines) > MAX_ENTRY_LINES,
        "_start": start,
    }


def _first_case_no(row_lines: List[str]) -> Optional[str]:
    joined = re.sub(r"-\n", "-", "\n".join(row_lines))
    match = CASE_NO.search(joined)
    return match.group(0) if match else None


def _bench_for(lines: List[Line], start: int) -> Tuple[List[str], Optional[str]]:
    """Bench header block above the entry (two lines = division bench) and its CR NO."""
    idx = start - 1
    while idx >= 0 and not BENCH_HEADER.match(lines[idx][1]):
        idx -= 1
    if idx < 0:
        return [], None

    first = idx
    while first > 0 and BENCH_HEADER.match(lines[first - 1][1]):
        first -= 1
    bench = [line for _, line, _ in lines[first : idx + 1]]

    # Joined, because the title often wraps between "CR NO" and the number.
    title = "\n".join(
        line for _, line, _ in lines[max(0, first - COURT_ROOM_LOOKBACK) : first]
    )
    rooms = COURT_ROOM.findall(title)
    if not rooms or rooms[-1].lower() == "none":
        return bench, None
    return bench, rooms[-1]


def _split_columns(entry: List[Line]) -> Optional[Dict[str, List[str]]]:
    """Case / Parties / Advocates cells, each line printed as-is.

    Columns are found from the lines' x positions: right-most is Advocates,
    the one before it Parties, everything left of that is the Case column.
    """
    if any(x is None for _, _, x in entry):
        return None  # plain-text input has no positions
    xs = sorted({x for _, _, x in entry})
    starts = [xs[0]] + [b for a, b in zip(xs, xs[1:]) if b - a > COLUMN_GAP]
    if len(starts) < MIN_COLUMNS:
        return None
    parties_x, advocates_x = starts[-2], starts[-1]
    cells: Dict[str, List[str]] = {"case": [], "parties": [], "advocates": []}
    for _, line, x in entry:
        key = (
            "advocates" if x >= advocates_x else "parties" if x >= parties_x else "case"
        )
        cells[key].append(line)
    return cells
