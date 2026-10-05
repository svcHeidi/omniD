"""A number of contract members stated in the repository's documents is the number ``provider_stack.MEMBERS`` holds."""
from __future__ import annotations

import re

from conftest import NO_REPO_ROOT, repo_root, skip_without_repo

from omnidriver.core.provider_stack import MEMBERS

pytestmark = skip_without_repo

_COUNT = re.compile(r"\b(\d+)\s+(?:(?:optional|contract|plugin)\s+)*members?\b")


def _stated_counts(text: str) -> list[int]:
    return [int(number) for number in _COUNT.findall(text)]


def test_the_scan_reads_a_stated_count():
    assert _stated_counts("a table of 39 optional members, and 4 contract members") == [39, 4]


def test_no_document_states_a_member_count_other_than_the_tables():
    root = repo_root or NO_REPO_ROOT
    documents = [*root.glob("*.md"), *(root / "docs").rglob("ROADMAP.md")]
    assert documents, "no document read"
    wrong = {
        path.relative_to(root).as_posix(): count
        for path in documents for count in _stated_counts(path.read_text()) if count != len(MEMBERS)
    }
    assert wrong == {}
