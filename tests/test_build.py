from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
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
            self.assert_fixture_output(output_dir / "ipv6.txt", FIXTURES / "expected" / "datacenter" / "ipv6.txt")

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


if __name__ == "__main__":
    unittest.main()
