#!/usr/bin/env python3
"""Stream IPtoASN TSV data into CIDR lists and validate generated output.

The builder keeps orchestration in Bash.  This helper contains the IP-address
math so an IPtoASN database is scanned once per address family rather than
once for every ASN.
"""

from __future__ import annotations

import argparse
import ipaddress
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import TextIO


ASN_PATTERN = re.compile(r"AS(\d+)$")


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def load_asns(path: Path) -> set[int]:
    """Read AS<number> values, preserving the legacy behavior of ignoring junk."""
    asns: set[int] = set()
    with path.open(encoding="utf-8") as source:
        for line_number, raw_line in enumerate(source, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            match = ASN_PATTERN.fullmatch(line.split(maxsplit=1)[0])
            if match:
                asns.add(int(match.group(1)))
            else:
                warn(f"ignoring invalid ASN entry at {path}:{line_number}")
    return asns


def open_output(path: Path | None) -> TextIO | None:
    if path is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("w", encoding="utf-8")


def expand_asns(args: argparse.Namespace) -> int:
    vpn_asns = load_asns(args.vpn_asns)
    datacenter_asns = load_asns(args.datacenter_asns) | vpn_asns

    vpn_output = open_output(args.vpn_output)
    datacenter_output = open_output(args.datacenter_output)
    try:
        with args.database.open(encoding="utf-8") as database:
            for line_number, raw_line in enumerate(database, start=1):
                columns = raw_line.rstrip("\n").split("\t")
                if len(columns) < 3:
                    if raw_line.strip():
                        warn(f"ignoring malformed database row at {args.database}:{line_number}")
                    continue

                try:
                    asn = int(columns[2])
                except ValueError:
                    warn(f"ignoring database row with invalid ASN at {args.database}:{line_number}")
                    continue

                write_vpn = vpn_output is not None and asn in vpn_asns
                write_datacenter = datacenter_output is not None and asn in datacenter_asns
                if not (write_vpn or write_datacenter):
                    continue

                try:
                    start = ipaddress.ip_address(columns[0])
                    end = ipaddress.ip_address(columns[1])
                    if start.version != args.family or end.version != args.family or int(start) > int(end):
                        raise ValueError("wrong address family or descending range")
                except ValueError as error:
                    warn(f"ignoring invalid database range at {args.database}:{line_number}: {error}")
                    continue

                for network in ipaddress.summarize_address_range(start, end):
                    if write_vpn:
                        print(network, file=vpn_output)
                    if write_datacenter:
                        print(network, file=datacenter_output)
    finally:
        if vpn_output is not None:
            vpn_output.close()
        if datacenter_output is not None:
            datacenter_output.close()
    return 0


def input_tokens(paths: Iterable[Path]) -> Iterable[tuple[Path, int, str]]:
    for path in paths:
        with path.open(encoding="utf-8") as source:
            for line_number, raw_line in enumerate(source, start=1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                yield path, line_number, line.split(maxsplit=1)[0]


def normalize(args: argparse.Namespace) -> int:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for path, line_number, token in input_tokens(args.inputs):
        try:
            network = ipaddress.ip_network(token, strict=False)
        except ValueError as error:
            warn(f"ignoring invalid network at {path}:{line_number}: {error}")
            continue
        if network.version != args.family:
            warn(f"ignoring wrong-family network at {path}:{line_number}: {token}")
            continue
        networks.append(network)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as destination:
        for network in ipaddress.collapse_addresses(networks):
            print(network, file=destination)
    return 0


def validate(args: argparse.Namespace) -> int:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for path, line_number, token in input_tokens([args.input]):
        try:
            network = ipaddress.ip_network(token, strict=False)
        except ValueError as error:
            raise ValueError(f"invalid output network at {path}:{line_number}: {error}") from error
        if network.version != args.family:
            raise ValueError(f"wrong-family output network at {path}:{line_number}: {token}")
        networks.append(network)

    if args.require_nonempty and not networks:
        raise ValueError(f"output is empty: {args.input}")

    if args.family == 4:
        forbidden = (ipaddress.ip_network("0.0.0.0/8"), ipaddress.ip_network("127.0.0.0/8"))
    else:
        forbidden = (ipaddress.ip_network("::1/128"), ipaddress.ip_network("fe80::/10"))

    for network in networks:
        for forbidden_network in forbidden:
            if network.overlaps(forbidden_network):
                raise ValueError(f"output contains prohibited range: {network}")

    address_count = sum(network.num_addresses for network in networks)
    if args.min_addresses is not None and address_count < args.min_addresses:
        raise ValueError(f"too few addresses covered ({address_count})")
    if args.max_addresses is not None and address_count > args.max_addresses:
        raise ValueError(f"too many addresses covered ({address_count})")

    print(f"validated {len(networks)} networks covering {address_count} addresses")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    expand = commands.add_parser("expand-asns", help="stream a TSV once and emit selected ASN CIDRs")
    expand.add_argument("--family", type=int, choices=(4, 6), required=True)
    expand.add_argument("--database", type=Path, required=True)
    expand.add_argument("--vpn-asns", type=Path, required=True)
    expand.add_argument("--datacenter-asns", type=Path, required=True)
    expand.add_argument("--vpn-output", type=Path)
    expand.add_argument("--datacenter-output", type=Path)
    expand.set_defaults(handler=expand_asns)

    normalize_command = commands.add_parser("normalize", help="canonicalize CIDRs for one address family")
    normalize_command.add_argument("--family", type=int, choices=(4, 6), required=True)
    normalize_command.add_argument("--output", type=Path, required=True)
    normalize_command.add_argument("inputs", type=Path, nargs="+")
    normalize_command.set_defaults(handler=normalize)

    validate_command = commands.add_parser("validate", help="validate generated CIDRs and optional coverage bounds")
    validate_command.add_argument("--family", type=int, choices=(4, 6), required=True)
    validate_command.add_argument("--input", type=Path, required=True)
    validate_command.add_argument("--require-nonempty", action="store_true")
    validate_command.add_argument("--min-addresses", type=int)
    validate_command.add_argument("--max-addresses", type=int)
    validate_command.set_defaults(handler=validate)

    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return args.handler(args)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
