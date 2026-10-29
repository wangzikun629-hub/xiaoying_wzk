"""Check submitted local links and generated evidence without calling a model."""

import json
import re

from campaign_planner.tools import PROJECT_ROOT

CURRENT_GROUPS = ("review-mock", "review-live")
EXPECTED_CURRENT_SCENARIOS = 19


def audit():
    errors = []
    documents = [
        PROJECT_ROOT / "README.md",
        *(PROJECT_ROOT / "docs").glob("*.md"),
        *(PROJECT_ROOT / "examples").glob("*.md"),
    ]
    for document in documents:
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            if target.startswith(("http:", "https:", "#")):
                continue
            resolved = document.parent / target.split("#", 1)[0]
            if not resolved.exists():
                errors.append(f"Broken link: {document.relative_to(PROJECT_ROOT)} -> {target}")
    for group in (
        "mock", "mock-scope-validated", "mock-final", "live", "live-validated", "live-final",
        "yaml-mock", "yaml-live", *CURRENT_GROUPS,
    ):
        summary_path = PROJECT_ROOT / "examples" / group / "summary.json"
        if not summary_path.exists():
            if group in CURRENT_GROUPS:
                errors.append(f"Missing current summary: {group}")
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if group in CURRENT_GROUPS and (
            summary["total"] != EXPECTED_CURRENT_SCENARIOS
            or summary["passed"] != summary["total"]
            or len({r["scenario"] for r in summary["records"]}) != EXPECTED_CURRENT_SCENARIOS
        ):
            errors.append(f"Current acceptance scenarios incomplete or failing: {group}")
        for item in summary["records"]:
            directory = summary_path.parent / item["scenario"]
            for name in ("input.json", "output.json", "trace.jsonl", "run-metadata.json", "assertions.json"):
                if not (directory / name).is_file():
                    errors.append(f"Missing evidence: {group}/{item['scenario']}/{name}")
            output = json.loads((directory / "output.json").read_text(encoding="utf-8"))
            if output.get("mode", summary["mode"]) != summary["mode"]:
                errors.append(f"Evidence mode mismatch: {group}/{item['scenario']}")
            if output["status"] == "completed" and not (directory / "plan.md").exists():
                errors.append(f"Missing saved plan export: {group}/{item['scenario']}")
    # Historical runs intentionally retain their original source hashes. Only the
    # current delivery groups must match the working implementation, including resumes.
    from campaign_planner.runner import metadata

    current_source = metadata("mock", {})["source_sha256"]
    for group in CURRENT_GROUPS:
        root = PROJECT_ROOT / "examples" / group
        if not root.exists():
            errors.append(f"Missing current evidence group: {group}")
            continue
        for path in root.rglob("run-metadata.json"):
            recorded = json.loads(path.read_text(encoding="utf-8"))
            if recorded.get("source_sha256") != current_source:
                errors.append(f"Current evidence source mismatch: {path.relative_to(PROJECT_ROOT)}")
    return errors


if __name__ == "__main__":
    problems = audit()
    for problem in problems:
        print(problem)
    print(f"Delivery audit: {'PASS' if not problems else 'FAIL'}")
    raise SystemExit(bool(problems))
