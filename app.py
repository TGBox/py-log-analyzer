import os
import sys
import json
import socket
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
import webview

from parser import parse_log_file, parse_log_line
from analyzer import analyze_log_entries

def get_resource_path(relative_path=""):
    """Get absolute path to resource, works for dev and for PyInstaller bundle."""
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

RESOURCE_DIR = get_resource_path()

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
                self.send_json_response(analysis)
            else:
                self.send_json_response({"error": "sample.log nicht gefunden"}, status=404)
            return
        
        return super().do_GET()

    def do_POST(self):
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/api/parse":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8', errors='ignore')
            
            lines = body.splitlines()
            parsed = [parse_log_line(line, i+1) for i, line in enumerate(lines) if line.strip()]
            parsed = [p for p in parsed if p is not None]
            analysis = analyze_log_entries(parsed)
            self.send_json_response(analysis)
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
        # Silence console HTTP logging in desktop mode
        pass

def start_server(port):
    server_address = ('127.0.0.1', port)
    httpd = HTTPServer(server_address, LogAnalyzerRequestHandler)
    httpd.serve_forever()

def main():
    port = get_free_port()
    
    # Start HTTP server thread in background
    server_thread = threading.Thread(target=start_server, args=(port,), daemon=True)
    server_thread.start()

    app_url = f"http://127.0.0.1:{port}"
    
    # Create native desktop window using pywebview
    window = webview.create_window(
        title='PyLogAnalyzer — Master-Detail Log Inspector',
        url=app_url,
        width=1350,
        height=850,
        min_size=(900, 600)
    )
    
    webview.start()

if __name__ == "__main__":
    main()
