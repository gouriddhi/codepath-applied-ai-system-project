"""Tests for care_assistant.py guardrails, using a mocked Gemini client (no network)."""

import json
from types import SimpleNamespace

import pytest

from care_assistant import retrieve_notes, suggest_care_tasks
from pawpal_system import Pet


class FakeClient:
    """Stands in for google.genai.Client; returns a fixed JSON reply."""

    def __init__(self, reply: dict):
        self.models = self
        self._text = json.dumps(reply)

    def generate_content(self, **kwargs):
        return SimpleNamespace(text=self._text)


def suggestion(title, preferred_time, category="walk"):
    return {
        "title": title,
        "duration_minutes": 15,
        "priority": "high",
        "category": category,
        "preferred_time": preferred_time,
        "frequency": "daily",
        "reason": "From the senior_pets note.",
        "confidence": 0.9,
    }


def test_duplicate_titles_are_kept_and_made_distinct():
    reply = {
        "tasks": [
            # Three walks with different times -> labeled by time of day.
            suggestion("Short slow walk", "morning"),
            suggestion("Short slow walk", "afternoon"),
            suggestion("Short slow walk", "evening"),
            # Two feedings without distinct times -> numbered.
            suggestion("Feeding", None, category="feeding"),
            suggestion("feeding", None, category="feeding"),
            # A unique title is left alone.
            suggestion("Brush coat", None, category="grooming"),
        ],
        "message": None,
    }
    pet = Pet(name="Biscuit", species="dog", age=12, special_needs=["arthritis"])

    result = suggest_care_tasks(pet, client=FakeClient(reply))

    assert result.error is None
    assert result.rejected == []
    titles = [t.title for t in result.accepted]
    assert titles == [
        "Short slow walk (morning)",
        "Short slow walk (afternoon)",
        "Short slow walk (evening)",
        "Feeding 1/2",
        "Feeding 2/2",
        "Brush coat",
    ]
    assert len(set(titles)) == len(titles)


# --- Retriever ---------------------------------------------------------------

def note_names(pet):
    return [n.name for n in retrieve_notes(pet)]


@pytest.mark.parametrize("needs", [[], [""], ["   "], ["no special needs"], ["none"]])
def test_cat_without_special_needs_does_not_get_arthritis(needs):
    names = note_names(Pet(name="Luna", species="cat", age=1, special_needs=needs))
    assert "arthritis" not in names
    assert "cat" in names


def test_dog_with_arthritis_gets_arthritis_note():
    names = note_names(Pet(name="Biscuit", species="dog", age=12, special_needs=["arthritis"]))
    assert "arthritis" in names


def test_no_notes_message_names_the_species():
    result = suggest_care_tasks(Pet(name="Hop", species="other", age=2))
    assert result.retrieved_notes == []
    assert result.model_message == "No care notes match this pet (species: other), so no tasks were suggested."


def test_senior_dog_with_arthritis_gets_exactly_the_right_notes():
    names = note_names(Pet(name="Biscuit", species="dog", age=12, special_needs=["arthritis"]))
    assert sorted(names) == ["arthritis", "dog", "senior_pets"]


# --- Guardrails ----------------------------------------------------------------

def valid(**overrides):
    task = suggestion("Short slow walk", "morning")
    task.update(overrides)
    return task


BISCUIT = Pet(name="Biscuit", species="dog", age=12, special_needs=["arthritis"])


def test_valid_tasks_are_accepted_as_task_objects():
    result = suggest_care_tasks(BISCUIT, client=FakeClient({"tasks": [valid()], "message": None}))
    assert result.error is None and result.rejected == []
    [task] = result.accepted
    assert (task.title, task.duration_minutes, task.priority, task.category) == ("Short slow walk", 15, "high", "walk")
    assert result.details[task.task_id]["confidence"] == 0.9


@pytest.mark.parametrize(
    "bad, reason_fragment",
    [
        (valid(duration_minutes=0), "outside 1-240"),
        (valid(duration_minutes=600), "outside 1-240"),
        (valid(priority="urgent"), "priority"),
        (valid(category="bathing"), "category"),
        ({k: v for k, v in valid().items() if k != "title"}, "missing required field(s): title"),
        (valid(confidence=1.5), "confidence"),
    ],
)
def test_bad_tasks_are_rejected_with_a_reason(bad, reason_fragment):
    reply = {"tasks": [valid(title="Good walk"), bad], "message": None}
    result = suggest_care_tasks(BISCUIT, client=FakeClient(reply))
    assert [t.title for t in result.accepted] == ["Good walk"]
    assert len(result.rejected) == 1
    assert result.rejected[0]["suggestion"] == bad
    assert reason_fragment in result.rejected[0]["reason"]


# --- Error handling (must never raise) -------------------------------------------

class RawClient:
    """Fake client returning raw text, or raising the given exception."""

    def __init__(self, text=None, exc=None):
        self.models = self
        self._text, self._exc = text, exc

    def generate_content(self, **kwargs):
        if self._exc:
            raise self._exc
        return SimpleNamespace(text=self._text)


def test_malformed_json_returns_empty_result_with_error():
    result = suggest_care_tasks(BISCUIT, client=RawClient(text='{"tasks": [ oops'))
    assert result.accepted == [] and "not valid JSON" in result.error


def test_rate_limit_429_returns_friendly_error():
    from google.genai import errors

    exc = errors.ClientError(429, {"error": {"message": "Resource exhausted"}})
    result = suggest_care_tasks(BISCUIT, client=RawClient(exc=exc))
    assert result.accepted == [] and "rate limit" in result.error.lower()


def test_missing_api_key_returns_error_without_calling_gemini(monkeypatch):
    import dotenv

    # Keep the real .env out of the test: no-op load_dotenv and an empty key.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setenv("GEMINI_API_KEY", "")
    result = suggest_care_tasks(BISCUIT)
    assert result.accepted == []
    assert "GEMINI_API_KEY is not set" in result.error


def test_arthritis_note_comes_only_from_a_stated_special_need():
    senior_cat = Pet(name="Whiskers", species="cat", age=14, special_needs=["medication"])
    cat_notes = note_names(senior_cat)
    assert "arthritis" not in cat_notes
    assert "medications" in cat_notes and "senior_pets" in cat_notes

    senior_dog = Pet(name="Biscuit", species="dog", age=12, special_needs=["arthritis"])
    assert "arthritis" in note_names(senior_dog)
