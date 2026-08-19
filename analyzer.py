import os
import io
import zipfile
import json
import csv
import sqlite3
from mapper import get_business_description, compute_field_diff, extract_patient_name

def check_anomalies(entry):
    anomalies = []
    payload = entry.get("payload")
    action = entry.get("action")
    table = entry.get("table")
    line_num = entry.get("line_number")

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


def get_entity_type_label(field_key, table_name=""):
    key = field_key.lower() if field_key else ""
    if key in ("group_id", "groupid"):
        return "Group-ID"
    elif key in ("patient_id", "patienten_id"):
        return "Patient-ID"
    elif key in ("rechnung_id", "rechnungid", "rechnungnr"):
        return "Rechnungs-ID"
    elif key in ("events_id", "event_id", "parentevent_id"):
        return "Termin-ID"
    elif key in ("rezept_id", "rezepte_id"):
        return "Rezept-ID"
    elif key in ("refid", "referenz_id"):
        return "Referenz-ID"
    elif key == "id":
        if table_name == "patienten":
            return "Patient-ID"
        elif table_name == "events":
            return "Termin-ID"
        elif table_name == "rechnung":
            return "Rechnungs-ID"
        elif table_name == "rezepte":
            return "Rezept-ID"
        elif table_name == "history":
            return "Historie-ID"
        return f"{table_name.capitalize()}-ID" if table_name else "ID"
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


def extract_entity_ids(entry):
    return list(extract_entity_details(entry).keys())


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
        tmp_path = "temp_import.db"
        try:
            if isinstance(content, bytes):
                with open(tmp_path, "wb") as f:
                    f.write(content)
                db_path = tmp_path
            else:
                db_path = content

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]

            for tbl in tables:
                try:
                    cursor.execute(f"SELECT * FROM {tbl}")
                    cols = [description[0].lower() for description in cursor.description]
                    rows = cursor.fetchall()
                    for row in rows:
                        row_dict = dict(zip(cols, row))
                        e_id = row_dict.get("id") or row_dict.get("user_id") or row_dict.get("userid") or row_dict.get("patient_id") or row_dict.get("p_nr")
                        e_name = extract_patient_name(row_dict) or row_dict.get("name") or row_dict.get("username")
                        if e_id and e_name:
                            names[str(e_id)] = str(e_name).strip()
                except Exception:
                    pass
            conn.close()
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
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
        enriched["is_chatter"] = False
        enriched["group_children"] = []
        
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
    skip_indices = set()

    for idx, item in enumerate(processed):
        if idx in skip_indices:
            continue

        table = item["table"]
        action = item["action"]
        target_id = item["target_id"]
        
        if action in ("update", "insert") and target_id:
            cluster = [item]
            j = idx + 1
            while j < len(processed):
                next_item = processed[j]
                if next_item["table"] == table and next_item["target_id"] == target_id and next_item["action"] == action:
                    cluster.append(next_item)
                    skip_indices.add(j)
                    j += 1
                else:
                    break
            
            if len(cluster) > 1:
                main_item = dict(cluster[-1])
                main_item["line_number"] = f"{cluster[0]['line_number']}-{cluster[-1]['line_number']}"
                main_item["is_clustered"] = True
                main_item["cluster_count"] = len(cluster)
                main_item["description"] = f"{main_item['description']} ({len(cluster)} aufeinanderfolgende Änderungen)"
                main_item["group_children"] = cluster[:-1]
                final_timeline.append(main_item)
                continue

        final_timeline.append(item)

    return {
        "timeline": final_timeline,
        "all_entries": processed,
        "entity_index": entity_index,
        "entity_names": entity_names,
        "entity_labels": entity_labels,
        "loaded_files": loaded_files,
        "total_count": len(parsed_entries)
    }
