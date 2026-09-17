# Existing Capabilities

Read when a proposed change introduces or reshapes a capability, interface,
data model, helper, or workflow, or when review finds overlapping responsibilities.
This reference supplies decision criteria; the calling workflow owns stage
scheduling, evidence ownership, and approved scope.

## Choose from repository evidence

Locate the nearest existing capability by business meaning, behavior, and call
paths, including differently named implementations. Reuse current evidence;
for a small local change, inspection of the relevant caller and nearby
implementation can be enough. Broaden the search only for a concrete unanswered
question.

Choose reuse, extension, extraction, or an independent implementation by comparing
shared meaning, contract differences, and total caller, maintenance, testing,
and migration cost. Consider only plausible alternatives. Ground a material
choice in code locations and the contracts that support it; if no counterpart
is found, state the bounded search and its result rather than claiming universal
absence.

Shared semantics and stable rules justify reuse. Similar syntax alone does not.
An independent implementation is appropriate when responsibilities or contracts
differ enough that sharing would distort them. Support cross-context abstraction
with actual consumers and their differences; a single current consumer does not
require a speculative framework or a second invented consumer.

Keep implementation choices within the approved contract. If consolidation
requires a material scope or architecture change, use the calling workflow's
existing decision or contract-amendment path. Carry forward an already approved
choice unless current evidence exposes a conflict or a material missing fact.

## Review the resulting responsibilities

Consume the design evidence and inspect the actual artifact or diff for duplicate
rules, parallel flows, overlapping models, or competing authorities. For a planned
replacement, verify which old path exits and which callers move; intentional
coexistence needs a clear responsibility boundary and, when transitional, an exit
condition. A renamed module or an added wrapper alone does not prove consolidation.

The check is complete when the implementation choice has proportionate repository
evidence and material overlaps are removed or justified within the approved
scope. Keep conclusions in the existing plan or review context; preserve only
material decisions through the workflow's existing durable record. This check
adds no mandatory report, approval stage, or independent review pass.
