import re
import json
import os
import io
import zipfile

LOG_LINE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s+([A-Z0-9\-]+)\s+([a-z]+)\s*(.*)$")

def try_unpack_json(val):
    """Recursively unpack stringified JSONs if valid."""
    if isinstance(val, str):
        val_strip = val.strip()
        if (val_strip.startswith('{') and val_strip.endswith('}')) or (val_strip.startswith('[') and val_strip.endswith(']')):
            try:
                decoded = json.loads(val_strip)
                return try_unpack_json(decoded)
            except Exception:
                pass
        return val
    elif isinstance(val, dict):
        return {k: try_unpack_json(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [try_unpack_json(item) for item in val]
    return val

def parse_log_line(line, line_number=0, file_name=""):
    line = line.strip()
    if not line:
        return None

    m = LOG_LINE_PATTERN.match(line)
    if not m:
        return {
            "line_number": line_number,
            "file_name": file_name,
            "raw": line,
            "error": "Failed to parse log format"
        }

    timestamp, user, action, rest = m.groups()
    table = None
    target_id = None
    payload = None

    if action in ('update', 'insert'):
        parts = rest.split(' ', 1)
        table = parts[0]
        payload_str = parts[1] if len(parts) > 1 else ""
        if payload_str.startswith("id "):
            payload_str = payload_str[3:]
        
        try:
            payload = json.loads(payload_str)
            if isinstance(payload, dict):
                target_id = payload.get('id')
                payload = try_unpack_json(payload)
        except Exception:
            payload = payload_str

    elif action in ('encexec', 'encdelete'):
        table = "sql_command"
        try:
            payload = json.loads(rest)
            payload = try_unpack_json(payload)
            if isinstance(payload, dict):
                params = payload.get('params', {})
                target_id = params.get('id') or params.get('rechnungid') or params.get('group_id')
        except Exception:
            payload = rest

    return {
        "line_number": line_number,
        "file_name": file_name,
        "timestamp": timestamp,
        "user": user,
        "action": action,
        "table": table,
        "target_id": target_id,
        "payload": payload,
        "raw": line
    }

def parse_log_file(file_path, file_name=""):
    fname = file_name or os.path.basename(file_path)
    entries = []
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for i, line in enumerate(f, 1):
            parsed = parse_log_line(line, line_number=i, file_name=fname)
            if parsed:
                entries.append(parsed)
    return entries

def parse_log_content(content, file_name=""):
    """Parse text string or bytes (ZIP archive or raw log text) into log entries."""
    fname = file_name or "uploaded.log"
    ext = os.path.splitext(fname)[1].lower() if fname else ""
    entries = []

    # Check for ZIP archive
    is_zip = ext == ".zip" or (isinstance(content, bytes) and content.startswith(b"PK\x03\x04"))
    if is_zip:
        try:
            zip_bytes = io.BytesIO(content) if isinstance(content, bytes) else content
            with zipfile.ZipFile(zip_bytes, 'r') as zf:
                for member_name in zf.namelist():
                    if member_name.endswith('/') or member_name.startswith('__MACOSX'):
                        continue
                    m_ext = os.path.splitext(member_name)[1].lower()
                    if m_ext in ('.log', '.txt', '.json'):
                        file_text = zf.read(member_name).decode('utf-8', errors='ignore')
                        lines = file_text.splitlines()
                        for i, line in enumerate(lines, 1):
                            parsed = parse_log_line(line, line_number=i, file_name=os.path.basename(member_name))
                            if parsed:
                                entries.append(parsed)
        except Exception as e:
            print(f"Error reading ZIP log archive: {e}")
        return entries

    text = content if isinstance(content, str) else content.decode('utf-8', errors='ignore')
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        parsed = parse_log_line(line, line_number=i, file_name=fname)
        if parsed:
            entries.append(parsed)

    return entries
