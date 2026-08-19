import json
from mapper import get_business_description, compute_field_diff

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


def extract_entity_ids(entry):
    ids = set()
    target_id = entry.get("target_id")
    if target_id and isinstance(target_id, str):
        ids.add(target_id)

    payload = entry.get("payload")

    def find_ids(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, str) and v and (k.endswith("_id") or k in ("id", "patient_id", "group_id", "rechnung_id", "events_id", "refid", "patienten_id", "parentevent_id")):
                    ids.add(v)
                elif isinstance(v, (dict, list)):
                    find_ids(v)
        elif isinstance(obj, list):
            for item in obj:
                find_ids(item)

    if isinstance(payload, (dict, list)):
        find_ids(payload)

    return list(ids)


def analyze_log_entries(parsed_entries):
    """Enrich log entries with descriptions, anomalies, diffs, entity tags, and group rapid updates/workflows."""
    processed = []
    entity_index = {} # id -> list of entry indices

    # 1. First pass: Enrich individual entries
    for entry in parsed_entries:
        desc = get_business_description(entry)
        anoms = check_anomalies(entry)
        entities = extract_entity_ids(entry)
        
        enriched = dict(entry)
        enriched["description"] = desc
        enriched["anomalies"] = anoms
        enriched["entities"] = entities
        enriched["is_chatter"] = False
        enriched["group_children"] = []
        
        processed.append(enriched)

    # Build entity index
    for idx, item in enumerate(processed):
        for eid in item["entities"]:
            if eid not in entity_index:
                entity_index[eid] = []
            entity_index[eid].append(idx)

    # 2. Second pass: Calculate diffs for consecutive updates to the same entity
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

    # 3. Third pass: Workflow grouping & Rapid keystroke (noise) collapsing
    final_timeline = []
    skip_indices = set()

    for idx, item in enumerate(processed):
        if idx in skip_indices:
            continue

        # Look ahead for rapid repetitive updates (keystroke noise)
        table = item["table"]
        action = item["action"]
        target_id = item["target_id"]
        
        if action in ("update", "insert") and target_id:
            cluster = [item]
            j = idx + 1
            while j < len(processed):
                next_item = processed[j]
                # Check if same table, action, target_id within 5 seconds
                if next_item["table"] == table and next_item["target_id"] == target_id and next_item["action"] == action:
                    cluster.append(next_item)
                    skip_indices.add(j)
                    j += 1
                else:
                    break
            
            if len(cluster) > 1:
                main_item = dict(cluster[-1]) # Use latest state as main
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
        "total_count": len(parsed_entries)
    }
