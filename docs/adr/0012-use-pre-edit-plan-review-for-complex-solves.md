# Use Pre-Edit Plan Review For Complex Solves

Complex, delegated, resumable, or digest-worthy `/ultra solve` runs should review the compressed plan before implementation edits for omitted steps, unhandled risks, missing validation, and unsafe assumptions. When subagents are available, this Pre-Edit Plan Review should default to a read-only planning reviewer subagent so critique context stays out of the main thread; the main agent folds findings into the plan or Execution Digest and keeps final execution responsibility.
