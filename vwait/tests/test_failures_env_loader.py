from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vwait.features.failures.integrations.jira.env_loader import read_env_file


def test_failure_env_loader_supports_export_quotes_and_comments(tmp_path):
    env_file = tmp_path / ".env.jira"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                "export JIRA_BASE_URL=https://jira.exemplo.com",
                'JIRA_EMAIL="qa@example.com"',
                "JIRA_API_TOKEN=abc123",
            ]
        ),
        encoding="utf-8",
    )

    data = read_env_file(env_file)

    assert data["JIRA_BASE_URL"] == "https://jira.exemplo.com"
    assert data["JIRA_EMAIL"] == "qa@example.com"
    assert data["JIRA_API_TOKEN"] == "abc123"

