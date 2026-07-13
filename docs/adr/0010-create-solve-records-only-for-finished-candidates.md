# Create Outcome Records at Meaningful Attempt Boundaries

`/ultra solve` should create a candidate Solve Record whenever a finished, reviewable candidate exists, even if human acceptance, merge review, rollout approval, or another manual gate is still required. A meaningful stopped Attempt creates an outcome-aware recovery receipt with the findings, blocker, and retained-resource context needed to resume. A fully cleaned transient Attempt remains recordless.
