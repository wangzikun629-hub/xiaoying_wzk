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
    summary = json.loads((PROJECT_ROOT / "examples/mock/summary.json").read_text(encoding="utf-8"))
    for item in summary["records"]:
        directory = PROJECT_ROOT / "examples/mock" / item["scenario"]
        for name in ("input.json", "output.json", "trace.jsonl", "run-metadata.json", "assertions.json"):
            if not (directory / name).is_file():
                errors.append(f"Missing evidence: {item['scenario']}/{name}")
        output = json.loads((directory / "output.json").read_text(encoding="utf-8"))
        if output.get("mode", "mock") != "mock":
            errors.append(f"Evidence mode mismatch: {item['scenario']}")
        if output["status"] == "completed" and not (directory / "plan.md").exists():
            errors.append(f"Missing saved plan export: {item['scenario']}")
    return errors


if __name__ == "__main__":
    problems = audit()
    for problem in problems:
        print(problem)
    print(f"Delivery audit: {'PASS' if not problems else 'FAIL'}")
    raise SystemExit(bool(problems))
