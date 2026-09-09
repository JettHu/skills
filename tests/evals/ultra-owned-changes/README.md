# Untracked-only review evidence

`scenario.py prepare --output <fresh-directory> --source <checkout>` creates an
isolated Git repository, a pre-existing user file, pinned Ultra input copies, and
a tiny target stub. Run the generated `prompt.txt` with a real Agent in `repo/`,
saving the model/runtime settings and raw tool transcript outside that repo.
Then run `scenario.py grade --output <directory>`.

The grader checks reviewer coverage against the actual file hash, unchanged user
content, unchanged tracked/index state and Git HEAD, and unchanged skill inputs.
Also inspect the tool transcript to confirm the review artifact was produced by
an actual reviewer (or an explicitly recorded serial capability fallback), not
merely written by the coordinator. This is a bounded review-selection scenario,
not a full TDD adherence or multi-model comparison. Failed model runs remain
local evidence; deterministic CI uses `tests/ultra-owned-changes.py` and requires
no historical `.evals/` output or model access.
