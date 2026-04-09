from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_TEST_LABEL = "agentleman-jira-live-test"


def main() -> None:
    """Delete Jira issues created by the live integration tests.

    This script is intentionally separate from the main workflow so the team can
    clean test artifacts on demand without coupling cleanup behavior to incident
    handling.
    """
    args = _parse_args()
    _load_root_env()

    client = _build_client()
    jql = f'project = "{client.config.project_key}" AND labels = "{args.label}" ORDER BY created DESC'
    issues = client.search_issues(
        jql=jql,
        fields=["summary", "status"],
        max_results=args.max_results,
        request_id="jira-clean-search",
    )

    if not issues:
        print("No Jira test issues matched the cleanup query.")
        return

    print(f"Found {len(issues)} Jira issues matching cleanup label '{args.label}'.")
    for issue in issues:
        issue_key = issue["key"]
        summary = issue.get("fields", {}).get("summary", "")
        status_name = issue.get("fields", {}).get("status", {}).get("name", "unknown")
        if args.dry_run:
            print(f"[dry-run] Would delete {issue_key} [{status_name}] {summary}")
            continue
        client.delete_issue(
            issue_key=issue_key,
            request_id=f"jira-clean-delete-{issue_key}",
            delete_subtasks=args.delete_subtasks,
        )
        print(f"Deleted {issue_key} [{status_name}] {summary}")


def _parse_args() -> argparse.Namespace:
    """Read CLI options for the Jira cleanup script."""
    parser = argparse.ArgumentParser(description="Delete Jira issues created by live integration tests.")
    parser.add_argument(
        "--label",
        default=DEFAULT_TEST_LABEL,
        help="Jira label used to find test issues.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=100,
        help="Maximum number of matching Jira issues to inspect.",
    )
    parser.add_argument(
        "--delete-subtasks",
        action="store_true",
        help="Delete subtasks as well when Jira requires it.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List matching issues without deleting them.",
    )
    return parser.parse_args()


def _load_root_env() -> None:
    """Load the repository root `.env` file so cleanup uses the same Jira credentials as the app."""
    env_path = Path(__file__).resolve().parents[4] / ".env"
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def _build_client() -> Any:
    """Create the Jira client after the backend root bootstrap is in place."""
    from src.services.jira.client import JiraClient, JiraConfig

    return JiraClient(JiraConfig.from_env())


if __name__ == "__main__":
    main()