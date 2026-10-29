from __future__ import annotations

import os
import ipaddress
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
BUILD = ROOT / "build-local.sh"
HELPER = ROOT / "helpers" / "asn_to_cidr.py"
CLEANUP = ROOT / "helpers" / "cleanup.pl"


class BuildListTests(unittest.TestCase):
    maxDiff = None

    def run_build(self, output_dir: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "bash",
                str(BUILD),
                "--output-dir",
                str(output_dir),
                "--database-dir",
                str(FIXTURES / "database"),
                "--input-dir",
                str(FIXTURES / "input"),
                *arguments,
            ],
            check=True,
            capture_output=True,
            text=True,
            env={**os.environ, "LC_ALL": "C"},
        )

    def assert_fixture_output(self, generated: Path, expected: Path) -> None:
        self.assertEqual(generated.read_bytes(), expected.read_bytes(), generated)

    def legacy_ipv4_output(self, raw_asn: Path, category: str, temporary_directory: Path) -> Path:
        """Run the pre-modernization IPv4 cleanup stages against fixture data."""
        compacted = subprocess.run(
            ["perl", str(CLEANUP), str(raw_asn)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        asn_networks = [
            network
            for network in compacted
            if network.rsplit("/", maxsplit=1)[1].isdigit()
            and int(network.rsplit("/", maxsplit=1)[1]) <= 24
        ]

        manual_networks: list[str] = []
        manual_dir = FIXTURES / "input" / category / "ips"
        for source in sorted(manual_dir.glob("*.txt")):
            if "ipv6" in source.name.lower():
                continue
            for line in source.read_text(encoding="utf-8").splitlines():
                if line and not line.startswith("#"):
                    manual_networks.append(line.split(maxsplit=1)[0])

        combined = temporary_directory / f"legacy-{category}-combined.txt"
        combined.write_text("\n".join(sorted(asn_networks + manual_networks)) + "\n", encoding="utf-8")
        output = temporary_directory / f"legacy-{category}-ipv4.txt"
        with output.open("w", encoding="utf-8") as destination:
            subprocess.run(["perl", str(CLEANUP), str(combined)], check=True, stdout=destination)
        return output

    def test_dual_stack_build_matches_byte_for_byte_ipv4_fixtures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory) / "output"
            result = self.run_build(output_dir)

            self.assertIn("ignoring invalid network", result.stderr)
            for category in ("vpn", "datacenter"):
                self.assert_fixture_output(
                    output_dir / category / "ipv4.txt",
                    FIXTURES / "expected" / category / "ipv4.txt",
                )
                self.assert_fixture_output(
                    output_dir / category / "ipv6.txt",
                    FIXTURES / "expected" / category / "ipv6.txt",
                )

            self.assert_fixture_output(output_dir / "ipv4.txt", FIXTURES / "expected" / "datacenter" / "ipv4.txt")
            self.assertFalse((output_dir / "ipv6.txt").exists())

    def test_single_category_and_family_only_emit_requested_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory) / "output"
            self.run_build(output_dir, "--family", "ipv4", "--list", "vpn")

            self.assert_fixture_output(
                output_dir / "vpn" / "ipv4.txt",
                FIXTURES / "expected" / "vpn" / "ipv4.txt",
            )
            self.assertFalse((output_dir / "datacenter").exists())
            self.assertFalse((output_dir / "ipv4.txt").exists())
            self.assertFalse((output_dir / "vpn" / "ipv6.txt").exists())

    def test_ipv4_migration_fixture_matches_legacy_perl_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            raw_vpn = temporary_path / "vpn-raw.txt"
            raw_datacenter = temporary_path / "datacenter-raw.txt"
            subprocess.run(
                [
                    "python3",
                    str(HELPER),
                    "expand-asns",
                    "--family",
                    "4",
                    "--database",
                    str(FIXTURES / "database" / "ip2asn-v4.tsv"),
                    "--vpn-asns",
                    str(FIXTURES / "input" / "vpn" / "ASN.txt"),
                    "--datacenter-asns",
                    str(FIXTURES / "input" / "datacenter" / "ASN.txt"),
                    "--vpn-output",
                    str(raw_vpn),
                    "--datacenter-output",
                    str(raw_datacenter),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            output_dir = temporary_path / "output"
            self.run_build(output_dir, "--family", "ipv4")
            for category, raw_asn in (("vpn", raw_vpn), ("datacenter", raw_datacenter)):
                legacy_output = self.legacy_ipv4_output(raw_asn, category, temporary_path)
                self.assertEqual(
                    (output_dir / category / "ipv4.txt").read_bytes(),
                    legacy_output.read_bytes(),
                    category,
                )

    def test_generated_fixture_outputs_pass_family_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory) / "output"
            self.run_build(output_dir)

            for family, filename in (("4", "ipv4.txt"), ("6", "ipv6.txt")):
                for category in ("vpn", "datacenter"):
                    subprocess.run(
                        [
                            "python3",
                            str(HELPER),
                            "validate",
                            "--family",
                            family,
                            "--input",
                            str(output_dir / category / filename),
                            "--require-nonempty",
                        ],
                        check=True,
                        capture_output=True,
                        text=True,
                    )

    def test_iplocate_csv_and_dated_zip_match_both_family_fixtures(self) -> None:
        for compressed in (False, True):
            with self.subTest(compressed=compressed), tempfile.TemporaryDirectory() as temporary_directory:
                temporary_path = Path(temporary_directory)
                database_dir = FIXTURES / "database"
                if compressed:
                    database_dir = temporary_path / "database"
                    database_dir.mkdir()
                    with zipfile.ZipFile(database_dir / "ip-to-asn.csv.zip", "w") as archive:
                        archive.write(FIXTURES / "database" / "ip-to-asn.csv", "ip-to-asn-20261028.csv")
                output_dir = temporary_path / "output"
                self.run_build(output_dir, "--database-source", "iplocate", "--database-dir", str(database_dir))
                for category in ("vpn", "datacenter"):
                    for filename in ("ipv4.txt", "ipv6.txt"):
                        self.assert_fixture_output(
                            output_dir / category / filename, FIXTURES / "expected" / category / filename,
                        )
                self.assert_fixture_output(output_dir / "ipv4.txt", output_dir / "datacenter" / "ipv4.txt")
                self.assertIn("IPLocate.io", (output_dir / "ASN-DATABASE.txt").read_text())

    def test_iplocate_rejects_invalid_databases_without_publishing_lists(self) -> None:
        cases = (
            ("network,wrong_column\n10.0.0.0/24,64500\n", "requires network and asn"),
            ("network,asn\n10.0.0.0/24,bad\n", "invalid IPLocate ASN"),
            ("network,asn\nbad,64500\n", "invalid IPLocate network"),
        )
        for content, error in cases:
            with self.subTest(error=error), tempfile.TemporaryDirectory() as temporary_directory:
                temporary_path = Path(temporary_directory)
                database_dir = temporary_path / "database"
                database_dir.mkdir()
                (database_dir / "ip-to-asn.csv").write_text(content)
                output_dir = temporary_path / "output"
                with self.assertRaises(subprocess.CalledProcessError) as caught:
                    self.run_build(output_dir, "--database-source", "iplocate", "--database-dir", str(database_dir))
                self.assertIn(error, caught.exception.stderr)
                self.assertEqual(list(output_dir.iterdir()), [])

    def test_default_source_downloads_iplocate_once_for_both_families(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            archive_path = temporary_path / "fixture.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.write(FIXTURES / "database" / "ip-to-asn.csv", "ip-to-asn-20261028.csv")
            curl = temporary_path / "curl"
            curl.write_text(
                '#!/usr/bin/env python3\n'
                'import os, pathlib, shutil, sys\n'
                'with open(os.environ["CURL_LOG"], "a") as log: log.write(sys.argv[-1] + "\\n")\n'
                'shutil.copyfile(os.environ["CURL_FIXTURE"], sys.argv[sys.argv.index("--output") + 1])\n'
            )
            curl.chmod(0o755)
            log = temporary_path / "curl.log"
            output_dir = temporary_path / "output"
            subprocess.run(
                ["bash", str(BUILD), "--output-dir", str(output_dir),
                 "--input-dir", str(FIXTURES / "input")],
                env={**os.environ, "PATH": f"{temporary_path}:{os.environ['PATH']}",
                     "CURL_LOG": str(log), "CURL_FIXTURE": str(archive_path)},
                check=True, capture_output=True, text=True,
            )
            self.assertEqual(log.read_text().splitlines(), [
                "https://media.githubusercontent.com/media/iplocate/ip-address-databases/main/ip-to-asn/ip-to-asn.csv.zip"
            ])
            self.assert_fixture_output(output_dir / "vpn" / "ipv6.txt", FIXTURES / "expected" / "vpn" / "ipv6.txt")

    def test_iplocate_selected_parents_include_unlisted_children(self) -> None:
        # Deliberately unordered, with both selected and unselected descendants.
        rows = (
            "10.0.1.0/25,64502\n10.0.1.0/24,64599\n10.0.0.0/22,64500\n"
            "192.0.2.0/25,64500\n192.0.2.0/24,64599\n"
            "2001:db8:0:1::/65,64502\n2001:db8:0:1::/64,64599\n2001:db8::/62,64500\n"
            "2001:db8:1::/65,64500\n2001:db8:1::/64,64599\n"
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            database = temporary_path / "ip-to-asn.csv"
            database.write_text("network,asn\n" + rows)
            for family, vpn_expected, extra_datacenter in (
                (4, ["10.0.0.0/22", "192.0.2.0/25"], "10.0.1.0/25"),
                (6, ["2001:db8::/62", "2001:db8:1::/65"], "2001:db8:0:1::/65"),
            ):
                outputs = {category: temporary_path / f"{category}-{family}.txt" for category in ("vpn", "datacenter")}
                subprocess.run(
                    ["python3", str(HELPER), "expand-asns", "--database-source", "iplocate",
                     "--family", str(family), "--database", str(database),
                     "--vpn-asns", str(FIXTURES / "input/vpn/ASN.txt"),
                     "--datacenter-asns", str(FIXTURES / "input/datacenter/ASN.txt"),
                     "--vpn-output", str(outputs["vpn"]), "--datacenter-output", str(outputs["datacenter"])],
                    check=True, capture_output=True, text=True,
                )
                for category, path in outputs.items():
                    expected = vpn_expected + ([extra_datacenter] if category == "datacenter" else [])
                    self.assertEqual(
                        list(ipaddress.collapse_addresses(map(ipaddress.ip_network, path.read_text().splitlines()))),
                        list(ipaddress.collapse_addresses(map(ipaddress.ip_network, expected))),
                    )

    def test_signed_asn_exclusions_override_parents_children_and_manual_inputs(self) -> None:
        rows = [
            ("10.0.0.0/22", 64500), ("10.0.1.0/24", 64599), ("10.0.1.0/25", 64500),
            ("10.0.2.0/25", 64598), ("10.0.3.0/24", 64577), ("192.0.2.0/24", 64502),
            ("2001:db8::/62", 64500), ("2001:db8:0:1::/64", 64599),
            ("2001:db8:0:1::/65", 64500), ("2001:db8:0:2::/65", 64598),
            ("2001:db8:0:3::/64", 64577), ("2001:db8:1::/64", 64502),
        ]
        expected = {
            ("vpn", 4): ["10.0.0.0/24", "10.0.2.0/23"],
            ("datacenter", 4): ["10.0.0.0/23", "10.0.2.128/25", "10.0.3.0/24", "192.0.2.0/24"],
            ("vpn", 6): ["2001:db8::/64", "2001:db8:0:2::/63"],
            ("datacenter", 6): ["2001:db8::/63", "2001:db8:0:2:8000::/65", "2001:db8:0:3::/64", "2001:db8:1::/64"],
        }
        for provider in ("iptoasn", "iplocate"):
            with self.subTest(provider=provider), tempfile.TemporaryDirectory() as temporary_directory:
                temporary_path = Path(temporary_directory)
                input_dir = temporary_path / "input"
                for category in ("vpn", "datacenter"):
                    directory = input_dir / category
                    (directory / "ips").mkdir(parents=True)
                    rules = "AS64500\nAS64599\n-AS64599 # explicit removal wins\n" if category == "vpn" else "AS64502\n-AS64598\n"
                    (directory / "ASN.txt").write_text(rules)
                    (directory / "ips/Manual.txt").write_text("10.0.1.0/24\n10.0.2.0/24\n")
                    (directory / "ips/Manual-ipv6.txt").write_text("2001:db8:0:1::/64\n2001:db8:0:2::/64\n")
                database_dir = temporary_path / "database"
                database_dir.mkdir()
                (database_dir / "ip-to-asn.csv").write_text("network,asn\n" + "".join(f"{network},{asn}\n" for network, asn in rows))
                for family in (4, 6):
                    with (database_dir / f"ip2asn-v{family}.tsv").open("w") as database:
                        for token, asn in rows:
                            network = ipaddress.ip_network(token)
                            if network.version == family:
                                print(f"{network.network_address}\t{network.broadcast_address}\t{asn}\tZZ\tfixture", file=database)
                output = temporary_path / "output"
                self.run_build(output, "--database-source", provider, "--database-dir", str(database_dir), "--input-dir", str(input_dir))
                for (category, family), networks in expected.items():
                    actual = (output / category / f"ipv{family}.txt").read_text().splitlines()
                    self.assertEqual(list(ipaddress.collapse_addresses(map(ipaddress.ip_network, actual))),
                                     list(ipaddress.collapse_addresses(map(ipaddress.ip_network, networks))))
                self.assert_fixture_output(output / "ipv4.txt", output / "datacenter/ipv4.txt")


if __name__ == "__main__":
    unittest.main()
