"""Find search terms in cause-list text and cut out the entry each hit belongs to.

Cause lists are a sequence of numbered entries ("404 ** RSA-4610-2011 ...")
grouped under bench headers ("HON'BLE MR. JUSTICE ..."). For every hit we
return the whole entry plus its bench and court room, so the email shows
the exact listing instead of just a page number.
"""

import re
from bisect import bisect_right
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

from app.managers.cause_list_manager import REGULAR_LIST, pdf_list_type
from app.utils.search_terms import compile_term

# "404 ** RSA-..", "406.1 WITH RSA-..", "501 ***", "218 *", "141 V FARIDKOT", "732 II (ON BAIL)"
ENTRY_START = re.compile(r"^(\d+(?:\.\d+)?)\s+(?:\*{1,3}|WITH|[IVX]{1,4})(?=\s|$)")
# Upper-case only, so notice text like "Hon'ble the Chief Justice has ordered" is skipped.
BENCH_HEADER = re.compile(r"^HON[’']?BLE\s.*\b(?:JUSTICE|BENCH)\b")
LIST_TITLE = re.compile(r"\bDATED\s+\d{1,2}/\d{1,2}/\d{4}")
COURT_ROOM = re.compile(r"\bCR\s*NO\.?\s*(\w+)", re.I)
CASE_NO = re.compile(r"\b[A-Z][A-Z.()]*(?:-[A-Z]+)*-\d+(?:-[A-Z]+)?-\d{4}\b")

MAX_ENTRY_LINES = 30
CONTEXT_LINES = 3
COURT_ROOM_LOOKBACK = 4
# Columns start at fixed x positions; lines inside one column differ by < ~30pt.
COLUMN_GAP = 40
MIN_COLUMNS = 3

# x position of every non-blank line on a 1-based page, in get_text() order.
LineX = Callable[[int], List[float]]


class Line(NamedTuple):
    page: int  # 1-based
    index: int  # position among the page's non-blank lines
    text: str  # whitespace collapsed


class Span(NamedTuple):
    start: int
    end: int  # exclusive
    is_entry: bool  # False: a ±CONTEXT_LINES window outside any entry


@dataclass(frozen=True)
class ListedBench:
    """The bench a case is listed before, as printed in a cause-list PDF."""

    name: str
    source: str
    is_regular_list: bool = False


def find_entries(
    pages: List[str], terms: List[str], line_x: Optional[LineX] = None
) -> Tuple[Dict[str, List[int]], List[Dict[str, Any]]]:
    """({term: [pages]}, [matched rows]) for one cause-list PDF.

    `line_x` is only called for pages holding a matched entry, to split it into
    columns; positions are slower to extract than text, and most pages never need them.
    """
    lines = _clean_lines(pages)
    text = "\n".join(line.text for line in lines)
    line_starts = _line_offsets(lines)

    found_pages: Dict[str, List[int]] = {}
    hits: Dict[Span, List[str]] = {}
    for term in terms:
        pages_hit = set()
        for match in compile_term(term).finditer(text):
            idx = bisect_right(line_starts, match.start()) - 1
            pages_hit.add(lines[idx].page)
            span_terms = hits.setdefault(_span(lines, idx), [])
            if term not in span_terms:
                span_terms.append(term)
        found_pages[term] = sorted(pages_hit)

    columns = _ColumnSplitter(lines, line_x)
    ordered = sorted(hits.items(), key=lambda hit: (-len(hit[1]), hit[0].start))
    rows = [_build_row(lines, span, matched, columns) for span, matched in ordered]
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
                    is_regular_list=pdf_list_type(result["pdf_name"]) == REGULAR_LIST,
                )
    return None


def _clean_lines(pages: List[str]) -> List[Line]:
    lines: List[Line] = []
    for page_no, page in enumerate(pages, start=1):
        texts = [" ".join(raw.split()) for raw in page.split("\n") if raw.strip()]
        lines += [Line(page_no, i, text) for i, text in enumerate(texts)]
    return lines


def _line_offsets(lines: List[Line]) -> List[int]:
    offsets, position = [], 0
    for line in lines:
        offsets.append(position)
        position += len(line.text) + 1
    return offsets


def _is_boundary(text: str) -> bool:
    return bool(BENCH_HEADER.match(text) or LIST_TITLE.search(text))


def _span(lines: List[Line], hit_idx: int) -> Span:
    """The entry holding the hit, or a ±CONTEXT_LINES window outside entries."""
    start = _entry_start(lines, hit_idx)
    if start is None:
        return Span(
            max(0, hit_idx - CONTEXT_LINES),
            min(len(lines), hit_idx + CONTEXT_LINES + 1),
            is_entry=False,
        )
    end = start + 1
    while end < len(lines) and not (
        ENTRY_START.match(lines[end].text) or _is_boundary(lines[end].text)
    ):
        end += 1
    return Span(start, end, is_entry=True)


def _entry_start(lines: List[Line], hit_idx: int) -> Optional[int]:
    for idx in range(hit_idx, -1, -1):
        if ENTRY_START.match(lines[idx].text):
            return idx
        if _is_boundary(lines[idx].text):
            return None
    return None


def _build_row(
    lines: List[Line], span: Span, terms: List[str], columns: "_ColumnSplitter"
) -> Dict[str, Any]:
    entry = lines[span.start : span.end]
    texts = [line.text for line in entry]
    row = {
        "terms": terms,
        "is_entry": span.is_entry,
        "item_no": None,
        "case_no": None,
        "page": entry[0].page,
        "last_page": entry[-1].page,
        "bench": [],
        "court_room": None,
        "columns": None,
        "lines": texts[:MAX_ENTRY_LINES],
        "truncated": len(texts) > MAX_ENTRY_LINES,
    }
    if not span.is_entry:
        return row
    bench, court_room = _bench_for(lines, span.start)
    return {
        **row,
        "item_no": ENTRY_START.match(texts[0]).group(1),
        "case_no": _first_case_no(texts),
        "bench": bench,
        "court_room": court_room,
        "columns": columns.split(entry),
    }


def _first_case_no(texts: List[str]) -> Optional[str]:
    match = CASE_NO.search(re.sub(r"-\n", "-", "\n".join(texts)))
    return match.group(0) if match else None


def _bench_for(lines: List[Line], start: int) -> Tuple[List[str], Optional[str]]:
    """Bench header block above the entry (two lines = division bench) and its CR NO."""
    last = start - 1
    while last >= 0 and not BENCH_HEADER.match(lines[last].text):
        last -= 1
    if last < 0:
        return [], None

    first = last
    while first > 0 and BENCH_HEADER.match(lines[first - 1].text):
        first -= 1
    bench = [line.text for line in lines[first : last + 1]]

    # Joined, because the title often wraps between "CR NO" and the number.
    title_lines = lines[max(0, first - COURT_ROOM_LOOKBACK) : first]
    rooms = COURT_ROOM.findall("\n".join(line.text for line in title_lines))
    if not rooms or rooms[-1].lower() == "none":
        return bench, None
    return bench, rooms[-1]


class _ColumnSplitter:
    """Case / Parties / Advocates cells from line x positions, text as printed.

    Right-most column is Advocates, the one before it Parties, everything left
    of that is the Case column. Positions are fetched once per page, and only
    trusted when their count matches the page's text lines.
    """

    def __init__(self, lines: List[Line], line_x: Optional[LineX]):
        self._line_x = line_x
        self._page_sizes: Dict[int, int] = {}
        for line in lines:
            self._page_sizes[line.page] = line.index + 1
        self._cache: Dict[int, Optional[List[float]]] = {}

    def split(self, entry: List[Line]) -> Optional[Dict[str, List[str]]]:
        xs = [self._x(line) for line in entry]
        if any(x is None for x in xs):
            return None
        distinct = sorted(set(xs))
        starts = [distinct[0]] + [
            b for a, b in zip(distinct, distinct[1:]) if b - a > COLUMN_GAP
        ]
        if len(starts) < MIN_COLUMNS:
            return None
        parties_x, advocates_x = starts[-2], starts[-1]
        cells: Dict[str, List[str]] = {"case": [], "parties": [], "advocates": []}
        for line, x in zip(entry, xs):
            column = (
                "advocates"
                if x >= advocates_x
                else "parties" if x >= parties_x else "case"
            )
            cells[column].append(line.text)
        return cells

    def _x(self, line: Line) -> Optional[float]:
        if self._line_x is None:
            return None
        if line.page not in self._cache:
            xs = self._line_x(line.page)
            self._cache[line.page] = (
                xs if len(xs) == self._page_sizes.get(line.page) else None
            )
        xs = self._cache[line.page]
        return xs[line.index] if xs else None
