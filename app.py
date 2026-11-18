import os
import sys
import json
import base64
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
import webview

from parser import parse_log_file, parse_log_content
from analyzer import analyze_log_entries, parse_external_entity_data
from sql_engine import SQLEngine

def get_resource_path(relative_path=""):
    """Get absolute path to resource, works for dev and for PyInstaller bundle."""
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

RESOURCE_DIR = get_resource_path()
sql_engine = SQLEngine()

# Gespeicherte Event-Regeln (benannte Suchen). Liegen im Benutzerprofil, damit sie
# Neustarts und neue Builds der .exe überleben.
RULES_FILE = os.path.join(
    os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config"),
    "PyLogAnalyzer", "rules.json"
)
DEFAULT_RULES = [
    {"name": "Therapiebericht geschrieben", "query": "tabelle:rezepte geändert:tp_therapiebericht"},
]

def load_rules():
    try:
        with open(RULES_FILE, "r", encoding="utf-8") as f:
            return clean_rules(json.load(f))
    except FileNotFoundError:
        return list(DEFAULT_RULES)
    except Exception as e:
        print(f"Regeln konnten nicht gelesen werden: {e}")
        return []

def clean_rules(rules):
    cleaned = []
    for rule in rules if isinstance(rules, list) else []:
        if isinstance(rule, dict):
            name = str(rule.get("name", "")).strip()
            query = str(rule.get("query", "")).strip()
            if name and query:
                cleaned.append({"name": name[:60], "query": query[:500]})
    return cleaned

def save_rules(rules):
    rules = clean_rules(rules)
    os.makedirs(os.path.dirname(RULES_FILE), exist_ok=True)
    with open(RULES_FILE, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)
    return rules

class LogAnalyzerRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=RESOURCE_DIR, **kwargs)

    def do_GET(self):
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/api/sample":
            sample_file = os.path.join(RESOURCE_DIR, "sample.log")
            if os.path.exists(sample_file):
                parsed = parse_log_file(sample_file)
                analysis = analyze_log_entries(parsed)
                sql_engine.load_data(analysis["all_entries"], analysis["entity_names"])
                self.send_json_response(analysis)
            else:
                self.send_json_response({"error": "sample.log nicht gefunden"}, status=404)
            return

        elif parsed_url.path == "/api/schema":
            self.send_json_response(sql_engine.get_schema())
            return

        elif parsed_url.path == "/api/rules":
            self.send_json_response({"rules": load_rules()})
            return

        return super().do_GET()

    def do_POST(self):
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/api/parse":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_body = self.rfile.read(content_length)
            filename = self.headers.get('X-File-Name', '')

            content_type = self.headers.get('Content-Type', '').split(';')[0].strip().lower()

            if content_type == 'application/json':
                try:
                    payload_data = json.loads(raw_body.decode('utf-8'))
                    parsed = []
                    for f in payload_data.get("files", []):
                        f_name = f.get("name", "")
                        if f.get("is_zip"):
                            f_bytes = base64.b64decode(f["data"])
                            parsed.extend(parse_log_content(f_bytes, file_name=f_name))
                        else:
                            parsed.extend(parse_log_content(f.get("text", ""), file_name=f_name))
                except Exception as e:
                    self.send_json_response({"error": f"Upload konnte nicht verarbeitet werden: {e}"}, status=400)
                    return
            else:
                parsed = parse_log_content(raw_body, file_name=filename)

            analysis = analyze_log_entries(parsed)
            sql_engine.load_data(analysis["all_entries"], analysis["entity_names"])
            self.send_json_response(analysis)
            return

        elif parsed_url.path == "/api/import_entities":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_body = self.rfile.read(content_length)
            filename = self.headers.get('X-File-Name', '')
            entity_map = parse_external_entity_data(raw_body, filename=filename)
            sql_engine.import_external_tables(entity_map)
            self.send_json_response({
                "entity_names": entity_map,
                "count": len(entity_map),
                "schema": sql_engine.get_schema()
            })
            return

        elif parsed_url.path == "/api/query_sql":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8', errors='ignore')
            try:
                payload = json.loads(body)
                query = payload.get("query", "")
            except Exception:
                query = body

            result = sql_engine.execute_query(query)
            self.send_json_response(result)
            return

        elif parsed_url.path == "/api/rules":
            content_length = int(self.headers.get('Content-Length', 0))
            try:
                payload = json.loads(self.rfile.read(content_length).decode('utf-8'))
                rules = save_rules(payload.get("rules", []))
            except Exception as e:
                self.send_json_response({"error": f"Regeln konnten nicht gespeichert werden: {e}"}, status=400)
                return
            self.send_json_response({"rules": rules})
            return

        self.send_error(404, "Not Found")

    def send_json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass

def main():
    httpd = HTTPServer(('127.0.0.1', 0), LogAnalyzerRequestHandler)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    app_url = f"http://127.0.0.1:{httpd.server_port}"
    
    window = webview.create_window(
        title='PyLogAnalyzer — Master-Detail Log Inspector',
        url=app_url,
        width=1350,
        height=850,
        min_size=(900, 600),
        maximized=True
    )
    
    webview.start()

if __name__ == "__main__":
    main()
