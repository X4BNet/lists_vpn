#!/usr/bin/env python3
"""Stream ASN databases into CIDR lists and validate generated output.

The builder keeps orchestration in Bash. This helper handles address math and
selects all requested ASNs in one pass per database, including both families
when using the combined IPLocate CSV.
"""

from __future__ import annotations

import argparse
import csv
import io
import ipaddress
import re
import sys
import zipfile
from collections.abc import Iterable, Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import TextIO

from network_ranges import merge, subtract, write_ranges


ASN_PATTERN = re.compile(r"(-?)AS(\d+)$")


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def load_asn_rules(path: Path) -> tuple[set[int], set[int]]:
    """Read AS<number> includes and -AS<number> exclusions."""
    included: set[int] = set()
    excluded: set[int] = set()
    with path.open(encoding="utf-8") as source:
        for line_number, raw_line in enumerate(source, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            match = ASN_PATTERN.fullmatch(line.split(maxsplit=1)[0])
            if match:
                target = excluded if match.group(1) else included
                target.add(int(match.group(2)))
            else:
                warn(f"ignoring invalid ASN entry at {path}:{line_number}")
    return included, excluded


def load_asns(path: Path) -> set[int]:
    included, excluded = load_asn_rules(path)
    return included - excluded


def load_keyword_rules(path: Path | None) -> tuple[set[str], set[str]]:
    """Read literal, case-insensitive substrings; '-' marks an exclusion."""
    included: set[str] = set()
    excluded: set[str] = set()
    if path is None:
        return included, excluded
    with path.open(encoding="utf-8") as source:
        for line_number, raw_line in enumerate(source, start=1):
            keyword = raw_line.split("#", 1)[0].strip()
            if not keyword:
                continue
            target = included
            if keyword.startswith("-"):
                target = excluded
                keyword = keyword[1:].strip()
            if not keyword:
                raise ValueError(f"empty keyword exclusion at {path}:{line_number}")
            target.add(keyword.casefold())
    return included, excluded


def open_output(path: Path | None) -> TextIO | None:
    if path is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("w", encoding="utf-8")


@contextmanager
def open_iplocate(path: Path) -> Iterator[TextIO]:
    """Read the single CSV member directly, without extracting the archive."""
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = [name for name in archive.namelist() if name.endswith(".csv")]
            if len(members) != 1:
                raise ValueError("IPLocate archive must contain exactly one CSV member")
            with archive.open(members[0]) as source:
                with io.TextIOWrapper(source, encoding="utf-8-sig", newline="") as database:
                    yield database
    else:
        with path.open(encoding="utf-8-sig", newline="") as database:
            yield database


def iplocate_networks(path: Path, wanted: set[int], keywords: set[str] | None = None
                     ) -> Iterator[tuple[int, ipaddress.IPv4Network | ipaddress.IPv6Network, set[str]]]:
    with open_iplocate(path) as database:
        rows = csv.reader(database, strict=True)
        header = next(rows, [])
        if not {"network", "asn"}.issubset(header):
            raise ValueError("IPLocate CSV requires network and asn columns")
        network_column, asn_column = header.index("network"), header.index("asn")
        metadata_columns = [header.index(field) for field in ("name", "org", "domain") if field in header]
        if keywords and not metadata_columns:
            raise ValueError("IPLocate keyword rules require name, org, or domain columns")
        for row in rows:
            if not row:
                continue
            try:
                asn = int(row[asn_column])
            except (IndexError, ValueError) as error:
                raise ValueError(f"invalid IPLocate ASN at {path}:{rows.line_num}") from error
            matches: set[str] = set()
            if keywords:
                try:
                    metadata = [row[column].casefold() for column in metadata_columns]
                except IndexError as error:
                    raise ValueError(f"missing IPLocate metadata at {path}:{rows.line_num}") from error
                matches = {keyword for keyword in keywords if any(keyword in value for value in metadata)}
            if asn not in wanted and not matches:
                continue
            try:
                network = ipaddress.ip_network(row[network_column])
            except (IndexError, TypeError, ValueError) as error:
                raise ValueError(f"invalid IPLocate network at {path}:{rows.line_num}") from error
            yield asn, network, matches


def database_networks(args: argparse.Namespace, wanted: set[int]) -> Iterator[tuple[int, ipaddress.IPv4Network | ipaddress.IPv6Network]]:
    """Yield selected ASN networks; selected parent ranges remain included."""
    if args.database_source == "iplocate":
        for asn, network, _ in iplocate_networks(args.database, wanted):
            if network.version == args.family:
                yield asn, network
        return

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
            if asn not in wanted:
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
                yield asn, network


def expand_asns(args: argparse.Namespace) -> int:
    vpn_included, vpn_excluded = load_asn_rules(args.vpn_asns)
    datacenter_included, datacenter_excluded = load_asn_rules(args.datacenter_asns)
    # Includes are inherited; exclusions are scoped to the file's category.
    datacenter_included |= vpn_included
    vpn_keywords, vpn_keyword_exclusions = load_keyword_rules(getattr(args, "vpn_keywords", None))
    dc_keywords, dc_keyword_exclusions = load_keyword_rules(getattr(args, "datacenter_keywords", None))
    rules = (
        (vpn_included, vpn_keywords, args.vpn_output),
        (datacenter_included, dc_keywords | vpn_keywords, args.datacenter_output),
        (vpn_excluded, vpn_keyword_exclusions, args.vpn_exclusions_output),
        (datacenter_excluded, dc_keyword_exclusions, args.datacenter_exclusions_output),
    )
    with ExitStack() as stack:
        outputs = []
        wanted: set[int] = set()
        keywords: set[str] = set()
        for asns, terms, path in rules:
            if path is not None:
                outputs.append((asns, terms, stack.enter_context(open_output(path))))
                wanted |= asns
                keywords |= terms
        if args.database_source == "iplocate":
            records = iplocate_networks(args.database, wanted, keywords)
        else:
            records = ((asn, network, set()) for asn, network in database_networks(args, wanted))
        for asn, network, matches in records:
            if network.version != args.family:
                continue
            line = f"{network}\n"
            for asns, terms, output in outputs:
                if asn in asns or matches & terms:
                    output.write(line)
    return 0


def expand_iplocate(args: argparse.Namespace) -> int:
    """Route both families and explicit exclusions from one CSV scan."""
    vpn_included, vpn_excluded = load_asn_rules(args.vpn_asns)
    dc_included, dc_excluded = load_asn_rules(args.datacenter_asns)
    vpn_keywords, vpn_keyword_exclusions = load_keyword_rules(getattr(args, "vpn_keywords", None))
    dc_keywords, dc_keyword_exclusions = load_keyword_rules(getattr(args, "datacenter_keywords", None))
    rules = {
        "vpn": ((vpn_included, vpn_keywords), (vpn_excluded, vpn_keyword_exclusions)),
        "datacenter": ((dc_included | vpn_included, dc_keywords | vpn_keywords),
                       (dc_excluded, dc_keyword_exclusions)),
    }
    families = (4, 6) if args.family == "all" else (int(args.family[-1]),)
    categories = ("vpn", "datacenter") if args.list == "all" else (args.list,)
    with ExitStack() as stack:
        outputs: dict[int, dict[int, list[TextIO]]] = {family: {} for family in families}
        keyword_outputs: dict[int, dict[str, list[TextIO]]] = {family: {} for family in families}
        wanted: set[int] = set()
        keywords: set[str] = set()
        for family in families:
            for category in categories:
                for (asns, terms), suffix in zip(rules[category], ("asn", "exclusions")):
                    path = args.output_dir / f"{category}-ipv{family}-{suffix}.txt"
                    output = stack.enter_context(open_output(path))
                    wanted |= asns
                    keywords |= terms
                    for asn in asns:
                        outputs[family].setdefault(asn, []).append(output)
                    for keyword in terms:
                        keyword_outputs[family].setdefault(keyword, []).append(output)
        for asn, network, matches in iplocate_networks(args.database, wanted, keywords):
            destinations = set(outputs.get(network.version, {}).get(asn, ()))
            for keyword in matches:
                destinations.update(keyword_outputs.get(network.version, {}).get(keyword, ()))
            if destinations:
                line = f"{network}\n"
                for output in destinations:
                    output.write(line)
    return 0


def exclude_ranges(args: argparse.Namespace) -> int:
    def read_ranges(path: Path) -> list[tuple[int, int]]:
        ranges = []
        for source, line_number, token in input_tokens([path]):
            network = ipaddress.ip_network(token)
            if network.version != args.family:
                raise ValueError(f"wrong-family network at {source}:{line_number}: {token}")
            ranges.append((int(network.network_address), int(network.broadcast_address)))
        return merge(ranges)

    included = read_ranges(args.input)
    excluded = read_ranges(args.exclusions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_ranges(args.output, subtract(included, excluded), args.family)
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
    ranges: list[tuple[int, int]] = []
    width = 32 if args.family == 4 else 128
    for path, line_number, token in input_tokens(args.inputs):
        try:
            network = ipaddress.ip_network(token, strict=False)
        except ValueError as error:
            warn(f"ignoring invalid network at {path}:{line_number}: {error}")
            continue
        if network.version != args.family:
            warn(f"ignoring wrong-family network at {path}:{line_number}: {token}")
            continue
        start = int(network.network_address)
        ranges.append((start, start | ((1 << (width - network.prefixlen)) - 1)))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_ranges(args.output, merge(ranges), args.family)
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

    expand = commands.add_parser("expand-asns", help="stream an ASN database and emit selected CIDRs")
    expand.add_argument("--family", type=int, choices=(4, 6), required=True)
    expand.add_argument("--database", type=Path, required=True)
    expand.add_argument("--database-source", choices=("iptoasn", "iplocate"), default="iptoasn")
    expand.add_argument("--vpn-asns", type=Path, required=True)
    expand.add_argument("--datacenter-asns", type=Path, required=True)
    expand.add_argument("--vpn-keywords", type=Path)
    expand.add_argument("--datacenter-keywords", type=Path)
    expand.add_argument("--vpn-output", type=Path)
    expand.add_argument("--datacenter-output", type=Path)
    expand.add_argument("--vpn-exclusions-output", type=Path)
    expand.add_argument("--datacenter-exclusions-output", type=Path)
    expand.set_defaults(handler=expand_asns)

    combined = commands.add_parser("expand-iplocate", help="select both families from one CSV pass")
    combined.add_argument("--family", choices=("ipv4", "ipv6", "all"), default="all")
    combined.add_argument("--list", choices=("vpn", "datacenter", "all"), default="all")
    combined.add_argument("--database", type=Path, required=True)
    combined.add_argument("--vpn-asns", type=Path, required=True)
    combined.add_argument("--datacenter-asns", type=Path, required=True)
    combined.add_argument("--vpn-keywords", type=Path)
    combined.add_argument("--datacenter-keywords", type=Path)
    combined.add_argument("--output-dir", type=Path, required=True)
    combined.set_defaults(handler=expand_iplocate)

    exclude = commands.add_parser("exclude", help="subtract explicit ASN ranges from a completed list")
    exclude.add_argument("--family", type=int, choices=(4, 6), required=True)
    exclude.add_argument("--input", type=Path, required=True)
    exclude.add_argument("--exclusions", type=Path, required=True)
    exclude.add_argument("--output", type=Path, required=True)
    exclude.set_defaults(handler=exclude_ranges)

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
    except (OSError, ValueError, csv.Error, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
