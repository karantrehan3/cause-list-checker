"""How a search term matches court text, shared by the PDF and judge-wise searches.

A term with a digit is a case number ("RSA-4610-2011"): matched anywhere, and
lists wrap these at hyphens ("FAO-6127-⏎2026"), so whitespace around hyphens is
allowed. Any other term is a name: matched as whole words, so "Krishan Chand"
does not hit "KRISHAN CHANDER". Names can wrap too ("VISHNU⏎MITTAR").
"""

import re
from typing import Pattern

_HAS_DIGIT = re.compile(r"\d")
_HYPHEN = re.compile(r"\s*-\s*")


def is_case_number(term: str) -> bool:
    return bool(_HAS_DIGIT.search(term))


def compile_term(term: str) -> Pattern[str]:
    if is_case_number(term):
        parts = _HYPHEN.split(term.strip())
        return re.compile(r"\s*-\s*".join(_words(part) for part in parts), re.I)
    return re.compile(rf"(?<!\w){_words(term)}(?!\w)", re.I)


def _words(text: str) -> str:
    return r"\s+".join(re.escape(word) for word in text.split())
