# Make Execution Digests Conditional

Every `/ultra solve` run should perform a Pre-Implementation Checkpoint after claim and before implementation edits, but it should write an Execution Digest only when the note changes future execution, delegation, recovery, or review. This keeps the planning behavior predictable while avoiding no-op tracker notes and stale sediment on simple ready-for-agent tickets.
