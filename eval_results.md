# Care assistant eval

Run: 2026-11-14 22:51 · model: `gemini-3.5-flash-lite` · pass rule: pets with notes need ≥3 valid tasks and no error; pets without notes need 0 tasks and no error.

| Pet | Retrieved notes | Accepted | Rejected | Avg confidence | Low conf (<0.6) | Error | Result |
|---|---|---|---|---|---|---|---|
| Senior dog with arthritis | arthritis, dog, senior_pets | 8 | 0 | 0.96 | 0 | - | ✅ Pass |
| Young cat, no needs | puppies_kittens | 4 | 0 | 0.95 | 0 | - | ✅ Pass |
| Puppy | puppies_kittens | 5 | 0 | 0.84 | 0 | - | ✅ Pass |
| Senior cat on medication | cat, medications, senior_pets | 7 | 0 | 0.86 | 0 | - | ✅ Pass |
| Rabbit (no notes) | (none) | 0 | 0 | - | 0 | - | ✅ Pass |
| Empty species | (none) | 0 | 0 | - | 0 | - | ✅ Pass |

**Summary:** 6/6 passed, average confidence 0.90 across 24 accepted tasks
