---
name: hermes-tweet
description: Use when the user wants Hermes Agent to explore, read, summarize, or draft gated actions for X/Twitter through the Hermes Tweet plugin.
---

# Hermes Tweet

Use this skill for Hermes Agent workflows that need X/Twitter exploration,
tweet or profile reading, social research, or drafted actions that remain
explicitly gated until the user enables them.

## Workflow

1. Confirm the task is about X/Twitter research, reading, drafting, or
   account-aware social workflow support.
2. Install or inspect Hermes Tweet from
   `https://github.com/Xquik-dev/hermes-tweet`.
3. Require `XQUIK_API_KEY` before read tools are used.
4. Treat exploration as safe by default: `tweet_explore` must not require a
   network key and must not perform writes.
5. Keep write-like behavior gated: action tools require
   `HERMES_TWEET_ENABLE_ACTIONS=true` in addition to the API key.
6. Return concise evidence: query used, accounts or tweets inspected, key
   findings, and any drafted action for user approval.

## Guardrails

- Do not claim a tweet was posted unless the action tool reports success.
- Do not expose API keys, cookies, account tokens, or private runtime details.
- Prefer summaries and links over copying large tweet or profile payloads.
- If credentials or action gates are missing, explain the missing setting and
  continue with read-free planning where possible.
