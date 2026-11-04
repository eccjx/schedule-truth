# Service Alerts collection

Install `requirements.txt` and run on Windows from the repository root:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -B -m schedule_truth.run_alerts --url https://cdn.mbta.com/realtime/Alerts.pb --root data/raw/alerts --interval-seconds 60 --timeout 30 --request-deadline-seconds 120 --max-response-bytes 10485760
```

Use a dedicated Alerts archive root. The runner acquires single-writer ownership before checking the root and recovering unfinished requests. It polls immediately after recovery, then waits 60 seconds after each successful or failed poll. All displayed limits and the interval are configurable. Results are persisted per poll without accumulating a results list.

Ctrl+C prevents further polls. The active request keeps its original monotonic network deadline; the 30-second socket timeout is an inactivity limit. Worker cleanup, parsing, and disk writes can extend total exit time beyond the network deadline.

Compact `requests/<id>.json` records contain `feed_type: service_alerts`, URL, request/receipt/finish times, status/error, and payload details when complete. Exact complete bodies are retained at `payloads/<sha256>/response.pb`. Complete malformed or HTTP-error bodies remain failed evidence. Incomplete, timed-out, and oversized bodies have a failed request with partial staging size and no payload identity; oversized responses also retain the observed count, which can exceed the staged size. Partial staging is discarded. Startup marks earlier started requests interrupted with unknown outcome and their observed partial size, then polls under a new ID.

Feed timestamps are source creation times; alert active periods are source display intervals. All periods and missing bounds remain in the Protobuf, without per-alert JSON arrays or disruption/trip-outcome claims. Identical payloads may be shared by distinct requests; existing replay and conflict rules remain unchanged.

Direct calls to `poll_alerts` or `persist_alerts_response` require the caller to hold archive ownership, as the runner does. This first slice does not establish live feed health, sustained operation, cross-host ownership, clean installation, or general crash/power-loss repair.
