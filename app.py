import os
import sys
import json
import socket
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
import webview

from parser import parse_log_file, parse_log_line
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

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

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
        
        return super().do_GET()

    def do_POST(self):
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/api/parse":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_body = self.rfile.read(content_length)
            filename = self.headers.get('X-File-Name', '')

            if raw_body.startswith(b"{") and b'"entries"' in raw_body:
                try:
                    payload_data = json.loads(raw_body.decode('utf-8'))
                    parsed = payload_data.get("entries", [])
                except Exception:
                    parsed = parse_log_content(raw_body, file_name=filename)
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

def start_server(port):
    server_address = ('127.0.0.1', port)
    httpd = HTTPServer(server_address, LogAnalyzerRequestHandler)
    httpd.serve_forever()

def main():
    port = get_free_port()
    
    server_thread = threading.Thread(target=start_server, args=(port,), daemon=True)
    server_thread.start()

    app_url = f"http://127.0.0.1:{port}"
    
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
