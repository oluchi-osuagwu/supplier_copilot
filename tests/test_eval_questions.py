"""Structural tests for the evaluation question set.

The gold set will grow from 20 to 60-100 questions and drive every metric we report.
If a question has a typo in its route, or two questions share an id, the scores are quietly
wrong. These tests catch that at commit time. Treating eval data like code is a form of
"data contract" testing.
"""

from __future__ import annotations

from collections import Counter

import pytest
import yaml

from supplier_copilot.config import PROJECT_ROOT

QUESTIONS_PATH = PROJECT_ROOT / "eval" / "questions" / "sample_questions.yaml"
VALID_ROUTES = {"sql", "docs", "both", "refuse"}
VALID_DIFFICULTY = {"easy", "medium", "hard"}
REQUIRED_KEYS = {"id", "question", "route", "difficulty", "tests", "expected"}


@pytest.fixture(scope="module")
def questions() -> list[dict]:
    return yaml.safe_load(QUESTIONS_PATH.read_text(encoding="utf-8"))["questions"]


def test_has_twenty_questions(questions):
    assert len(questions) == 20


def test_every_question_has_required_fields(questions):
    for q in questions:
        missing = REQUIRED_KEYS - q.keys()
        assert not missing, f"{q.get('id')} is missing {missing}"


def test_ids_are_unique(questions):
    dupes = [i for i, n in Counter(q["id"] for q in questions).items() if n > 1]
    assert not dupes, f"duplicate ids: {dupes}"


def test_labels_use_allowed_values(questions):
    for q in questions:
        assert q["route"] in VALID_ROUTES, q["id"]
        assert q["difficulty"] in VALID_DIFFICULTY, q["id"]


def test_every_route_is_covered(questions):
    # A routing classifier can't be evaluated on a class that never appears.
    assert {q["route"] for q in questions} == VALID_ROUTES
