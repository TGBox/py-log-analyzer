import os
import json
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from parser import parse_log_file, parse_log_line
from analyzer import analyze_log_entries

PORT = 8050
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))

class LogAnalyzerRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WORKSPACE_DIR, **kwargs)

    def do_GET(self):
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/api/sample":
            sample_file = os.path.join(WORKSPACE_DIR, "sample.log")
            if os.path.exists(sample_file):
                parsed = parse_log_file(sample_file)
                analysis = analyze_log_entries(parsed)
                self.send_json_response(analysis)
            else:
                self.send_json_response({"error": "sample.log not found"}, status=404)
            return
        
        # Serve static files as default
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

def main():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, LogAnalyzerRequestHandler)
    url = f"http://localhost:{PORT}"
    print(f"==================================================")
    print(f"   PyLogAnalyzer GUI Server running on:")
    print(f"   {url}")
    print(f"==================================================")
    
    # Automatically open browser
    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer shutting down.")

if __name__ == "__main__":
    main()
