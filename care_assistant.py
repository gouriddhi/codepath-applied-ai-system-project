"""PawPal+ care assistant: the "Process" stage of diagrams/architecture.mmd.

Pipeline:  Retriever (knowledge/ notes)  ->  Gemini API (task suggestions as JSON)
           ->  Guardrails (validate, convert to Task)  ->  CareSuggestionResult

Nothing here touches the UI. The owner reviews the accepted tasks before they
reach the Scheduler (the "Human check" stage).
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from pawpal_system import Pet, Task

# --- Configuration ---------------------------------------------------------

MODEL_NAME = "gemini-3.5-flash-lite"  # free-tier Flash model
API_KEY_ENV = "GEMINI_API_KEY"

BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
LOG_FILE = BASE_DIR / "logs" / "pawpal.log"

# Allowed values for suggestions (guardrails).
PRIORITIES = {"low", "medium", "high"}
CATEGORIES = {"walk", "feeding", "meds", "enrichment", "grooming", "other"}
PREFERRED_TIMES = {"morning", "afternoon", "evening"}
FREQUENCIES = {"daily", "weekly", "once"}
MIN_DURATION, MAX_DURATION = 1, 240
LOW_CONFIDENCE = 0.6  # below this, the UI labels a suggestion "low confidence"
REQUIRED_FIELDS = (
    "title", "duration_minutes", "priority", "category",
    "preferred_time", "frequency", "reason", "confidence",
)

# Age -> tag, from the ranges in knowledge/puppies_kittens.md and senior_pets.md.
YOUNG_UNDER_YEARS = 1                      # puppies/kittens: under ~12 months
SENIOR_FROM_YEARS = {"dog": 7, "cat": 10}  # dogs ~7-8, cats ~10-11


# --- Logging ----------------------------------------------------------------

def _get_logger() -> logging.Logger:
    """Return the module logger, writing to logs/pawpal.log (handler added once)."""
    logger = logging.getLogger("pawpal.care_assistant")
    if not logger.handlers:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


log = _get_logger()


# --- Result types -----------------------------------------------------------

@dataclass
class Note:
    """One knowledge note: file stem, metadata, and body text."""

    name: str
    species: set[str]
    tags: set[str]
    text: str


@dataclass
class CareSuggestionResult:
    """Everything the UI needs from one run of the care assistant."""

    retrieved_notes: list[str] = field(default_factory=list)
    accepted: list[Task] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)  # {"suggestion": ..., "reason": ...}
    details: dict[str, dict] = field(default_factory=dict)  # task_id -> {"reason", "confidence"}
    error: Optional[str] = None
    model_message: Optional[str] = None  # e.g. the model saying the notes don't cover this pet

    @property
    def ok(self) -> bool:
        """True when the run finished without an error."""
        return self.error is None


# --- Retriever --------------------------------------------------------------

def _split_list(value: str) -> set[str]:
    """Turn "dog, cat" into {"dog", "cat"}."""
    return {part.strip().lower() for part in value.split(",") if part.strip()}


def parse_note(path: Path) -> Optional[Note]:
    """Read a note's `---` metadata header (species, tags) and body. None if no header."""
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        return None
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return None
    meta: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip().lower()] = value
    return Note(
        name=path.stem,
        species=_split_list(meta.get("species", "")),
        tags=_split_list(meta.get("tags", "")),
        text=parts[2].strip(),
    )


def load_notes(knowledge_dir: Path = KNOWLEDGE_DIR) -> list[Note]:
    """Load every note with a valid header from the knowledge folder."""
    notes = []
    for path in sorted(knowledge_dir.glob("*.md")):
        note = parse_note(path)
        if note is None:
            log.warning("Skipping %s: missing metadata header", path.name)
        else:
            notes.append(note)
    return notes


def age_tag(species: str, age: Optional[int]) -> Optional[str]:
    """Map an age in years to "young", "adult" or "senior" (None if age is unknown)."""
    if age is None:
        return None
    if age < YOUNG_UNDER_YEARS:
        return "young"
    senior_from = SENIOR_FROM_YEARS.get(species.strip().lower())
    if senior_from is not None and age >= senior_from:
        return "senior"
    return "adult"


def _normalize(word: str) -> str:
    """Lowercase and drop a trailing plural "s" so "medication" matches "medications"."""
    word = word.strip().lower()
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


# Filler words that must never cause a match on their own. Without this, an owner typing
# "no special needs" matched arthritis.md's "special-needs" tag.
IGNORED_NEED_WORDS = {"no", "none", "n/a", "na", "nothing", "special", "need", "needs", "general"}


def _need_words(text: str) -> set[str]:
    """Meaningful, normalized words in a need or tag ("joint pain" -> {"joint", "pain"})."""
    words = {_normalize(w) for w in text.replace("-", " ").replace("/", " ").split()}
    return {w for w in words if w and w not in IGNORED_NEED_WORDS}


def _need_matches_tag(need: str, tag: str) -> bool:
    """True if a special need and a tag share a meaningful word, e.g. "joint pain" ~ "pain"."""
    return bool(_need_words(need) & _need_words(tag))


def wanted_tags(pet: Pet) -> set[str]:
    """Tags implied by the pet's age (plus "general" for non-young pets)."""
    tag = age_tag(pet.species, pet.age)
    tags = {tag} if tag else set()
    if tag != "young":
        tags.add("general")  # adult species guide also applies to adult/senior/unknown age
    return tags


def retrieve_notes(pet: Pet, notes: Optional[list[Note]] = None) -> list[Note]:
    """Pick notes for this pet's species that match its age tag or a special need."""
    notes = load_notes() if notes is None else notes
    species = pet.species.strip().lower()
    tags = wanted_tags(pet)
    # Ignore blank entries and ones made only of filler words ("", "  ", "none", "no special needs").
    needs = [n.strip() for n in pet.special_needs if isinstance(n, str) and _need_words(n)]

    matched = []
    for note in notes:
        if species not in note.species:
            continue
        if note.tags & tags or any(_need_matches_tag(n, t) for n in needs for t in note.tags):
            matched.append(note)

    log.info(
        "Retrieval for pet=%r species=%s age=%s needs=%s tags=%s -> %s",
        pet.name, species, pet.age, needs, sorted(tags), [n.name for n in matched] or "no notes",
    )
    return matched


# --- Gemini call ------------------------------------------------------------

SYSTEM_INSTRUCTION = """You are a pet-care planning assistant for the PawPal+ app.
Suggest daily care tasks for ONE pet using ONLY the care notes provided.
Rules:
- Every task must be directly supported by the notes. Do not use outside knowledge or guess.
- If the notes do not cover this pet, return an empty "tasks" list and explain why in "message".
- Do not suggest specific drugs or doses; a meds task should say to follow the vet's instructions.
- "confidence" must measure how directly the notes state THIS specific task, not how sure
  you are in general. Score each task separately; do not give every task the same score.
  - 1.0: a note explicitly states the task, including what to do and roughly how long or often.
    Example: the arthritis note says "two or three short, slow walks of 10-20 minutes", so
    "Short slow walk, 15 min, daily" scores 1.0.
  - about 0.5: you inferred the task from more general advice in a note.
    Example: the arthritis note says "keeping a lean body weight" reduces joint pain, so
    "Measure meals to manage weight" is an inference and scores about 0.5.
  - Use values in between (e.g. 0.7-0.8) when the note states the task but you chose the
    duration, time of day, or frequency yourself. Use below 0.5 for weak support.
- Respond with JSON only, in exactly this shape:
{
  "tasks": [
    {
      "title": string,
      "duration_minutes": integer between 1 and 240,
      "priority": "low" | "medium" | "high",
      "category": "walk" | "feeding" | "meds" | "enrichment" | "grooming" | "other",
      "preferred_time": "morning" | "afternoon" | "evening" | null,
      "frequency": "daily" | "weekly" | "once",
      "reason": string naming the note it comes from,
      "confidence": number from 0 to 1 (how directly the notes support it)
    }
  ],
  "message": string or null
}"""


def build_prompt(pet: Pet, notes: list[Note]) -> str:
    """Combine pet info and retrieved notes into the user prompt."""
    needs = ", ".join(pet.special_needs) if pet.special_needs else "none"
    age = f"{pet.age} years" if pet.age is not None else "unknown"
    notes_text = "\n\n".join(f"### Note: {n.name}\n{n.text}" for n in notes)
    return (
        f"Pet: {pet.name}\nSpecies: {pet.species}\nAge: {age} "
        f"(age group: {age_tag(pet.species, pet.age) or 'unknown'})\n"
        f"Special needs: {needs}\n\nCare notes:\n\n{notes_text}"
    )


def _make_client(api_key: str) -> Any:
    """Create a google-genai client (imported lazily so the module loads without it)."""
    from google import genai
    return genai.Client(api_key=api_key)


def call_gemini(prompt: str, client: Any) -> str:
    """Send the prompt to Gemini, asking for a JSON response; return the raw text."""
    from google.genai import types
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )
    text = response.text
    if not text:
        raise ValueError("Gemini returned an empty response (it may have been blocked).")
    return text


def _describe_api_error(exc: Exception) -> str:
    """Turn an SDK/network exception into a short, user-friendly message."""
    code = getattr(exc, "code", None)
    if code == 429:
        return "Gemini rate limit reached (429). Wait a minute and try again."
    if code in (401, 403):
        return "Gemini rejected the API key. Check GEMINI_API_KEY in your .env file."
    if code is not None:
        return f"Gemini API error ({code}). Please try again later."
    return f"Could not reach the Gemini API ({type(exc).__name__})."


# --- Guardrails -------------------------------------------------------------

def validate_suggestion(item: Any) -> tuple[Optional[dict], Optional[str]]:
    """Check one suggestion. Returns (cleaned dict, None) or (None, reason it was rejected)."""
    if not isinstance(item, dict):
        return None, "suggestion is not a JSON object"

    missing = [f for f in REQUIRED_FIELDS if f not in item]
    if missing:
        return None, f"missing required field(s): {', '.join(missing)}"

    title = item["title"]
    if not isinstance(title, str) or not title.strip():
        return None, "title must be a non-empty string"

    duration = item["duration_minutes"]
    if isinstance(duration, float) and duration.is_integer():
        duration = int(duration)
    if isinstance(duration, bool) or not isinstance(duration, int):
        return None, f"duration_minutes must be a whole number, got {duration!r}"
    if not MIN_DURATION <= duration <= MAX_DURATION:
        return None, f"duration_minutes {duration} is outside {MIN_DURATION}-{MAX_DURATION}"

    checks = (
        ("priority", PRIORITIES),
        ("category", CATEGORIES),
        ("frequency", FREQUENCIES),
    )
    cleaned_choices = {}
    for name, allowed in checks:
        value = item[name]
        value = value.strip().lower() if isinstance(value, str) else value
        if value not in allowed:
            return None, f"{name} {item[name]!r} is not one of {sorted(allowed)}"
        cleaned_choices[name] = value

    preferred = item["preferred_time"]
    if isinstance(preferred, str):
        preferred = preferred.strip().lower() or None
        if preferred in ("null", "none", "any"):
            preferred = None
    if preferred is not None and preferred not in PREFERRED_TIMES:
        return None, f"preferred_time {item['preferred_time']!r} is not one of {sorted(PREFERRED_TIMES)} or null"

    reason = item["reason"]
    if not isinstance(reason, str) or not reason.strip():
        return None, "reason must be a non-empty string"

    confidence = item["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return None, f"confidence must be a number, got {confidence!r}"
    if not 0 <= confidence <= 1:
        return None, f"confidence {confidence} is outside 0-1"

    return {
        "title": title.strip(),
        "duration_minutes": duration,
        **cleaned_choices,
        "preferred_time": preferred,
        "reason": reason.strip(),
        "confidence": float(confidence),
    }, None


def to_task(clean: dict) -> Task:
    """Convert a validated suggestion into a Task; reason + confidence go in the description."""
    return Task(
        title=clean["title"],
        duration_minutes=clean["duration_minutes"],
        priority=clean["priority"],
        category=clean["category"],
        preferred_time=clean["preferred_time"],
        frequency=clean["frequency"],
        description=f"{clean['reason']} (AI confidence: {clean['confidence']:.2f})",
    )


def apply_guardrails(suggestions: list[Any], result: CareSuggestionResult) -> None:
    """Validate each suggestion, adding Tasks to result.accepted or entries to result.rejected."""
    for item in suggestions:
        clean, reason = validate_suggestion(item)
        if clean is None:
            result.rejected.append({"suggestion": item, "reason": reason})
            log.info("Rejected suggestion %s: %s", json.dumps(item, default=str), reason)
            continue
        try:
            task = to_task(clean)
        except ValueError as exc:  # Task's own checks (e.g. frequency) as a last line of defense
            result.rejected.append({"suggestion": item, "reason": str(exc)})
            log.info("Rejected suggestion %s: %s", json.dumps(item, default=str), exc)
            continue
        result.accepted.append(task)
        result.details[task.task_id] = {"reason": clean["reason"], "confidence": clean["confidence"]}
        log.info("Accepted task %r (confidence %.2f)", task.title, clean["confidence"])


def make_titles_distinct(tasks: list[Task]) -> None:
    """Rename tasks that share a title (case-insensitive) so each one is distinguishable.

    Every task is kept. If the duplicates all have different preferred times, each gets
    a label like "Short slow walk (morning)"; otherwise they're numbered "Short slow walk 1/3".
    """
    groups: dict[str, list[Task]] = {}
    for task in tasks:
        groups.setdefault(task.title.strip().lower(), []).append(task)

    for group in groups.values():
        if len(group) < 2:
            continue
        original = group[0].title
        times = [t.preferred_time for t in group]
        use_times = None not in times and len(set(times)) == len(times)
        for i, task in enumerate(group, start=1):
            task.title = f"{original} ({task.preferred_time})" if use_times else f"{original} {i}/{len(group)}"
        log.info(
            "Duplicate title %r x%d; renamed to %s",
            original, len(group), [t.title for t in group],
        )


def log_owner_review(pet_name: str, approved: list[Task], rejected: list[Task]) -> None:
    """Record the owner's approve/reject decision (the "Human check" stage)."""
    log.info(
        "Owner review for pet=%r: %d approved %s, %d rejected %s",
        pet_name, len(approved), [t.title for t in approved],
        len(rejected), [t.title for t in rejected],
    )


# --- Main entry point -------------------------------------------------------

def suggest_care_tasks(pet: Pet, client: Any = None, notes: Optional[list[Note]] = None) -> CareSuggestionResult:
    """Run retrieve -> Gemini -> guardrails for one pet. Never raises; errors go in result.error.

    Args:
        pet: The pet to plan for (species, age, special_needs are used).
        client: Optional pre-built genai client (tests pass a fake one).
        notes: Optional preloaded notes; defaults to reading knowledge/.
    """
    result = CareSuggestionResult()

    try:
        matched = retrieve_notes(pet, notes)
    except OSError as exc:
        result.error = "Could not read the care notes in knowledge/."
        log.exception("Failed to load notes: %s", exc)
        return result
    result.retrieved_notes = [n.name for n in matched]

    if not matched:
        result.model_message = (
            f"No care notes match this pet (species: {pet.species}), so no tasks were suggested."
        )
        log.info("No notes matched for pet=%r; skipping the Gemini call", pet.name)
        return result

    if client is None:
        from dotenv import load_dotenv
        load_dotenv(BASE_DIR / ".env")
        api_key = os.getenv(API_KEY_ENV, "").strip()
        if not api_key:
            result.error = f"{API_KEY_ENV} is not set. Add it to your .env file (see .env.example)."
            log.error("Missing %s", API_KEY_ENV)
            return result
        try:
            client = _make_client(api_key)
        except Exception as exc:
            result.error = "Could not start the Gemini client."
            log.exception("Client setup failed: %s", type(exc).__name__)
            return result

    try:
        raw = call_gemini(build_prompt(pet, matched), client)
    except Exception as exc:
        result.error = _describe_api_error(exc)
        log.error("Gemini call failed: %s: %s", type(exc).__name__, exc)
        return result
    log.info("Gemini raw response: %s", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        result.error = "The AI response was not valid JSON, so no tasks were added."
        log.error("Malformed JSON from Gemini: %s", exc)
        return result

    if isinstance(data, list):  # tolerate a bare list of tasks
        data = {"tasks": data}
    if not isinstance(data, dict) or not isinstance(data.get("tasks", []), list):
        result.error = "The AI response had an unexpected shape, so no tasks were added."
        log.error("Unexpected JSON shape from Gemini: %s", type(data).__name__)
        return result

    message = data.get("message")
    result.model_message = message if isinstance(message, str) and message.strip() else None
    apply_guardrails(data.get("tasks", []), result)
    make_titles_distinct(result.accepted)
    log.info(
        "Run finished for pet=%r: %d accepted, %d rejected",
        pet.name, len(result.accepted), len(result.rejected),
    )
    return result
