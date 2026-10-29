"""Integer interval operations shared by ASN exclusions and build comparisons."""

from __future__ import annotations

import ipaddress
from pathlib import Path


def merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def subtract(left: list[tuple[int, int]], right: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Subtract sorted, disjoint inclusive intervals in linear time."""
    result: list[tuple[int, int]] = []
    index = 0
    for start, end in left:
        while index < len(right) and right[index][1] < start:
            index += 1
        cursor = index
        while cursor < len(right) and right[cursor][0] <= end:
            other_start, other_end = right[cursor]
            if other_start > start:
                result.append((start, other_start - 1))
            start = max(start, other_end + 1)
            if start > end:
                break
            cursor += 1
        if start <= end:
            result.append((start, end))
        index = cursor
    return result


def size(ranges: list[tuple[int, int]]) -> int:
    return sum(end - start + 1 for start, end in ranges)


def write_ranges(path: Path, ranges: list[tuple[int, int]], family: int) -> None:
    address = ipaddress.IPv4Address if family == 4 else ipaddress.IPv6Address
    with path.open("w") as destination:
        for start, end in ranges:
            for network in ipaddress.summarize_address_range(address(start), address(end)):
                print(network, file=destination)


