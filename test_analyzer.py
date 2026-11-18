import unittest
import os
from pathlib import Path
from parser import parse_log_file
from parser import parse_log_line
from analyzer import analyze_log_entries, parse_external_entity_data, parse_sql_write

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

    def _analyze_lines(self, lines):
        entries = [parse_log_line(line, line_number=i) for i, line in enumerate(lines, 1)]
        return analyze_log_entries(entries)["all_entries"]

    def test_field_changes_track_last_known_value(self):
        entries = self._analyze_lines([
            '2026-08-19 09:00:00 U1 insert rezepte {"id":"R1","diagnose":"A","tp_therapiebericht":null}',
            # Feld taucht auf, Wert unverändert -> keine Änderung
            '2026-08-19 09:01:00 U1 update rezepte id {"id":"R1","tp_therapiebericht":null,"status":"1"}',
            # Teil-Update ohne das Feld -> keine Änderung am Feld
            '2026-08-19 09:02:00 U1 update rezepte id {"id":"R1","diagnose":"B"}',
            '2026-08-19 09:03:00 U1 update rezepte id {"id":"R1","tp_therapiebericht":"Bericht"}',
            '2026-08-19 09:04:00 U1 update rezepte id {"id":"R1","tp_therapiebericht":"Bericht"}',
            '2026-08-19 09:05:00 U1 update rezepte id {"id":"R1","tp_therapiebericht":null}',
            # Anderer Datensatz, Vorwert unbekannt
            '2026-08-19 09:06:00 U1 update rezepte id {"id":"R2","tp_therapiebericht":"X","diagnose":null}',
        ])
        changes = [e["changes"] for e in entries]
        self.assertEqual(changes[0], {"diagnose": {"kind": "initial"}})
        self.assertEqual(changes[1], {"status": {"kind": "set"}})
        self.assertEqual(changes[2], {"diagnose": {"kind": "changed", "old": "A"}})
        self.assertEqual(changes[3], {"tp_therapiebericht": {"kind": "changed", "old": None}})
        self.assertEqual(changes[4], {})
        self.assertEqual(changes[5], {"tp_therapiebericht": {"kind": "changed", "old": "Bericht"}})
        self.assertEqual(changes[6], {"tp_therapiebericht": {"kind": "set"}})

    def test_sql_update_is_parsed_as_field_write(self):
        entries = self._analyze_lines([
            '2026-08-19 09:00:00 U1 insert events {"id":"E1","title":"Alt","abgerechnet":null}',
            '2026-08-19 09:01:00 U1 encexec {"sql":"\\nupdate events set title=:title, abgerechnet=true where id=:id and parentevent_id is null\\n","params":{"id":"E1","title":"Neu"}}',
            '2026-08-19 09:02:00 U1 encexec {"sql":"update events set patient= :patient where patient_id= :patient_id","params":{"patient":"Max","patient_id":"P1"}}',
            '2026-08-19 09:03:00 U1 encdelete {"sql":"Delete from events where id=:id","params":{"id":"E1"}}',
        ])
        self.assertEqual(entries[1]["sql_write"], {"table": "events", "id": "E1", "fields": {"title": "Neu", "abgerechnet": True}})
        self.assertEqual(entries[1]["changes"], {
            "title": {"kind": "changed", "old": "Alt"},
            "abgerechnet": {"kind": "changed", "old": None},
        })
        # Kein 'where id=...' -> Felder bekannt, aber kein einzelner Datensatz
        self.assertIsNone(entries[2]["sql_write"]["id"])
        self.assertEqual(entries[2]["changes"], {})
        self.assertNotIn("sql_write", entries[3])
        self.assertNotIn("changes", entries[3])

        expr = parse_sql_write({"action": "encexec", "payload": {
            "sql": "UPDATE rechnung SET status = 'Gemahnt: ' || to_char(current_date, 'DD.MM.YYYY'), x = NULL where id= :id",
            "params": {"id": "R9"}}})
        self.assertEqual(expr["id"], "R9")
        self.assertEqual(list(expr["fields"]), ["status", "x"])
        self.assertIsNone(expr["fields"]["x"])

if __name__ == '__main__':
    unittest.main()
