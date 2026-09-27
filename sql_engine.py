import sqlite3
import time
import json
import re

class SQLEngine:
    def __init__(self):
        self._init_db()

    def _init_db(self):
        if hasattr(self, "conn") and self.conn:
            self.conn.close()
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                line_number INTEGER,
                file_name TEXT,
                timestamp TEXT,
                user TEXT,
                action TEXT,
                table_name TEXT,
                target_id TEXT,
                description TEXT,
                raw TEXT
            );
        """)
        self.conn.commit()

    def load_data(self, parsed_entries, entity_names=None):
        """Populate in-memory SQLite DB with log entries and extracted entity tables."""
        self._init_db()
        cursor = self.conn.cursor()

        # 2. Populate logs table
        log_rows = []
        for entry in parsed_entries:
            log_rows.append((
                entry.get("line_number"),
                entry.get("file_name"),
                entry.get("timestamp"),
                entry.get("user"),
                entry.get("action"),
                entry.get("table"),
                entry.get("target_id"),
                entry.get("description"),
                entry.get("raw")
            ))

        cursor.executemany("""
            INSERT INTO logs (line_number, file_name, timestamp, user, action, table_name, target_id, description, raw)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, log_rows)

        # 3. Dynamically build tables for entities (e.g. patienten, events, rezepte, rechnung, rechpos)
        tables_data = {}

        def collect_payload(tbl_name, payload):
            if not isinstance(payload, dict) or not tbl_name:
                return
            
            tbl_name = re.sub(r'[^a-zA-Z0-9_]', '_', tbl_name.lower())
            if tbl_name not in tables_data:
                tables_data[tbl_name] = []
            
            row_dict = {}
            for k, v in payload.items():
                col_name = re.sub(r'[^a-zA-Z0-9_]', '_', k.lower())
                if isinstance(v, (dict, list)):
                    row_dict[col_name] = json.dumps(v, ensure_ascii=False)
                else:
                    row_dict[col_name] = v
            
            tables_data[tbl_name].append(row_dict)

        for entry in parsed_entries:
            table = entry.get("table")
            payload = entry.get("payload")
            if table and isinstance(payload, dict):
                collect_payload(table, payload)
                # Check nested objects like rechnung, patient
                if "rechnung" in payload and isinstance(payload["rechnung"], dict):
                    collect_payload("rechnung", payload["rechnung"])
                if "patient" in payload:
                    pat = payload["patient"]
                    if isinstance(pat, dict):
                        collect_payload("patienten", pat)
                    elif isinstance(pat, str) and payload.get("patient_id"):
                        collect_payload("patienten", {"id": payload.get("patient_id"), "name": pat.split('\n')[0]})

        # If entity_names mapping exists, ensure patienten table is populated with all resolved names
        if entity_names and isinstance(entity_names, dict):
            if "patienten" not in tables_data:
                tables_data["patienten"] = []
            for eid, ename in entity_names.items():
                tables_data["patienten"].append({"id": eid, "p_name": ename})

        # Create and populate dynamic tables
        for tbl_name, rows in tables_data.items():
            if not rows or tbl_name == "logs":
                continue

            all_cols = set()
            for r in rows:
                all_cols.update(r.keys())
            cols = sorted(list(all_cols))

            col_defs = ", ".join([f'"{c}" TEXT' for c in cols])
            cursor.execute(f'CREATE TABLE IF NOT EXISTS "{tbl_name}" ({col_defs});')

            insert_cols = ", ".join([f'"{c}"' for c in cols])
            placeholders = ", ".join(["?" for _ in cols])
            insert_sql = f'INSERT INTO "{tbl_name}" ({insert_cols}) VALUES ({placeholders});'

            row_values = []
            for r in rows:
                row_values.append(tuple(r.get(c) for c in cols))

            cursor.executemany(insert_sql, row_values)

        self.conn.commit()

    def import_external_tables(self, entity_map):
        """Helper to inject or update entity mappings in SQLite."""
        if not entity_map:
            return
        cursor = self.conn.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS "entity_names" ("id" TEXT PRIMARY KEY, "name" TEXT);')
        rows = [(str(k), str(v)) for k, v in entity_map.items()]
        cursor.executemany('INSERT OR REPLACE INTO "entity_names" (id, name) VALUES (?, ?);', rows)
        self.conn.commit()

    def execute_query(self, query):
        """Execute arbitrary SQL query and return columns, rows, execution time or error."""
        query = query.strip()
        if not query:
            return {"error": "Leere SQL-Abfrage"}

        start_time = time.time()
        cursor = self.conn.cursor()

        try:
            cursor.execute(query)
            exec_time_ms = round((time.time() - start_time) * 1000, 2)

            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                raw_rows = cursor.fetchall()
                rows = [list(r) for r in raw_rows]
                return {
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                    "execution_time_ms": exec_time_ms,
                    "error": None
                }
            else:
                self.conn.commit()
                return {
                    "columns": ["Status"],
                    "rows": [[f"SQL-Befehl erfolgreich ausgeführt ({cursor.rowcount} Zeilen betroffen)"]],
                    "row_count": cursor.rowcount,
                    "execution_time_ms": exec_time_ms,
                    "error": None
                }
        except Exception as e:
            return {"error": str(e)}

    def get_schema(self):
        """Returns dict of available tables, column names, and row counts."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]

        schema = {}
        row_counts = {}
        for tbl in tables:
            try:
                cursor.execute(f'PRAGMA table_info("{tbl}");')
                cols = [row[1] for row in cursor.fetchall()]
                schema[tbl] = cols

                cursor.execute(f'SELECT count(*) FROM "{tbl}";')
                cnt = cursor.fetchone()
                row_counts[tbl] = cnt[0] if cnt else 0
            except Exception:
                pass

        return {"tables": schema, "row_counts": row_counts}
