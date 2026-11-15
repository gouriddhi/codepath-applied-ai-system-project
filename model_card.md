# Model Card: PawPal+ AI Care Assistant

## Overview

PawPal+ AI suggests daily pet-care tasks for a specific pet. A keyword retriever picks matching notes from `knowledge/`. Gemini (`gemini-3.5-flash-lite`, free tier) turns those notes into structured task suggestions. Guardrails validate every suggestion, and the owner approves or rejects each one before the existing scheduler plans it.

## Limitations and Biases

- **Only dogs and cats are covered.** The knowledge base has six hand-written notes, all for dogs and cats. Rabbits, birds, reptiles and any other species get no suggestions at all. That's safer than guessing, but less useful for those owners.
- **The notes are general guidance, not veterinary advice.** I wrote them from common pet-care guidelines, and no vet has reviewed them. Any gap or mistake in the notes carries straight into the suggestions.
- **Age groups are coarse.** "Senior" starts at 7 for dogs and 10 for cats for every pet. The senior note itself says large breeds age earlier (around 6), and the system doesn't know breed or size.
- **Keyword retrieval misses different wording.** A pet with "hip dysplasia" or "stiff joints" won't get `arthritis.md`, because neither phrase shares a word with that note's tags. Filler words caused the opposite problem, which I fixed (see below).
- **Confidence is self-reported.** The confidence score is the model's own estimate of how directly the notes support a task. It isn't measured against real outcomes, so 0.9 doesn't mean "right 90% of the time."
- **The guardrails check format, not truth.** They make sure every task has an allowed priority, category and duration. They can't tell whether a valid-looking task actually matches the notes, so a plausible but unsupported suggestion could still get through.
- **The pass rule doesn't check advice.** `eval_assistant.py` passes a run if the pipeline returns enough valid tasks without crashing. Whether the advice was good, I judged by reading the outputs myself.

## Misuse and Prevention

- **Treating it as a vet.** The biggest risk is an owner trusting a suggestion over their vet, especially for medication.
  - The prompt forbids specific drugs or doses; a meds task has to say "follow the vet's instructions."
  - The notes include warning signs that mean "contact a vet."
  - Nothing is added to the schedule until the owner approves it.
  - Not done yet: the app should show a short "not veterinary advice" note next to the suggestions.
- **Prompt injection through the special-needs field.** That free text goes into the prompt, so someone could type instructions like "ignore the notes."
  - The damage is limited because the output must be JSON with fixed fields and allowed values, so the worst case is an odd task the owner can uncheck.
  - The text can't trigger retrieval of anything outside `knowledge/`.
  - Not done yet: a length limit on the field.
- **Inventing advice for unsupported pets.** If no notes match, the app never calls Gemini. The model can't make up rabbit care from general knowledge because it never gets asked.
- **Leaking the API key.** The key lives in `.env`, which is gitignored. Only an empty `.env.example` is committed, and the key is never written to `logs/pawpal.log`.

## What Surprised Me While Testing Reliability

- **Gemini never produced an invalid task in real runs.** Every guardrail rejection in my tests came from unit tests with deliberately bad input. I still think the guardrails are worth having, but I can't point to a real run where they saved me.
- **The real bugs weren't where I expected.** I expected malformed JSON or bad durations. What I actually got was:
  - **A retrieval bug:** a 1-year-old cat with "no special needs" got arthritis advice, because the word "special" matched the `special-needs` tag.
  - **Over-retrieval:** every senior pet got arthritis advice because that note was tagged `senior`.
  - **Duplicate titles:** "Short slow walk" came back three times with the same name.
- **Every confidence score was 1.00 at first,** so the score told me nothing. After I added examples to the prompt of what 1.0 and about 0.5 should look like, inferred tasks started scoring 0.70–0.80. The model needed a definition, not just a field name.
- **The model I first picked stopped working.** `gemini-2.5-flash` returned a 404 for new users. Because errors were caught and logged, the app showed a warning instead of crashing, and the log told me exactly why.

## Collaboration with AI

I built this with Claude Code as a coding assistant. I wrote the plan in steps (care assistant, UI integration, tests, evaluation). Claude wrote the code for each step, then I ran it in the real app, read the logs, and came back with bugs. Several of the most important fixes started with something I noticed in a real run that the tests hadn't caught.

**A suggestion I accepted:** skipping the Gemini call entirely when no notes match. I had asked for the model to *say* when notes didn't cover a pet. Claude suggested also not calling the API in that case, and returning a clear message instead. I kept it because it makes "no notes, no invented advice" a guarantee in the code, not something I have to trust the model to follow. It also saves free-tier quota.

**A suggestion I changed:** the model choice. Claude's first version used `gemini-2.5-flash`. When I tested, that model returned a 404 for new API users, so I replaced it with `gemini-3.5-flash-lite`. The suggestion wasn't careless, because the name was kept in one constant, which made the switch a one-line change. But it didn't fit my situation as a new free-tier user, so I didn't keep it as written.

**Another correction:** when I reported the cat retrieval bug, I guessed an empty string was matching every note. Claude checked the log instead and found the real cause: the phrase "no special needs" matched the `special-needs` tag. My guessed fix wouldn't have solved it. That taught me to check the log before assuming why something broke.
