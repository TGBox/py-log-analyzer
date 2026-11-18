import os
import io
import zipfile
import json
import csv
import sqlite3
import itertools
import re
from mapper import get_business_description, compute_field_diff, extract_patient_name

SQL_UPDATE_PATTERN = re.compile(r"^\s*update\s+(\w+)\s+set\s+(.+?)\s+where\s+(.+)$", re.IGNORECASE | re.DOTALL)
SQL_WHERE_ID_PATTERN = re.compile(r"^\s*id\s*=\s*:(\w+)", re.IGNORECASE)


def _split_top_level(text):
    """Split on commas that are not inside parentheses or quotes."""
    parts, depth, quote, current = [], 0, None, []
    for ch in text:
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(ch)
    parts.append("".join(current))
    return parts


def _sql_value(expr, params):
    expr = expr.strip()
    if expr.startswith(":"):
        return params.get(expr[1:])
    low = expr.lower()
    if low == "null":
        return None
    if low in ("true", "false"):
        return low == "true"
    if len(expr) >= 2 and expr[0] == "'" and expr[-1] == "'":
        return expr[1:-1]
    try:
        return json.loads(expr)
    except Exception:
        return expr  # SQL expression such as CURRENT_DATE


def parse_sql_write(entry):
    """Extract the written columns of an 'update <table> set ...' SQL command.

    Returns {"table", "id", "fields"} or None. "id" is only set when the
    statement addresses a single row via 'where id=:param'.
    """
    payload = entry.get("payload")
    if entry.get("action") != "encexec" or not isinstance(payload, dict):
        return None
    sql = payload.get("sql")
    params = payload.get("params")
    if not isinstance(sql, str):
        return None
    if not isinstance(params, dict):
        params = {}

    m = SQL_UPDATE_PATTERN.match(sql.strip())
    if not m:
        return None
    table, assignments, where = m.groups()

    fields = {}
    for part in _split_top_level(assignments):
        if "=" not in part:
            continue
        col, expr = part.split("=", 1)
        col = col.strip().lower()
        if re.fullmatch(r"\w+", col):
            fields[col] = _sql_value(expr, params)
    if not fields:
        return None

    record_id = None
    m_id = SQL_WHERE_ID_PATTERN.match(where)
    if m_id:
        record_id = params.get(m_id.group(1))

    return {"table": table.lower(), "id": record_id, "fields": fields}


def get_written_fields(entry):
    """Return (table, record_id, fields) for entries that write data, else None."""
    sql_write = entry.get("sql_write")
    if sql_write:
        return sql_write["table"], sql_write["id"], sql_write["fields"]
    payload = entry.get("payload")
    if entry.get("action") in ("insert", "update") and entry.get("table") and isinstance(payload, dict):
        return entry["table"], entry.get("target_id") or payload.get("id"), payload
    return None


def _is_empty(val):
    return val is None or val == "" or val == [] or val == {}


def detect_field_changes(entry, record_states):
    """Compare the written fields with the last known state of the same record.

    record_states maps (table, id) -> {field: last value} and is updated in place.
    Returns {field: {"kind": ...}} with kind
      "initial" - non-empty value on insert
      "set"     - non-empty value, field not seen before (previous value unknown)
      "changed" - value differs from the last known value (carries "old")
    or None if the entry writes no data.
    """
    written = get_written_fields(entry)
    if not written:
        return None
    table, record_id, fields = written
    changes = {}
    if record_id is None:
        return changes

    known = record_states.setdefault((table, str(record_id)), {})
    is_insert = entry.get("action") == "insert"
    for field, new_val in fields.items():
        if field == "id":
            continue
        if field in known:
            if known[field] != new_val:
                changes[field] = {"kind": "changed", "old": known[field]}
        elif not _is_empty(new_val):
            changes[field] = {"kind": "initial" if is_insert else "set"}
        known[field] = new_val
    return changes

def check_anomalies(entry):
    anomalies = []
    payload = entry.get("payload")
    action = entry.get("action")
    table = entry.get("table")
    line_num = entry.get("line_number")

    # 0. Unparseable line
    if entry.get("error"):
        anomalies.append({
            "type": "parse_error",
            "severity": "warning",
            "title": "Parse-Fehler",
            "message": f"Zeile {line_num} entspricht nicht dem erwarteten Log-Format"
        })
        return anomalies

    # 1. SQL Null Parameter Check
    if action in ("encexec", "encdelete") and isinstance(payload, dict):
        params = payload.get("params", {})
        if isinstance(params, dict):
            for k, v in params.items():
                if v is None:
                    anomalies.append({
                        "type": "null_sql_param",
                        "severity": "warning",
                        "title": "SQL-Parameter 'null'",
                        "message": f"SQL-Parameter '{k}' ist NULL in Query: {payload.get('sql', '').strip()}"
                    })

    # 2. Float Precision Anomaly Check
    def scan_floats(obj, path=""):
        if isinstance(obj, float):
            s = str(obj)
            if 'e-' in s or ('.' in s and len(s.split('.')[1]) > 5):
                anomalies.append({
                    "type": "float_precision",
                    "severity": "info",
                    "title": "Gleitkomma-Ungenauigkeit",
                    "message": f"Feld '{path}' hat ungenauen Wert: {obj}"
                })
        elif isinstance(obj, str):
            if 'e-' in obj or '.00000000' in obj:
                anomalies.append({
                    "type": "float_precision",
                    "severity": "info",
                    "title": "Gleitkomma-Ungenauigkeit in Text",
                    "message": f"Feld '{path}' enthält Formatsprung: {obj}"
                })
        elif isinstance(obj, dict):
            for k, v in obj.items():
                scan_floats(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                scan_floats(item, f"{path}[{idx}]")

    if isinstance(payload, (dict, list)):
        scan_floats(payload)

    # 3. Deletion Indicator
    if action == "encdelete" or (action == "update" and isinstance(payload, dict) and payload.get("abgesagt") == 1):
        anomalies.append({
            "type": "deletion",
            "severity": "critical" if action == "encdelete" else "warning",
            "title": "Lösch- / Absage-Vorgang",
            "message": "Eintrag betrifft eine Löschung oder Absage eines Termins"
        })

    return anomalies


ENTITY_KEY_LABELS = {
    "group_id": "Group-ID", "groupid": "Group-ID",
    "patient_id": "Patient-ID", "patienten_id": "Patient-ID",
    "rechnung_id": "Rechnungs-ID", "rechnungid": "Rechnungs-ID", "rechnungnr": "Rechnungs-ID",
    "events_id": "Termin-ID", "event_id": "Termin-ID", "parentevent_id": "Termin-ID",
    "rezept_id": "Rezept-ID", "rezepte_id": "Rezept-ID",
    "refid": "Referenz-ID", "referenz_id": "Referenz-ID",
}
TABLE_ID_LABELS = {
    "patienten": "Patient-ID", "events": "Termin-ID", "rechnung": "Rechnungs-ID",
    "rezepte": "Rezept-ID", "history": "Historie-ID",
}

def get_entity_type_label(field_key, table_name=""):
    key = field_key.lower() if field_key else ""
    if key in ENTITY_KEY_LABELS:
        return ENTITY_KEY_LABELS[key]
    if key == "id":
        return TABLE_ID_LABELS.get(table_name, f"{table_name.capitalize()}-ID" if table_name else "ID")
    return field_key.replace("_", "-").upper()


def extract_entity_details(entry):
    details_map = {} # id -> entity_type_label
    table_name = entry.get("table", "")
    target_id = entry.get("target_id")

    if target_id and isinstance(target_id, str):
        label = get_entity_type_label("id", table_name)
        details_map[target_id] = label

    payload = entry.get("payload")

    def find_ids(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str) and v and (k.endswith("_id") or k in ("id", "patient_id", "group_id", "rechnung_id", "events_id", "refid", "patienten_id", "parentevent_id")):
                    label = get_entity_type_label(k, table_name)
                    if v not in details_map or details_map[v] == "ID":
                        details_map[v] = label
                elif isinstance(v, (dict, list)):
                    find_ids(v)
        elif isinstance(obj, list):
            for item in obj:
                find_ids(item)

    if isinstance(payload, (dict, list)):
        find_ids(payload)

    return details_map


def extract_entity_name_from_entry(entry):
    """Extract ID -> Name mapping from a single log entry if present."""
    payload = entry.get("payload")
    if not isinstance(payload, dict):
        return {}

    names = {}
    target_id = payload.get("id") or entry.get("target_id")
    pat_name = extract_patient_name(payload)

    if target_id and pat_name:
        names[target_id] = pat_name

    pat_id = payload.get("patient_id") or payload.get("patienten_id")
    if pat_id and pat_name:
        names[pat_id] = pat_name

    def scan_nested(obj):
        if isinstance(obj, dict):
            p_id = obj.get("id") or obj.get("patient_id") or obj.get("patienten_id") or obj.get("p_nr")
            p_name = extract_patient_name(obj)
            if p_id and p_name:
                names[p_id] = p_name
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    scan_nested(v)
        elif isinstance(obj, list):
            for item in obj:
                scan_nested(item)

    scan_nested(payload)
    return names


def parse_external_entity_data(content, filename=""):
    """Parse JSON, CSV, SQLite database or ZIP archive bytes/string into ID -> Name mapping."""
    names = {}
    ext = os.path.splitext(filename)[1].lower() if filename else ""

    # ZIP Archive support
    if ext == ".zip" or (isinstance(content, bytes) and content.startswith(b"PK\x03\x04")):
        try:
            zip_bytes = io.BytesIO(content) if isinstance(content, bytes) else content
            with zipfile.ZipFile(zip_bytes, 'r') as zf:
                for member_name in zf.namelist():
                    if member_name.endswith('/') or member_name.startswith('__MACOSX'):
                        continue
                    file_ext = os.path.splitext(member_name)[1].lower()
                    if file_ext in ('.csv', '.json', '.db', '.sqlite', '.sqlite3'):
                        file_data = zf.read(member_name)
                        extracted = parse_external_entity_data(file_data, filename=member_name)
                        names.update(extracted)
        except Exception as e:
            print(f"Error parsing ZIP archive: {e}")
        return names

    is_sqlite = ext in (".db", ".sqlite", ".sqlite3") or (isinstance(content, bytes) and content.startswith(b"SQLite format 3"))

    if is_sqlite:
        try:
            if isinstance(content, bytes):
                conn = sqlite3.connect(":memory:")
                conn.deserialize(content)
            elif isinstance(content, str) and os.path.exists(content):
                conn = sqlite3.connect(content)
            else:
                conn = None

            if conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [row[0] for row in cursor.fetchall()]

                for tbl in tables:
                    try:
                        cursor.execute(f"SELECT * FROM {tbl}")
                        cols = [description[0].lower() for description in cursor.description]
                        for row in cursor.fetchall():
                            row_dict = dict(zip(cols, row))
                            e_id = row_dict.get("id") or row_dict.get("user_id") or row_dict.get("userid") or row_dict.get("patient_id") or row_dict.get("p_nr")
                            e_name = extract_patient_name(row_dict) or row_dict.get("name") or row_dict.get("username")
                            if e_id and e_name:
                                names[str(e_id)] = str(e_name).strip()
                    except Exception:
                        pass
                conn.close()
        except Exception as e:
            print(f"Error parsing SQLite DB: {e}")

    elif ext == ".csv" or (isinstance(content, str) and ("," in content or ";" in content or "\t" in content)):
        try:
            text = content if isinstance(content, str) else content.decode('utf-8', errors='ignore')
            delimiter = ';' if ';' in text else (',' if ',' in text else '\t')
            reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
            for row in reader:
                norm_row = {k.strip().lower(): v.strip() for k, v in row.items() if k and v}
                e_id = norm_row.get("id") or norm_row.get("user_id") or norm_row.get("userid") or norm_row.get("patient_id") or norm_row.get("patienten_id") or norm_row.get("p_nr")
                e_name = extract_patient_name(norm_row) or norm_row.get("name") or norm_row.get("username")
                if e_id and e_name:
                    names[str(e_id)] = str(e_name).strip()
        except Exception as e:
            print(f"Error parsing CSV: {e}")

    else:
        try:
            text = content if isinstance(content, str) else content.decode('utf-8', errors='ignore')
            data = json.loads(text)
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, str):
                        names[str(k)] = v
                    elif isinstance(v, dict):
                        name = extract_patient_name(v) or v.get("name") or v.get("username")
                        if name:
                            names[str(k)] = name
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        e_id = item.get("id") or item.get("user_id") or item.get("userid") or item.get("patient_id")
                        e_name = extract_patient_name(item) or item.get("name") or item.get("username")
                        if e_id and e_name:
                            names[str(e_id)] = str(e_name).strip()
        except Exception as e:
            print(f"Error parsing JSON: {e}")

    return names


def analyze_log_entries(parsed_entries, external_entity_map=None):
    """Enrich log entries using 2-pass indexing for entity name resolution."""
    # Sort chronologically across all loaded files
    parsed_entries = sorted(parsed_entries, key=lambda x: x.get("timestamp") or "")

    # Extract unique loaded file names
    loaded_files = sorted(list(set(e.get("file_name") for e in parsed_entries if e.get("file_name"))))

    # Pass 1: Build global ID -> Name dictionary from log entries
    entity_names = {}
    if external_entity_map and isinstance(external_entity_map, dict):
        entity_names.update(external_entity_map)

    for entry in parsed_entries:
        discovered = extract_entity_name_from_entry(entry)
        entity_names.update(discovered)

    processed = []
    entity_index = {} # id -> list of entry indices
    entity_labels = {} # id -> entity_type_label
    record_states = {} # (table, id) -> {field: last known value}
    field_names = set()

    # Pass 2: Enrich individual entries with resolved descriptions and entity info
    for entry in parsed_entries:
        desc = get_business_description(entry, entity_names=entity_names)
        anoms = check_anomalies(entry)
        entities_details = extract_entity_details(entry)
        entities = list(entities_details.keys())
        
        entities_info = []
        for eid, elabel in entities_details.items():
            name = entity_names.get(eid)
            entity_labels[eid] = elabel
            entities_info.append({
                "id": eid,
                "name": name,
                "label": elabel
            })

        user_id = entry.get("user")
        user_name = entity_names.get(user_id) if user_id else None
        if user_id and user_name:
            entity_labels[user_id] = "Nutzer-ID"

        enriched = dict(entry)
        enriched["description"] = desc
        enriched["user_name"] = user_name
        enriched["anomalies"] = anoms
        enriched["entities"] = entities
        enriched["entities_info"] = entities_info
        enriched["group_children"] = []

        sql_write = parse_sql_write(entry)
        if sql_write:
            enriched["sql_write"] = sql_write
        changes = detect_field_changes(enriched, record_states)
        if changes is not None:
            enriched["changes"] = changes
            field_names.update(k.lower() for k in get_written_fields(enriched)[2])

        processed.append(enriched)

    # Build entity index
    for idx, item in enumerate(processed):
        for eid in item["entities"]:
            if eid not in entity_index:
                entity_index[eid] = []
            entity_index[eid].append(idx)

    # Pass 3: Calculate diffs for consecutive updates
    for eid, indices in entity_index.items():
        if len(indices) > 1:
            for i in range(1, len(indices)):
                prev_idx = indices[i-1]
                curr_idx = indices[i]
                prev_item = processed[prev_idx]
                curr_item = processed[curr_idx]
                
                if prev_item["table"] == curr_item["table"] and curr_item["action"] == "update":
                    diff = compute_field_diff(prev_item.get("payload"), curr_item.get("payload"))
                    if diff:
                        curr_item["diff"] = diff

    # Pass 4: Workflow grouping & Rapid keystroke (noise) collapsing
    final_timeline = []

    def cluster_key(item):
        if item.get("action") in ("update", "insert") and item.get("target_id"):
            return (item["table"], item["target_id"], item["action"])
        return id(item)

    for _, group in itertools.groupby(processed, key=cluster_key):
        cluster = list(group)
        if len(cluster) > 1:
            main_item = dict(cluster[-1])
            main_item["line_number"] = f"{cluster[0]['line_number']}-{cluster[-1]['line_number']}"
            main_item["is_clustered"] = True
            main_item["cluster_count"] = len(cluster)
            main_item["description"] = f"{main_item['description']} ({len(cluster)} aufeinanderfolgende Änderungen)"
            main_item["group_children"] = cluster[:-1]
            final_timeline.append(main_item)
        else:
            final_timeline.append(cluster[0])

    return {
        "timeline": final_timeline,
        "all_entries": processed,
        "entity_index": entity_index,
        "entity_names": entity_names,
        "entity_labels": entity_labels,
        "loaded_files": loaded_files,
        "field_names": sorted(field_names),
        "total_count": len(parsed_entries)
    }
