# FS-CCA-001 — Frozen Claim and Falsifier

## Frozen proposition

If authority changes after preparation but before final bind, an attempted
continuation using the prior authority must be refused, no execution permit may
issue, and no protected consequence may form.

The tested artifact is commit
`6341c6c267e567d48a4873859b9101c9e74ca978` on branch
`challenge/fs-cca-001-constitutional-revocation`.

## Observable pass conditions

1. Unchanged current authority reaches final bind, receives a bound execution
   permit, and forms exactly one represented protected consequence.
2. A prepared operation followed by a competent authority-fence transition is
   blocked at final bind with `AUTHORITY_CONTEXT_CHANGED`.
3. The blocked path receives no execution permit.
4. Repeating the stale prepared operation remains blocked.
5. Mutation of the protected operation is independently classified as
   `PROTECTED_OPERATION_CHANGED` rather than being relabelled as revocation.
6. If authority changes after permit mint but before consequence formation, the
   protected boundary denies the stale authority snapshot and no represented
   protected consequence forms.

## Falsification criteria

The frozen proposition is falsified if a prepared operation can cross final
bind after the tested authority transition, if a permit is minted for that
blocked bind, or if the protected consequence is recorded as formed.

## Bounded scope

This is a reference-harness claim about the tested FlowSignal final-bind and
protected-consequence path. It does not establish production certification,
external settlement non-formation, crash/restart persistence of the in-memory
authority fence, distributed atomicity, or universal constitutional legitimacy.

