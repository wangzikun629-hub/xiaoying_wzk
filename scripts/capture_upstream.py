"""Record the exact upstream reference; downloads data only, never executes upstream code."""

import hashlib
import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "campaign-planner-reference-audit"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


if __name__ == "__main__":
    try:
        commit = json.loads(fetch("https://api.github.com/repos/langchain-ai/deepagents/commits/main"))
        sha = commit["sha"]
    except urllib.error.HTTPError as exc:
        if exc.code != 403:
            raise
        # Anonymous GitHub API rate limits do not apply to read-only Git refs.
        result = subprocess.run(
            ["git", "ls-remote", "https://github.com/langchain-ai/deepagents.git", "refs/heads/main"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        sha = result.stdout.split()[0]
    files = {}
    for name in [
        "README.md",
        "content_writer.py",
        "AGENTS.md",
        "pyproject.toml",
        "skills/blog-post/SKILL.md",
    ]:
        path = "examples/content-builder-agent/" + name
        content = fetch(f"https://raw.githubusercontent.com/langchain-ai/deepagents/{sha}/{path}")
        files[path] = {
            "sha256": hashlib.sha256(content).hexdigest(),
            "url": f"https://github.com/langchain-ai/deepagents/blob/{sha}/{path}",
        }
    license_text = fetch(f"https://raw.githubusercontent.com/langchain-ai/deepagents/{sha}/LICENSE")
    (ROOT / "docs/upstream-LICENSE.txt").write_bytes(license_text)
    reference = dict(
        repository="https://github.com/langchain-ai/deepagents",
        commit=sha,
        files=files,
        note="Reference only; the upstream application is not vendored or executed.",
    )
    (ROOT / "docs/upstream-source.json").write_text(json.dumps(reference, indent=2) + "\n", encoding="utf-8")
    print("Captured upstream commit " + sha)
