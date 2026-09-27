import unittest
import os
from pathlib import Path
from parser import parse_log_file
from analyzer import analyze_log_entries, parse_external_entity_data

class TestLogAnalyzer(unittest.TestCase):
    def setUp(self):
        self.sample_path = str(Path(__file__).parent / "sample.log")

    def test_parse_sample_log(self):
        entries = parse_log_file(self.sample_path)
        self.assertGreater(len(entries), 0, f"Expected entries, got {len(entries)}")

        analysis = analyze_log_entries(entries)
        timeline = analysis["timeline"]
        entity_index = analysis["entity_index"]
        entity_names = analysis["entity_names"]
        
        self.assertGreater(len(timeline), 0)
        self.assertGreater(len(entity_index), 0)

        # Check entity name resolution if present
        if "6KCRE-MRANHX" in entity_names:
            print(f"Resolved entity name: 6KCRE-MRANHX -> {entity_names['6KCRE-MRANHX']}")

        # 2. Check for nested JSON unpacking in line 142 (update rezepte)
        rezepte_entry = None
        for entry in entries:
            if entry.get("table") == "rezepte" and isinstance(entry.get("payload"), dict):
                rechnung = entry["payload"].get("rechnung")
                if isinstance(rechnung, dict):
                    rezepte_entry = entry
                    break
        
        self.assertIsNotNone(rezepte_entry, "Nested JSON in 'rezepte.rechnung' should be auto-decoded to dict")

        # 3. Check anomaly detection
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
        print(f"Entity names mapped: {len(entity_names)} resolved names.")

    def test_external_entity_import(self):
        csv_data = "id;p_vname;p_name\nTEST-ID-123;Max;Mustermann"
        parsed_csv = parse_external_entity_data(csv_data, filename="test.csv")
        self.assertEqual(parsed_csv.get("TEST-ID-123"), "Max Mustermann")

        json_data = '{"TEST-ID-456": "Erika Mustermann"}'
        parsed_json = parse_external_entity_data(json_data, filename="test.json")
        self.assertEqual(parsed_json.get("TEST-ID-456"), "Erika Mustermann")

if __name__ == '__main__':
    unittest.main()
