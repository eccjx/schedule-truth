def parse_gtfs_time(value: str) -> int:
    parts = value.split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid GTFS time: {value!r}")

    hours, minutes, seconds = parts

    if any(
        not part or any(char not in "0123456789" for char in part)
        for part in parts
    ):
        raise ValueError(f"Invalid GTFS time: {value!r}")

    if len(minutes) != 2 or len(seconds) != 2:
        raise ValueError(f"Invalid GTFS time: {value!r}")

    hours, minutes, seconds = int(hours), int(minutes), int(seconds)

    if minutes > 59 or seconds > 59:
        raise ValueError(f"Invalid GTFS time: {value!r}")

    return hours * 3600 + minutes * 60 + seconds