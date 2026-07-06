#!/usr/bin/env python3
"""Create a PR for the environments feature branch."""

import json
import urllib.request

with open("/opt/data/.github_token") as f:
    token = f.read().strip()

data = json.dumps(
    {
        "title": "feat: first-class environments in project.toml ([environments.*]) — #27",
        "head": "feat/environments-in-project-toml",
        "base": "main",
        "body": (
            "## Summary\n\n"
            "Implements first-class environment support in project.toml via [environments.*] sections. Closes #27.\n\n"
            "## Changes\n\n"
            "- **t4t/engine/config.py**: DatabaseConfigManager with env_name parameter to load from [environments.<name>]\n"
            "- **t4t/cli/utils.py**: load_project_config with env_name parameter\n"
            "- **t4t/cli/context.py**: CommandContext with env parameter\n"
            "- **tests/test_environments.py**: 15 new tests covering environments, legacy compat, and error cases\n\n"
            "## Design\n\n"
            "Environments are defined as TOML tables under [environments.<name>] with:\n"
            "- [environments.<name>.connection] — database connection config\n"
            "- [environments.<name>.variables] — env-specific variables\n"
            "- protected — boolean flag for production environments\n\n"
            "Legacy [connection] section continues to work when no --env is specified."
        ),
    }
).encode()

req = urllib.request.Request(
    "https://api.github.com/repos/francescomucio/tee-for-transform/pulls",
    data=data,
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "hermes-agent",
    },
)

with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read())
    print(f"PR #{result['number']} created: {result['html_url']}")
    print(f"PR number: {result['number']}")
