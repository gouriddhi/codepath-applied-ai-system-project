# CLAUDE.md

## Project
PawPal+ AI — a Streamlit app that helps a pet owner plan daily pet-care tasks.
A rule-based scheduler builds the daily plan; a RAG care assistant suggests
tasks for each pet from a small knowledge base, using Gemini. Course project
(CodePath AI110), extending the Module 2 PawPal+ scheduler.

## Commands
- Setup: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`,
  then `cp .env.example .env` and set `GEMINI_API_KEY`.
- Run app: `streamlit run app.py`
- Tests: `pytest` (68 tests; no API key or network needed — Gemini is mocked)
- AI eval: `python eval_assistant.py` (makes REAL Gemini calls; writes `eval_results.md`).
  Only run it when the user asks.

## Structure
- `app.py` — Streamlit UI only. The `Owner` lives in `st.session_state.owner`.
  "AI care suggestions" section: per-pet button → `suggest_care_tasks`, owner approves
  suggestions with checkboxes, approved tasks are added to the pet. Pending suggestions
  live in `st.session_state.ai_suggestions`.
- `pawpal_system.py` — scheduler logic: `Task`, `Pet`, `Owner`, `Scheduler`
  (priority ordering, time slots, recurring tasks, conflict detection, explanations).
  Don't change scheduling behavior as part of AI work.
- `care_assistant.py` — RAG pipeline ("Process" stage of `diagrams/architecture.mmd`):
  - Retriever: matches `knowledge/*.md` by their `species`/`tags` front-matter, using
    species, an age tag (young < 1; senior dog ≥ 7, cat ≥ 10; else adult) and special-needs
    keywords. Filler words ("no", "none", "special", "needs") never match.
  - Gemini call: `google-genai` SDK, JSON response, model in `MODEL_NAME` at the top.
    No notes matched → no API call.
  - Guardrails: validate every field (allowed values, duration 1–240, confidence 0–1),
    convert valid ones to `Task`, reject others with a reason, relabel duplicate titles.
  - Never raises: errors (missing key, 429, API failure, bad JSON) go in `result.error`.
  - Logs retrieval, raw AI output, accept/reject decisions, owner review and errors to
    `logs/pawpal.log` (gitignored).
- `knowledge/` — hand-written care notes with a `---` metadata header (`species`, `tags`).
- `eval_assistant.py` — runs 6 sample pets through the real pipeline, Pass/Fail table.
- `tests/test_pawpal.py` (scheduler), `tests/test_care_assistant.py` (retriever,
  guardrails, error handling, with a fake Gemini client).
- `diagrams/architecture.mmd` (system), `diagrams/uml.mmd` (class diagram; filename fixed
  for grading). `README.md`, `model_card.md`, `reflection.md`, `ai_interactions.md` — write-ups.

## Rules
- NEVER read, print, or log the contents of `.env` (it holds the real API key).
  Tests must not load it either (mock `load_dotenv` / set the env var).
- Keep logic in Python modules; `app.py` only calls them.
- Priorities: "low" | "medium" | "high". Categories: walk, feeding, meds, enrichment,
  grooming, other. Frequencies: daily, weekly, once.
- Add pytest tests for new behavior; keep all tests passing.
- AI errors are shown in the UI as friendly `st.warning` messages, never tracebacks.
