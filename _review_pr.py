#!/usr/bin/env python3
"""Leave a review comment on PR #68."""

import json
import urllib.request

with open("/opt/data/.github_token") as f:
    token = f.read().strip()

with open("/opt/data/tee-for-transform/_review_body.md") as f:
    body = f.read()

data = json.dumps(
    {
        "event": "COMMENT",
        "body": body,
    }
).encode()

req = urllib.request.Request(
    "https://api.github.com/repos/francescomucio/tee-for-transform/pulls/68/reviews",
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
    print(f"Review submitted: id={result.get('id')}")
    print(f"State: {result.get('state')}")
