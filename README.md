# 🐾 PawPal+ AI: Pet Care Planner with a Retrieval-Augmented Care Assistant

PawPal+ AI helps busy pet owners turn "what does my pet actually need?" into a realistic daily schedule. When you add a pet, an AI care assistant looks up relevant care guidelines for that pet's species, age, and special needs, suggests care tasks grounded in those guidelines, and, once you approve them, schedules them around the time you actually have.

**Why it matters:** generic AI chatbots give generic pet advice. This system grounds every suggestion in a curated knowledge base, checks each suggestion before it touches your schedule, and keeps a human in control of what gets added.

---

## 📌 Original Project (Modules 1–3)

This project extends **PawPal+**, my Module 2 project for CodePath AI110. The original PawPal+ was a Streamlit app where a pet owner could enter pets and care tasks (walks, feeding, meds, grooming) and get a daily plan built around their available time and task priorities. Its scheduler handled fixed and flexible time slots, daily/weekly recurring tasks, overlapping-task conflict detection with fix suggestions, and a plain-language explanation for every scheduled or skipped task. There was no AI in it: the owner had to know and enter every task by hand.

---

## 🏗️ Architecture Overview

![System architecture](assets/architecture.png)

Diagram source: [`diagrams/architecture.mmd`](diagrams/architecture.mmd)

The system runs in four stages:

1. **Input:** the owner adds a pet (species, age, special needs) in the Streamlit UI (`app.py`).
2. **Process (RAG):** `care_assistant.py` runs the AI pipeline.
   - The **retriever** selects the matching care notes from the `knowledge/` folder (for example, `dog.md` + `senior_pets.md` for a 12-year-old dog).
   - The retrieved notes and the pet's details are sent to the **Gemini API**, which is instructed to suggest tasks *only* based on those notes and return them as JSON.
   - **Guardrails** validate every suggestion (allowed priority, duration between 1 and 240 minutes, known category, required fields). Invalid suggestions and API errors are logged and never reach the schedule.
3. **Human check:** the owner reviews the suggested tasks and approves or rejects each one.
4. **Output:** approved tasks become real `Task` objects in the existing scheduler (`pawpal_system.py`), which builds the daily plan, flags conflicts, and explains its choices.

**Testing and monitoring:** `pytest` covers the scheduler and the guardrails; an evaluation script runs sample pets through the full pipeline and checks the AI's output; everything the assistant retrieves, suggests, accepts, or rejects is written to `logs/pawpal.log`.

---

## ⚙️ Setup Instructions

**Requirements:** Python 3.10+ and a free Gemini API key (from aistudio.google.com).

```bash
# 1. Clone the repo
git clone https://github.com/gouriddhi/codepath-applied-ai-system-project.git
cd codepath-applied-ai-system-project

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add your API key
cp .env.example .env
# then open .env and set GEMINI_API_KEY=your-key-here

# 5. Run the app
streamlit run app.py
```

**Run the tests** (no API key needed; the AI calls are mocked):
```bash
pytest
```

**Run the AI evaluation** (uses the API):
```bash
python eval_assistant.py
```

> TODO: confirm these file names and commands match the final code before submitting.

---

## 💬 Sample Interactions

> TODO: fill in with **real** runs of the finished app. For each one, paste the input, the notes that were retrieved, and the tasks the AI suggested (and which the guardrails accepted or rejected). Screenshots can go in `assets/`.

**Example 1: Senior dog with arthritis**
- Input: `Biscuit, dog, age 12, special needs: arthritis`
- Retrieved notes: `arthritis.md`, `dog.md`, `senior_pets.md`
- AI suggestions: 9 tasks
  - Short slow walk, 15 min, high (x3)
  - Feeding, 10 min, high (x2)
  - Refill and rinse water bowl, 5 min, medium
  - Enrichment activity, 10 min, medium
  - Brush hips and back, 5 min, medium
  - Health monitoring note, 5 min, low
- Guardrail result: 9 accepted, 0 rejected
- Observation: the suggestions matched the senior and arthritis guidance (short, low-impact walks and gentle brushing). However, repeated tasks came back with identical titles, so I added a guardrail that labels duplicates by time of day or number, e.g. "Short slow walk (morning)" or "Feeding 1/2".

**Example 2: Young cat, no special needs**
- Input: `Luna, cat, age 1`
- Retrieved notes: TODO
- AI suggestions: TODO
- Guardrail result: TODO

**Example 3: Guardrails in action**
- Input: TODO (e.g. a species with no matching notes, or a run where the AI returned an invalid duration)
- What happened: TODO (e.g. "no notes found; assistant declined to guess" or "1 of 4 suggestions rejected: duration 600 min exceeds limit")

---

## 🧠 Design Decisions

- **Simple, transparent retrieval over vector embeddings.** The knowledge base is a small set of hand-written markdown notes, so the retriever matches on species, age group, and special-needs keywords. This is easy to test, needs no extra infrastructure, and makes it obvious *why* a note was retrieved. Trade-off: it won't find notes that use different wording than the pet's details, and it won't scale to a large knowledge base the way embeddings would.
- **The AI suggests; the scheduler decides.** Claude only proposes tasks. The existing, already-tested `Scheduler` still decides when things happen. This keeps the AI's job small and checkable, and reuses code that was already tested. Trade-off: the AI can't directly optimize the schedule itself.
- **Structured JSON output + validation.** Asking for JSON with fixed fields means every suggestion can be checked against the same rules as a hand-entered task. Anything that fails validation is dropped and logged rather than "fixed" silently.
- **Human approval before anything is scheduled.** Pet care involves medication and health, so the owner always reviews AI suggestions instead of having them added automatically. Trade-off: one extra click for the user.
- **Grounded prompts.** The prompt tells the model to base suggestions only on the retrieved notes and to say so when the notes don't cover a situation, which reduces made-up advice.

> TODO: add or adjust anything you changed while building.

---

## 🧪 Testing Summary

> TODO: fill in after running the tests and the eval script. Include real numbers, for example:
> - `pytest`: X tests passing (scheduler tests from Module 2 + new guardrail/retriever tests)
> - Evaluation: X of Y sample pets produced only valid tasks; X suggestions rejected by guardrails and why
> - What didn't work at first and how you fixed it
> - What you learned from testing the AI part vs. the regular code

---

## 💭 Reflection

> TODO: a few sentences on what this project taught you about AI and problem-solving (e.g. how much of building an AI feature is checking its output, why grounding the model in your own data changes the results). The graded responsible-AI reflection goes in `model_card.md`.