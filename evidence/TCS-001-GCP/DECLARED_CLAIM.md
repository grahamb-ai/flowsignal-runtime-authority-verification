# TCS-001-GCP — Declared Claim and Falsifier

## Declared claim

For requests submitted through the frozen candidate's
`POST /authority/final-bind` boundary, movements sharing the same authoritative
capacity key are atomically reserved against one durable aggregate.

The boundary MUST NOT reserve a movement, or issue an execution permit for it,
when:

`reserved burden + proposed burden > authoritative capacity`

For the frozen challenge:

- shared capacity: `C = 10`
- movement A: `M_A = 6`
- movement B: `M_B = 6`
- combined burden: `M = 12`
- remaining capacity: `Phi = C - M = -2`

The deployed GCP run uses the dimensionally equivalent values:

- authoritative capacity: `1,000,000`
- movement A: `600,000`
- movement B: `600,000`

## Falsification criteria

The declared claim is falsified if, within one authoritative capacity scope:

1. both 600,000 movements obtain capacity reservations;
2. both movements obtain execution permits;
3. the durable reserved total exceeds 1,000,000;
4. replay of one execution identity consumes capacity twice; or
5. an altered request reusing an existing execution identity obtains a new
   reservation or execution permit.

## Actual boundary

The tested boundary is `POST /authority/final-bind`. A successful atomic
reservation is required before an execution permit is minted. A refused
movement receives no reservation and no execution permit.

This claim is deliberately bounded to the FlowSignal final-bind and permit
boundary. It does not claim external financial settlement, physical
non-formation outside routes governed by this boundary, production
certification, or universal mathematical sufficiency.

