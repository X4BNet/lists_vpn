#!/usr/bin/env python3
"""Compare address coverage of two builds, independent of CIDR segmentation."""

from __future__ import annotations

import argparse
import ipaddress
import json
from collections import Counter
from pathlib import Path

from network_ranges import merge, size, subtract, write_ranges


def load(path: Path, family: int) -> tuple[list[tuple[int, int]], dict]:
    networks = [ipaddress.ip_network(line) for line in path.read_text().splitlines() if line.strip()]
    if any(network.version != family for network in networks):
        raise ValueError(f"wrong address family in {path}")
    ranges = merge([(int(network.network_address), int(network.broadcast_address)) for network in networks])
    return ranges, {
        "cidrs": len(networks), "addresses": size(ranges),
        "prefix_lengths": dict(sorted(Counter(network.prefixlen for network in networks).items())),
    }


def compare(baseline: Path, candidate: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    results = {}
    for category in ("vpn", "datacenter"):
        for family in (4, 6):
            name = f"{category}/ipv{family}.txt"
            old, old_stats = load(baseline / name, family)
            new, new_stats = load(candidate / name, family)
            added, removed = subtract(new, old), subtract(old, new)
            common = size(old) - size(removed)
            results[name] = {
                "baseline": old_stats, "candidate": new_stats,
                "added_addresses": size(added), "removed_addresses": size(removed),
                "common_addresses": common,
                "net_change_percent": (size(new) / size(old) - 1) * 100 if size(old) else None,
                "baseline_retained_percent": common / size(old) * 100 if size(old) else None,
            }
            for label, ranges in (("added", added), ("removed", removed)):
                write_ranges(output / f"{category}-ipv{family}-{label}.txt", ranges, family)
    (output / "comparison.json").write_text(json.dumps(results, indent=2) + "\n")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    for name, result in compare(args.baseline, args.candidate, args.output_dir).items():
        print(f"{name}: {result['baseline']['addresses']:,} -> {result['candidate']['addresses']:,}; "
              f"+{result['added_addresses']:,} / -{result['removed_addresses']:,} addresses")


if __name__ == "__main__":
    main()
