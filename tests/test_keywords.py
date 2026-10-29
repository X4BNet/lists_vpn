from __future__ import annotations

import csv
import ipaddress
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "helpers"))
from asn_to_cidr import load_keyword_rules


class KeywordTests(unittest.TestCase):
    def test_keyword_files_support_phrases_comments_casefold_and_negation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="lists-vpn-keywords-", dir="/tmp") as directory:
            path = Path(directory) / "Keywords.txt"
            path.write_text("# rules\n\nVPN # include\nvPn\nHoSt\n- Example VPN # exclude\nVPN+\n")
            self.assertEqual(load_keyword_rules(path), ({"vpn", "host", "vpn+"}, {"example vpn"}))
            self.assertEqual(load_keyword_rules(None), (set(), set()))
            path.write_text("- # an empty exclusion must not match every entry\n")
            with self.assertRaisesRegex(ValueError, "empty keyword exclusion"):
                load_keyword_rules(path)

    def test_keyword_selection_and_exclusions_in_full_and_partial_builds(self) -> None:
        with tempfile.TemporaryDirectory(prefix="lists-vpn-keywords-", dir="/tmp") as directory:
            directory = Path(directory)
            inputs, databases = directory / "input", directory / "database"
            databases.mkdir()
            for category in ("vpn", "datacenter"):
                folder = inputs / category
                (folder / "ips").mkdir(parents=True)
                (folder / "ASN.txt").write_text("AS64500\nAS64606\n" if category == "vpn" else "-AS64605\n")
                (folder / "Keywords.txt").write_text("VPN\n-BlockedVPN\n" if category == "vpn" else "Host\n-BlockedHost\n")
                # Explicit exclusions must also override these manual includes.
                (folder / "ips/Manual.txt").write_text("198.18.1.0/24\n198.18.2.0/24\n")
                (folder / "ips/Manual-ipv6.txt").write_text("2001:db8:0:1::/64\n2001:db8:0:2::/64\n")
            with (databases / "ip-to-asn.csv").open("w", newline="") as database:
                writer = csv.writer(database)
                # Reordered columns and quoted comma/newline metadata.
                writer.writerow(["org", "domain", "country_code", "network", "name", "asn"])
                for parent, child1, child2, extra in (
                    ("198.18.0.0/22", "198.18.1.0/24", "198.18.2.0/25", "198.19.0.0/24"),
                    ("2001:db8::/62", "2001:db8:0:1::/64", "2001:db8:0:2::/65", "2001:db8:1::/64"),
                ):
                    writer.writerow(["Plain", "example.test", "ZZ", parent, "PLAIN", 64500])
                    writer.writerow(["BlockedVPN", "example.test", "ZZ", child1, "PLAIN", 64590])
                    writer.writerow(["Plain", "blockedhost.example", "ZZ", child2, "PLAIN", 64591])
                    network = ipaddress.ip_network(extra)
                    address = type(network.network_address)
                    for offset, asn, name, org, domain, country in (
                        (0, 64601, "MyVpNService", "Plain", "example.test", "ZZ"),
                        (1, 64601, "PLAIN", "Plain", "example.test", "VPN"),
                        (2, 64602, "PLAIN", "Best, HoSting\nLtd", "example.test", "ZZ"),
                        (3, 64603, "PLAIN", "Plain", "vpn.example", "ZZ"),
                        (4, 64604, "HOST-NET", "BlockedHost, Ltd", "example.test", "ZZ"),
                        (5, 64605, "HOST-NET", "Plain", "example.test", "ZZ"),
                        (6, 64606, "BlockedVPN", "Plain", "example.test", "ZZ"),
                    ):
                        prefix = f"{address(int(network.network_address) + offset * network.num_addresses)}/{network.prefixlen}"
                        writer.writerow([org, domain, country, prefix, name, asn])

            expected = {
                ("vpn", 4): ["198.18.0.0/24", "198.18.2.0/23", "198.19.0.0/24", "198.19.3.0/24"],
                ("datacenter", 4): ["198.18.0.0/23", "198.18.2.128/25", "198.18.3.0/24",
                                    "198.19.0.0/24", "198.19.2.0/23", "198.19.6.0/24"],
                ("vpn", 6): ["2001:db8::/64", "2001:db8:0:2::/63", "2001:db8:1::/64", "2001:db8:1:3::/64"],
                ("datacenter", 6): ["2001:db8::/63", "2001:db8:0:2:8000::/65", "2001:db8:0:3::/64",
                                    "2001:db8:1::/64", "2001:db8:1:2::/63", "2001:db8:1:6::/64"],
            }
            for family, category in (("all", "all"), ("ipv4", "vpn"), ("ipv6", "datacenter")):
                with self.subTest(family=family, category=category):
                    output = directory / f"{family}-{category}"
                    subprocess.run(
                        ["bash", str(ROOT / "build-local.sh"), "--database-source", "iplocate",
                         "--database-dir", str(databases), "--input-dir", str(inputs), "--output-dir", str(output),
                         "--family", family, "--list", category],
                        check=True, capture_output=True, text=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                    )
                    emitted = set()
                    for (item_category, item_family), tokens in expected.items():
                        if category not in ("all", item_category) or family not in ("all", f"ipv{item_family}"):
                            continue
                        path = output / item_category / f"ipv{item_family}.txt"
                        emitted.add(path.relative_to(output).as_posix())
                        actual = path.read_text().splitlines()
                        self.assertEqual(list(ipaddress.collapse_addresses(map(ipaddress.ip_network, actual))),
                                         list(ipaddress.collapse_addresses(map(ipaddress.ip_network, tokens))))
                    actual_paths = {path.relative_to(output).as_posix() for path in output.glob("*/*.txt")}
                    self.assertEqual(actual_paths, emitted)
                    if (output / "ipv4.txt").exists():
                        self.assertEqual((output / "ipv4.txt").read_bytes(), (output / "datacenter/ipv4.txt").read_bytes())

    def test_keyword_metadata_errors_fail_without_publishing_lists(self) -> None:
        cases = (
            ("network,asn\n198.18.0.0/24,64500\n", "require name, org, or domain"),
            ("network,asn,org\n198.18.0.0/24,64500\n", "missing IPLocate metadata"),
        )
        for data, error in cases:
            with self.subTest(error=error), tempfile.TemporaryDirectory(prefix="lists-vpn-keywords-", dir="/tmp") as directory:
                directory = Path(directory)
                (directory / "ip-to-asn.csv").write_text(data)
                (directory / "vpn/ips").mkdir(parents=True)
                (directory / "datacenter/ips").mkdir(parents=True)
                for category in ("vpn", "datacenter"):
                    (directory / category / "ASN.txt").write_text("AS64500\n")
                (directory / "vpn/Keywords.txt").write_text("VPN\n")
                output = directory / "output"
                result = subprocess.run(
                    ["bash", str(ROOT / "build-local.sh"), "--database-source", "iplocate",
                     "--database-dir", str(directory), "--input-dir", str(directory), "--output-dir", str(output)],
                    capture_output=True, text=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(error, result.stderr)
                self.assertEqual(list(output.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
