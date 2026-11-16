# AI Interactions Log

> **Stretch features only.** Only fill in the sections that apply to stretch features you attempted. If you did not attempt a stretch feature, leave its section blank or delete it. This file is not required for the core project.

---

## Agent Workflow (SF7)

**What task did you give the agent?**

I used Claude Code (the agent in VS Code) to add a Retrieval-Augmented care assistant to PawPal+. I gave it one prompt per step and told it to stop after each, so I could check the result before moving on:

1. Write a `knowledge/` folder of pet-care notes with a metadata header (species, tags).
2. Build `care_assistant.py`: a tag-based retriever, a Gemini call that returns JSON, guardrails that validate each suggestion, logging, and error handling.
3. Connect it to the Streamlit app with an approve/reject step before tasks reach the scheduler.
4. Add pytest tests (with a fake Gemini client) and an evaluation script that runs sample pets through the real pipeline.
5. Check that the README, diagram and code all match.

**What did the agent do?**

- Created 6 notes in `knowledge/` (dog, cat, senior pets, puppies/kittens, medications, arthritis).
- Wrote `care_assistant.py` with the retriever, `call_gemini()`, `validate_suggestion()` / `apply_guardrails()`, `make_titles_distinct()`, and logging to `logs/pawpal.log`.
- Edited `app.py` to add a "Suggest care tasks with AI" button, the approval checkboxes, a special-needs field on the pet form, and a "not veterinary advice" caption.
- Added `google-genai` and `python-dotenv` to `requirements.txt`, created `.env.example`, and updated `.gitignore`.
- Wrote 20 tests in `tests/test_care_assistant.py` and the `eval_assistant.py` script, and ran `pytest` after each step. The final count was 68 passing tests.
- Updated `README.md`, `model_card.md` and `CLAUDE.md` to match the code, and removed a committed `__pycache__` file from git.

**What did you have to verify or fix manually?**

The agent tested with fake clients, so the real problems only showed up when I ran the app myself:

- **The model didn't exist for me.** The agent's first choice, `gemini-2.5-flash`, returned a 404 for new users. I found the cause in `logs/pawpal.log`, listed the models my key could use, and switched to `gemini-3.5-flash-lite`.
- **Duplicate titles.** In a real run, "Short slow walk" came back three times with the same name. I asked for a guardrail that relabels repeats instead of dropping them.
- **Wrong notes retrieved.** My screenshots showed a young cat with no special needs getting `arthritis.md`. The agent checked the log and found the real cause: the word "special" in "no special needs" matched the `special-needs` tag.
- **Over-retrieval.** The agent flagged that every senior pet got arthritis advice because the note was tagged `senior`. I decided to remove that tag so arthritis guidance only comes from a stated need.
- **Confidence scores were all 1.00.** I noticed this in the app and asked for a prompt change (see the comparison below).
- **Docs and honesty.** I checked the README and model card against what really happened. For example, I corrected the model card to say the knowledge notes were drafted with AI and reviewed by me, not written by me.

---

## Prompt Comparison (SF11)

Same model (`gemini-3.5-flash-lite`) and same task (suggest care tasks from retrieved notes), with two versions of the instructions for the `confidence` field.

| | Option A | Option B |
|-|----------|----------|
| **Model / tool used** | Gemini `gemini-3.5-flash-lite` | Gemini `gemini-3.5-flash-lite` |
| **Prompt** | Each task includes `confidence (0–1, how directly the notes support it)`. No further definition. | Confidence must measure how directly the notes state *this specific task*, scored separately per task. 1.0 = a note explicitly states it (example: "two or three short, slow walks of 10–20 minutes" → "Short slow walk, 15 min" = 1.0). About 0.5 = inferred from general advice (example: "lean body weight" → "Measure meals" ≈ 0.5). 0.7–0.8 when the note states the task but the model chose the duration, time or frequency. |
| **Response summary** | Every suggestion for both test pets scored **1.00**. | Directly stated tasks stayed at 1.00. Inferred ones scored lower, for example "Brush hips and back" 0.80, "Feed small meals" 0.80, and "Brush cat (assuming short-haired...)" 0.70. Eval average: 0.90, with per-pet averages from 0.84 to 0.96. |
| **What was useful** | The tasks themselves were reasonable and grounded in the notes. | The score now separates what the notes say from what the model filled in. The model even flagged its own assumption about coat type. |
| **Problems noticed** | The score carried no information, and the "low confidence" label in the UI could never trigger. | Still self-reported, so it's the model's judgment, not measured accuracy. No task dropped below the 0.6 low-confidence threshold in my runs. |
| **Decision** | Rejected | **Used** |

**Which approach did you use in your final implementation and why?**

Option B. A confidence score is only useful if it varies, and Option A gave the same 1.00 to everything, including tasks the model had partly made up the details for. Defining what each score means, with one concrete example from my own notes, made the model separate "the note says this" from "I inferred this." The lesson for me was that the model needed a definition, not just a field name. Even so, I still treat the score as a hint for the owner, not proof. That's why every suggestion still needs the owner's approval.
