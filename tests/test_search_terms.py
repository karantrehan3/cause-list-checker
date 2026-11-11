import pytest

from app.utils.search_terms import compile_term, is_case_number


@pytest.mark.parametrize(
    "text",
    [
        "CR-2227-2010",
        "CR-2227-\n2010",
        "CR-\n2227-2010",
        "CR - 2227 - 2010",
        "**CR-2227-2010",
    ],
)
def test_case_number_matches_when_wrapped_or_spaced_at_hyphens(text):
    assert compile_term("CR-2227-2010").search(text)


def test_case_number_does_not_match_a_different_number():
    assert not compile_term("CR-2227-2010").search("CR-2227-2011")
    assert not compile_term("CR-2227-2010").search("CR-22270-2010")


def test_partial_case_number_matches_as_substring():
    assert compile_term("RSA-4610").search("**RSA-4610-2011")


@pytest.mark.parametrize(
    "text, matches",
    [
        ("KRISHAN CHAND,", True),
        ("KRISHAN\nCHAND V/S", True),
        ("krishan  chand", True),
        ("KRISHAN CHANDER", False),
        ("RAMKRISHAN CHAND", False),
    ],
)
def test_names_match_whole_words_across_whitespace(text, matches):
    assert bool(compile_term("Krishan Chand").search(text)) is matches


@pytest.mark.parametrize(
    "term, expected",
    [("CR-2227-2010", True), ("RSA 4610", True), ("Vishnu Mittar", False)],
)
def test_is_case_number(term, expected):
    assert is_case_number(term) is expected
