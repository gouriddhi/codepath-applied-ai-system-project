"""Reliability eval: run sample pets through the REAL care-assistant pipeline (calls Gemini).

Usage:  python eval_assistant.py
Needs GEMINI_API_KEY in .env. Prints a markdown table and saves it to eval_results.md.
"""

import time
from datetime import datetime

from care_assistant import LOW_CONFIDENCE, MODEL_NAME, suggest_care_tasks
from pawpal_system import Pet

DELAY_SECONDS = 6  # pause after each Gemini call to stay under free-tier rate limits
MIN_TASKS = 3      # pets with matching notes should get at least this many valid tasks
RESULTS_FILE = "eval_results.md"

# (label, pet, expect_tasks): expect_tasks=False means "no notes -> no tasks, no crash".
SAMPLES = [
    ("Senior dog with arthritis", Pet("Biscuit", "dog", 12, ["arthritis"]), True),
    ("Young cat, no needs", Pet("Luna", "cat", 0), True),
    ("Puppy", Pet("Pip", "dog", 0), True),
    ("Senior cat on medication", Pet("Whiskers", "cat", 14, ["medication"]), True),
    ("Rabbit (no notes)", Pet("Hop", "rabbit", 2), False),
    ("Empty species", Pet("Mystery", "", 3), False),
]


def evaluate(label: str, pet: Pet, expect_tasks: bool) -> dict:
    """Run one pet and return a row of metrics plus Pass/Fail."""
    try:
        result = suggest_care_tasks(pet)
    except Exception as exc:  # the pipeline should never raise; count it as a failure
        return {"label": label, "notes": "-", "accepted": 0, "rejected": 0, "confidences": [],
                "low": 0, "error": f"CRASH: {type(exc).__name__}", "passed": False, "called_api": True}

    confidences = [result.details[t.task_id]["confidence"] for t in result.accepted if t.task_id in result.details]
    if expect_tasks:
        passed = result.error is None and len(result.accepted) >= MIN_TASKS
    else:
        passed = result.error is None and not result.accepted
    return {
        "label": label,
        "notes": ", ".join(result.retrieved_notes) or "(none)",
        "accepted": len(result.accepted),
        "rejected": len(result.rejected),
        "confidences": confidences,
        "low": sum(c < LOW_CONFIDENCE for c in confidences),
        "error": result.error or "",
        "passed": passed,
        "called_api": bool(result.retrieved_notes),
    }


def to_markdown(rows: list[dict]) -> str:
    """Build the results table and summary line."""
    lines = [
        "| Pet | Retrieved notes | Accepted | Rejected | Avg confidence | Low conf (<0.6) | Error | Result |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        avg = f"{sum(r['confidences']) / len(r['confidences']):.2f}" if r["confidences"] else "-"
        error = r["error"].replace("|", "\\|") or "-"
        lines.append(
            f"| {r['label']} | {r['notes']} | {r['accepted']} | {r['rejected']} | {avg} | "
            f"{r['low']} | {error} | {'✅ Pass' if r['passed'] else '❌ Fail'} |"
        )

    all_conf = [c for r in rows for c in r["confidences"]]
    passed = sum(r["passed"] for r in rows)
    summary = f"{passed}/{len(rows)} passed"
    if all_conf:
        summary += f", average confidence {sum(all_conf) / len(all_conf):.2f} across {len(all_conf)} accepted tasks"
    return "\n".join(lines) + f"\n\n**Summary:** {summary}\n"


def main() -> None:
    rows = []
    for i, (label, pet, expect_tasks) in enumerate(SAMPLES, start=1):
        print(f"[{i}/{len(SAMPLES)}] {label}...", flush=True)
        row = evaluate(label, pet, expect_tasks)
        rows.append(row)
        if row["called_api"] and i < len(SAMPLES):
            time.sleep(DELAY_SECONDS)

    table = to_markdown(rows)
    header = (
        f"# Care assistant eval\n\nRun: {datetime.now():%Y-%m-%d %H:%M} · model: `{MODEL_NAME}` · "
        f"pass rule: pets with notes need ≥{MIN_TASKS} valid tasks and no error; "
        f"pets without notes need 0 tasks and no error.\n\n"
    )
    print("\n" + table)
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        f.write(header + table)
    print(f"Saved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()
