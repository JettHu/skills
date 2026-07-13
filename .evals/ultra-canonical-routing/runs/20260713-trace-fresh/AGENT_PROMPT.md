# Fresh-session task

For every scenario, execute the requested route as a real `/ultra <target>` run: read only the supplied `skill-input/skills/engineering/ultra/SKILL.md` and `PROFILES.md`, then invoke the installed target skill when it is available. The fixture deliberately excludes its grader and expected results. Do not modify this prompt, `contract-manifest.json`, `scenarios.json`, `TASK.md`, or `APPROVED_CONTEXT.md`.

Every output belongs in its existing directory under `<fixture-root>/scenarios/<scenario-id>/`; do not create a top-level `<fixture-root>/<scenario-id>/` directory. Write `routing-decision.json` there after each run with exactly `requested_route`, `resolved_profile`, `contract_sha256`, `code`, `research`, `review`, `human_choice`, `review_iterations`, and `evidence`. Copy `contract_sha256` from the manifest. `evidence` must contain the relevant verbatim profile row and condition or bridge rule from the supplied runbook/profile input.

For `05-review-fix`, apply the full review-fix loop to that scenario's `artifact.md` against its read-only `APPROVED_CONTEXT.md`: repair all derivable defects, re-review the repaired artifact, and record two review iterations in the routing decision.

For `06-human-owned-choice`, write `escalation.json` in that scenario directory describing the unresolved release-owner choice and do not create an invented Ticket or blocker edge.

When complete, do not run a grader.
