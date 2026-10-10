# TCS-001-GCP — Preserved Result

## Sequential deployed run

| Movement | Burden | Decision | Reservation | Execution permit |
| --- | ---: | --- | --- | --- |
| A | 600,000 | ALLOW | issued | issued |
| B | 600,000 | REFUSE | not issued | not issued |

Movement B reason code: `COUPLED_CAPACITY_EXCEEDED`.

The durable aggregate remained `600,000` against authoritative capacity
`1,000,000`.

## Replay

An identical replay of movement A returned
`CAPACITY_RESERVATION_IDEMPOTENT`. It retained the same reservation identity,
store version `1`, and durable aggregate `600,000`.

## Mutation

Changing movement A's amount while reusing its execution identity returned
`EXECUTION_ID_CONFLICT`. No new permit was issued and the aggregate remained
`600,000`.

## Concurrent deployed run

Two 600,000 requests were submitted simultaneously to the Cloud Run candidate
while two instances were warm and request concurrency was configured to one.
Exactly one request received `ALLOW`; the other received
`COUPLED_CAPACITY_EXCEEDED`. Firestore recorded one reservation and aggregate
version `1` with reserved total `600,000`.

The evidence proves atomic enforcement through the tested final-bind and
permit boundary. It does not prove which individual Cloud Run instance served
each request, external settlement non-formation, or independent reproduction.

## Container regression

The two TCS-001 test modules completed with:

```text
6 passed, 1 warning in 0.63s
```

The warning is a Starlette/httpx deprecation warning and did not affect the
test result.

