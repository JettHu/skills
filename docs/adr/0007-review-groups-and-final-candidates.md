# Review Groups and Final Candidates

`/ultra solve` should keep group review close to each group branch and add a Post-Execution Review on the integrated candidate after final validation and before solve-record finalization. Group review catches local spec and standards problems while fixes are cheap; Post-Execution Review checks the final candidate for cross-group coupling, unhandled Execution Digest risks, Agent Decision Log completeness, side effects, regressions, and validation gaps before the candidate becomes a solve record.

Post-Execution Review should not create a standalone durable artifact by default. Findings should be fixed directly when possible; only state-relevant residue remains durable: manual merge or acceptance caveats go into the solve record, and blockers that prevent a finished candidate go back to the ticket.
