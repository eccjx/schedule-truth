"""Continuous polling with a monotonic deadline and isolated network reception."""

import argparse
import math
from pathlib import Path
import signal
import threading
from urllib.parse import urlsplit

from schedule_truth.collect_vehicle_positions import _poll_vehicle_positions, recover_started_requests
from schedule_truth.vehicle_positions_ownership import own_archive


def run_vehicle_positions(url: str, root: Path, interval_seconds: float = 15,
                          timeout: float = 30, max_response_bytes: int = 10 * 1024 * 1024,
                          stop_event=None, request_deadline_seconds: float = 120):
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise ValueError('A complete HTTP or HTTPS URL is required.')
    if not math.isfinite(interval_seconds) or interval_seconds < 0:
        raise ValueError('interval_seconds must be finite and nonnegative.')
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout must be finite and positive.')
    if type(max_response_bytes) is not int or max_response_bytes < 0:
        raise ValueError('max_response_bytes must be a nonnegative integer.')
    if not math.isfinite(request_deadline_seconds) or request_deadline_seconds <= 0:
        raise ValueError('request_deadline_seconds must be finite and positive.')
    if stop_event is None:
        stop_event = threading.Event()
    with own_archive(root):
        recover_started_requests(root)
        while not stop_event.is_set():
            _poll_vehicle_positions(url, root, timeout, max_response_bytes, request_deadline_seconds)
            if stop_event.wait(interval_seconds):
                break


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--interval-seconds', type=float, default=15)
    parser.add_argument('--timeout', type=float, default=30)
    parser.add_argument('--request-deadline-seconds', type=float, default=120)
    parser.add_argument('--max-response-bytes', type=int, default=10 * 1024 * 1024)
    args = parser.parse_args()
    stop = threading.Event()

    def request_stop(signum, frame):
        stop.set()

    previous = {}
    try:
        for name in ('SIGINT', 'SIGTERM', 'SIGBREAK'):
            if hasattr(signal, name):
                number = getattr(signal, name)
                previous[number] = signal.signal(number, request_stop)
        try:
            run_vehicle_positions(args.url, args.root, args.interval_seconds, args.timeout,
                                  args.max_response_bytes, stop, args.request_deadline_seconds)
        except (RuntimeError, OSError) as error:
            parser.exit(1, f'{error}\n')
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


if __name__ == '__main__':
    main()
