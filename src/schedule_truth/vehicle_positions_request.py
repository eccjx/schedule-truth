"""Isolated transport worker; never creates request records or payload identities."""

import json
from pathlib import Path
import sys
import time

from schedule_truth.collect_vehicle_positions import _receive_vehicle_positions
from schedule_truth.vehicle_positions_job import join_transport_job


if __name__ == '__main__':
    join_transport_job(sys.argv[5])
    result = _receive_vehicle_positions(sys.argv[1], Path(sys.argv[2]), float(sys.argv[3]),
                                       int(sys.argv[4]), worker=True)
    result['completed_monotonic'] = time.monotonic()
    print(json.dumps(result), flush=True)
