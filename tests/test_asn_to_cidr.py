from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "helpers"))
from asn_to_cidr import load_asn_rules, load_asns


class AsnRuleTests(unittest.TestCase):
    def test_signed_entries_comments_duplicates_and_conflicts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "ASN.txt"
            path.write_text("# rules\n\nAS64500 # include\n-AS64501 # exclude\nAS64502\n-AS64502\n-AS64501\n")
            self.assertEqual(load_asn_rules(path), ({64500, 64502}, {64501, 64502}))
            self.assertEqual(load_asns(path), {64500})


if __name__ == "__main__":
    unittest.main()
