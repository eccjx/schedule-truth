# Running Vehicle Positions collection

The continuous runner currently supports Windows. Install `requirements.txt` in your Python environment, then run from the repository root in PowerShell:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -B -m schedule_truth.run_vehicle_positions --url https://cdn.mbta.com/realtime/VehiclePositions.pb --root data/raw/vehicle_positions --interval-seconds 15 --timeout 30 --request-deadline-seconds 120 --max-response-bytes 10485760
```

These are the default interval, socket timeout, total request deadline, and response limit. The URL and root are required. Press Ctrl+C or Ctrl+Break for graceful shutdown. A stop during a request allows reception only until its original deadline, then persists the outcome; a stop during the wait exits immediately without another poll. Forced termination instead leaves startup recovery to mark unfinished requests interrupted.

The 120-second deadline uses elapsed monotonic time from request start, including initial record persistence and worker startup. The runner receives network data in a child process and terminates it when the remaining deadline expires, even during DNS, connection setup, blocked headers/reads, or slow-drip responses. The socket inactivity timeout remains independent. Ctrl+C never resets the original deadline. A Windows kill-on-close job also terminates the network worker if the runner exits or crashes.

Deadline expiry records `request_deadline_exceeded`, a UTC finish time, and `observed_size_bytes`/`partial_staging_size_bytes` counted from the staging file after worker termination. It discards staging and creates no payload identity or valid snapshot. This counts application-observed body bytes, not bytes still buffered inside the network stack or HTTP decoder.

This is not a hard real-time shutdown guarantee. Windows process creation/termination and scheduling, initial/final metadata writes, staging operations, parsing, and other storage operations can outlive the deadline. Worker termination is given an additional five-second cleanup wait; inability to terminate or persist raises instead of claiming a finalized failure. The finite collector retains its original socket-timeout-only interface. Complete-response decoding and persistence in the runner happen after network reception and are not forcibly terminated at the deadline.

The runner acquires a Windows global named mutex keyed by the normalized, resolved archive path before recovery or any archive writes. A second runner, including the finite collector, exits with an ownership error. Ownership is released on exit or abandoned by Windows after process termination. Different roots are independent. The lock is local to this machine; do not share an archive root between machines. Non-Windows ownership is not implemented.

Polling is sequential, immediately after recovery and then after a completion-to-start delay. Results stay in `requests/<id>.json`; complete bytes stay in `payloads/<hash>/response.pb`. The runner does not build a history list. The response limit counts bytes actually read, requesting at most one byte beyond the remaining allowance. Oversized bodies finish as failed with `error: response_too_large` and `observed_size_bytes`; partial staging is discarded without a hash or payload identity. Complete bodies at or below the limit keep the existing collector behavior.

No freshness or missing-service conclusions follow from successful or failed polls. Existing payload trust and unresolved power-loss/storage-error recovery limits remain. Disk usage grows with persisted requests and unique payloads; retention/deletion is not implemented.
