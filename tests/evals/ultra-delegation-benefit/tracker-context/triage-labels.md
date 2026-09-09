# Triage Labels

The skills use five canonical triage roles. Local Markdown stores the corresponding value in the Ticket's `Status:` line.

| Canonical role | Local status | Meaning |
| --- | --- | --- |
| `needs-triage` | `needs-triage` | Maintainer evaluation is required. |
| `needs-info` | `needs-info` | Core information is missing. |
| `ready-for-agent` | `ready-for-agent` | The Ticket is approved for AFK execution. |
| `ready-for-human` | `ready-for-human` | A human-owned decision or action is required. |
| `wontfix` | `wontfix` | The Ticket will not be actioned. |

Ultra additionally uses `completed` as the verified-candidate terminal Ticket state and `solve-in-progress` as a temporary Claim flag. Neither changes the five canonical triage roles.
