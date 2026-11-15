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
