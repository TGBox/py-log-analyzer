import unittest
from pathlib import Path
from parser import parse_log_file
from analyzer import analyze_log_entries
from sql_engine import SQLEngine

class TestSQLEngine(unittest.TestCase):
    def setUp(self):
        self.sample_path = str(Path(__file__).parent / "sample.log")
        self.parsed = parse_log_file(self.sample_path)
        self.analysis = analyze_log_entries(self.parsed)
        self.engine = SQLEngine()
        self.engine.load_data(self.analysis["all_entries"], self.analysis["entity_names"])

    def tearDown(self):
        if hasattr(self, "engine") and self.engine.conn:
            self.engine.conn.close()

    def test_schema_and_tables(self):
        schema = self.engine.get_schema()
        tables = schema.get("tables", {})
        self.assertIn("logs", tables)
        self.assertIn("patienten", tables)
        self.assertIn("events", tables)

    def test_select_logs(self):
        res = self.engine.execute_query("SELECT count(*) FROM logs;")
        self.assertIsNone(res.get("error"))
        self.assertGreater(res["rows"][0][0], 0)

    def test_join_query(self):
        res = self.engine.execute_query("""
            SELECT logs.timestamp, patienten.p_name, logs.description 
            FROM logs 
            JOIN patienten ON logs.target_id = patienten.id 
            LIMIT 5;
        """)
        self.assertIsNone(res.get("error"))
        self.assertGreater(len(res["rows"]), 0)

    def test_dynamic_tables_carry_log_origin(self):
        res = self.engine.execute_query(
            "SELECT r._file_name, r._line_number, l.raw FROM rezepte r "
            "JOIN logs l ON l.file_name = r._file_name AND l.line_number = r._line_number "
            "WHERE r._action = 'insert';"
        )
        self.assertIsNone(res.get("error"))
        self.assertGreater(len(res["rows"]), 0)
        self.assertIn("insert rezepte", res["rows"][0][2])

    def test_field_changes_table(self):
        res = self.engine.execute_query(
            "SELECT kind, count(*) FROM field_changes GROUP BY kind ORDER BY kind;"
        )
        self.assertIsNone(res.get("error"))
        self.assertEqual([r[0] for r in res["rows"]], ["changed", "initial", "set"])

        res = self.engine.execute_query(
            "SELECT count(*) FROM field_changes fc "
            "JOIN logs l ON l.file_name = fc.file_name AND l.line_number = fc.line_number;"
        )
        total = self.engine.execute_query("SELECT count(*) FROM field_changes;")
        self.assertEqual(res["rows"][0][0], total["rows"][0][0])

    def test_update_insert_query(self):
        res_create = self.engine.execute_query("CREATE TABLE test_tab (id INT, val TEXT);")
        self.assertIsNone(res_create.get("error"))

        res_insert = self.engine.execute_query("INSERT INTO test_tab VALUES (1, 'Hello SQL');")
        self.assertIsNone(res_insert.get("error"))

        res_select = self.engine.execute_query("SELECT * FROM test_tab;")
        self.assertIsNone(res_select.get("error"))
        self.assertEqual(res_select["rows"][0][1], "Hello SQL")

if __name__ == '__main__':
    unittest.main()
