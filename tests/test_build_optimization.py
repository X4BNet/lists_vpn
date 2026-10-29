from __future__ import annotations

import argparse
import contextlib
import io
import ipaddress
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
import asn_to_cidr as helper


class BuildOptimizationTests(unittest.TestCase):
    def test_interval_normalization_matches_stdlib_collapse(self) -> None:
        random_source = random.Random(42)
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "input.txt", Path(directory) / "output.txt"
            for family, parent in ((4, "192.0.2.0/24"), (6, "2001:db8::/120")):
                parent = ipaddress.ip_network(parent)
                width = parent.max_prefixlen
                # Include host bits, duplicate networks, overlaps, comments, and
                # invalid/wrong-family manual entries accepted by the old reader.
                tokens = [f"{parent.network_address + random_source.randrange(256)}/{random_source.randrange(width - 5, width + 1)}"
                          for _ in range(100)]
                tokens += tokens[:10]
                source.write_text("# fixture\n\n" + "\n".join(tokens) + "\ninvalid\n" +
                                  ("2001:db8::/32\n" if family == 4 else "192.0.2.0/24\n"))
                with contextlib.redirect_stderr(io.StringIO()):
                    helper.normalize(argparse.Namespace(family=family, output=output, inputs=[source]))
                expected = list(ipaddress.collapse_addresses(ipaddress.ip_network(token, strict=False) for token in tokens))
                self.assertEqual(output.read_text(), "".join(f"{network}\n" for network in expected))

    def test_combined_expansion_reads_csv_once_and_matches_separate_families(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            vpn_asns, dc_asns = directory / "vpn.txt", directory / "datacenter.txt"
            vpn_asns.write_text("AS64500\n-AS64599\n")
            dc_asns.write_text("AS64502\n-AS64598\n")
            vpn_keywords, dc_keywords = directory / "vpn-keywords.txt", directory / "datacenter-keywords.txt"
            vpn_keywords.write_text("VPN\n-Example\n")
            dc_keywords.write_text("Company\n-example\n")
            database = directory / "ip-to-asn.csv"
            # Interleaved families, reordered columns, a BOM, and CSV metadata
            # containing commas/newlines must not affect routing to the outputs.
            database.write_text(
                '\ufefforg,asn,network\n"Example, Inc.",64500,2001:0DB8:0000::/62\n'
                'example,64599,10.0.1.0/24\nexample,64500,10.0.0.0/22\n'
                '"Example\nCompany",64598,2001:db8:0:1::/65\n'
                'example,64502,192.0.2.0/24\nexample,64599,2001:db8:1::/64\n'
                'My VPN,64600,198.18.0.0/24\nMy VPN,64600,2001:db8:2::/64\n'
            )
            combined = directory / "combined"
            args = argparse.Namespace(database=database, vpn_asns=vpn_asns, datacenter_asns=dc_asns,
                                      output_dir=combined, family="all", list="all",
                                      vpn_keywords=vpn_keywords, datacenter_keywords=dc_keywords)
            with patch.object(helper, "open_iplocate", wraps=helper.open_iplocate) as opened:
                helper.expand_iplocate(args)
            self.assertEqual(opened.call_count, 1)
            for family in (4, 6):
                paths = {name: directory / f"{family}-{name}.txt" for name in (
                    "vpn_output", "datacenter_output", "vpn_exclusions_output", "datacenter_exclusions_output")}
                helper.expand_asns(argparse.Namespace(database=database, database_source="iplocate", family=family,
                                                     vpn_asns=vpn_asns, datacenter_asns=dc_asns,
                                                     vpn_keywords=vpn_keywords, datacenter_keywords=dc_keywords, **paths))
                for category in ("vpn", "datacenter"):
                    for suffix, argument in (("asn", "output"), ("exclusions", "exclusions_output")):
                        self.assertEqual((combined / f"{category}-ipv{family}-{suffix}.txt").read_bytes(),
                                         paths[f"{category}_{argument}"].read_bytes())
            for family in ("ipv4", "ipv6"):
                for category in ("vpn", "datacenter"):
                    with self.subTest(family=family, category=category):
                        args.family, args.list = family, category
                        args.output_dir = directory / f"{category}-{family}-only"
                        helper.expand_iplocate(args)
                        names = {f"{category}-{family}-{suffix}.txt" for suffix in ("asn", "exclusions")}
                        self.assertEqual({path.name for path in args.output_dir.iterdir()}, names)
                        for name in names:
                            self.assertEqual((args.output_dir / name).read_bytes(), (combined / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
