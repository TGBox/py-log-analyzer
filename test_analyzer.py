import unittest
import os
from parser import parse_log_file
from analyzer import analyze_log_entries

class TestLogAnalyzer(unittest.TestCase):
    def setUp(self):
        self.sample_path = r"c:\Users\droesch\Documents\Programmiertes\py-log-analyzer\sample.log"

    def test_parse_sample_log(self):
        entries = parse_log_file(self.sample_path)
        self.assertEqual(len(entries), 441, f"Expected 441 entries, got {len(entries)}")

        analysis = analyze_log_entries(entries)
        timeline = analysis["timeline"]
        entity_index = analysis["entity_index"]
        
        self.assertGreater(len(timeline), 0)
        self.assertGreater(len(entity_index), 0)

        # Check for nested JSON unpacking in line 142 (update rezepte)
        rezepte_entry = None
        for entry in entries:
            if entry.get("table") == "rezepte" and isinstance(entry.get("payload"), dict):
                rechnung = entry["payload"].get("rechnung")
                if isinstance(rechnung, dict):
                    rezepte_entry = entry
                    break
        
        self.assertIsNotNone(rezepte_entry, "Nested JSON in 'rezepte.rechnung' should be auto-decoded to dict")

        # Check anomaly detection
        has_float_anomaly = False
        has_null_param = False
        for entry in analysis["all_entries"]:
            for anom in entry.get("anomalies", []):
                if anom["type"] == "float_precision":
                    has_float_anomaly = True
                if anom["type"] == "null_sql_param":
                    has_null_param = True
        
        print(f"Sample analysis complete. Clustered Timeline items: {len(timeline)} (from {len(entries)} raw).")
        print(f"Entities indexed: {len(entity_index)} unique IDs.")
        print(f"Float precision anomalies found: {has_float_anomaly}")
        print(f"Null SQL params found: {has_null_param}")

if __name__ == '__main__':
    unittest.main()
