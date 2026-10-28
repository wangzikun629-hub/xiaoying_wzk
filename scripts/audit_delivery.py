"""Check submitted local links and generated evidence without calling a model."""

import json
import re

from campaign_planner.tools import PROJECT_ROOT


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
    for group in ("mock", "mock-scope-validated", "mock-final", "live", "live-validated", "live-final"):
        summary_path = PROJECT_ROOT / "examples" / group / "summary.json"
        if not summary_path.exists():
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
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
    return errors


if __name__ == "__main__":
    problems = audit()
    for problem in problems:
        print(problem)
    print(f"Delivery audit: {'PASS' if not problems else 'FAIL'}")
    raise SystemExit(bool(problems))
