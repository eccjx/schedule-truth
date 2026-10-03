# Vehicle Positions continuous runner contract

Status: author-accepted Vehicle Positions continuous runner slice, 2026-10-02. Implementation, independent tests, and review passed in the working tree; the code is not yet committed. This extends the [first collection slice](vehicle-positions-first-slice.md); it does not change its request, payload, or timestamp meanings. This is not Phase 2 milestone acceptance.

## Normal operation

- One runner owns an archive root at a time. A second runner targeting that root exits with a clear ownership error and does not start a request. Different roots may be used independently. The implementation must release ownership on normal exit and avoid treating a leftover marker from a crashed process as a live owner; the locking mechanism is an implementation detail to review.
- On startup, run the existing reconciliation for prior `started` requests. Start a new poll immediately afterward. The new request gets a new request ID.
- Poll sequentially. Wait 15 seconds **after a request finishes** before starting the next one. A slow request never overlaps another. The interval is configurable, with 15 seconds as the default.
- A failed poll is recorded under its own request ID. Wait the same 15 seconds, then try again. No additional backoff or rapid retry in this first runner. A later success resumes the same cadence. Failure does not imply absent vehicle service.
- Persist each poll before moving to the next. Do not retain an ever-growing list of results in memory. Keep only the current response and small runner state. Historical request and payload records remain on disk.

## Size limit and stopping

- Default maximum HTTP response body: 10 MiB (10 * 1024 * 1024 bytes), configurable. Stop reading as soon as the body exceeds the limit. Record `response_too_large` and the observed byte count on that request. Discard its partial staging bytes; create no content hash, immutable payload, or valid snapshot from the truncated body. A body at or below the limit follows the first-slice contract, including retention of complete malformed or HTTP-error bodies.
- On a normal stop request, do not start another poll. If a request is active, allow it to finish or fail within its total request deadline, persist its outcome, then exit and release ownership. If stopping during the inter-poll wait, exit without another request.
- Default total request deadline: 120 seconds from request start, configurable. Measure elapsed duration with a monotonic clock; keep UTC request and finish timestamps as separate evidence. The existing socket timeout only limits inactivity during socket operations and does not replace this deadline. The deadline must still work when a server keeps sending small pieces or a network operation blocks.
- If the deadline expires before a complete response arrives, save the request as failed with reason `request_deadline_exceeded`, the observed partial byte count, and a finish time. Discard partial staging bytes; create no payload hash, immutable payload, or valid snapshot. A normal stop request does not reset or extend the request's deadline.
- A crash or forced termination is distinct from normal shutdown. On restart, mark a prior `started` request `interrupted` with its outcome unknown, following the first-slice contract. This does not claim recovery from every power-loss or storage-failure window.

## Examples

| Event | Next action |
| --- | --- |
| Poll finishes at 10:00:02 | Next poll begins at 10:00:17. |
| Poll fails at 10:00:02 | Persist failure; next poll begins at 10:00:17. |
| Stop requested during a poll | Finish or time out that poll, persist its result, and exit without another poll. |
| A response sends small pieces for more than 120 seconds | Stop that request at its total deadline, record `request_deadline_exceeded` and the partial byte count, discard partial bytes, then continue the normal polling cadence unless shutdown was requested. |
| Runner restarts after a crash | Reconcile prior `started` attempts, acquire sole ownership, then poll immediately. |

## Review boundary

The contract does not establish clean dependency installation, stored-payload tamper detection, general crash recovery, or service freshness. Independent deadline tests and review passed with 151 full-suite tests. The verified deadline stops network reception; process cleanup, decoding, and storage may extend shutdown. The sustained memory checks are accelerated local tests, not a long-running live-network soak.
