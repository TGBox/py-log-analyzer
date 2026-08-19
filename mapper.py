import json

def extract_patient_name(data):
    if not isinstance(data, dict):
        return None
    
    # Direct fields
    if "p_name" in data or "p_vname" in data:
        vname = data.get("p_vname", "") or ""
        name = data.get("p_name", "") or ""
        full = f"{vname} {name}".strip()
        if full:
            return full

    if "patient" in data:
        pat = data["patient"]
        if isinstance(pat, str):
            # Often formatted as "Schneider Bryan \nSperberweg 6 B ..."
            lines = pat.split('\n')
            return lines[0].strip() if lines else pat.strip()
        elif isinstance(pat, dict):
            return extract_patient_name(pat)

    return None

def get_business_description(entry):
    action = entry.get("action")
    table = entry.get("table")
    payload = entry.get("payload") or {}
    
    if not isinstance(payload, dict):
        return f"{action.upper()} {table}" if table else action.upper()

    patient_name = extract_patient_name(payload)

    # 1. EVENTS
    if table == "events":
        title = payload.get("title", "Termin")
        start = payload.get("start", "")
        # Format time if ISO format
        if "T" in start:
            time_part = start.split("T")[1][:5]
            date_part = start.split("T")[0]
            start_fmt = f"{date_part} um {time_part} Uhr"
        else:
            start_fmt = start

        if action == "insert":
            if patient_name:
                return f"Termin angelegt: '{title}' für {patient_name} ({start_fmt})"
            return f"Termin angelegt: '{title}' ({start_fmt})"
        elif action == "update":
            status_addon = ""
            if payload.get("abgesagt") == 1 or payload.get("abgesagt") is True:
                status_addon = " [ABGESAGT]"
            elif payload.get("wahrgenommen") is True:
                status_addon = " [WAHRGENOMMEN]"
            elif payload.get("nicht_wahrgenommen") is True:
                status_addon = " [AUSFALL]"
            
            if patient_name:
                return f"Termin aktualisiert: '{title}' für {patient_name}{status_addon}"
            return f"Termin aktualisiert: '{title}' ({start_fmt}){status_addon}"

    # 2. RECHNUNG
    elif table == "rechnung":
        rechnungnr = payload.get("rechnungnr") or payload.get("id", "")[:8]
        referenz = payload.get("referenz", "Rechnung")
        if action == "insert":
            if patient_name:
                return f"Rechnung ({referenz}) angelegt für {patient_name}"
            return f"Rechnung ({referenz}) angelegt"
        elif action == "update":
            if rechnungnr and rechnungnr != payload.get("id", "")[:8]:
                return f"Rechnung #{rechnungnr} ({referenz}) aktualisiert"
            return f"Rechnung ({referenz}) aktualisiert"

    # 3. RECHPOS (Rechnungsposition)
    elif table == "rechpos":
        bezeichnung = payload.get("bezeichnung", "Rechnungsposition")
        preis = payload.get("einzelpreis") or payload.get("gesamtpreis")
        preis_str = f" ({preis} €)" if preis else ""
        if action == "insert":
            return f"Rechnungsposition hinzugefügt: '{bezeichnung}'{preis_str}"
        return f"Rechnungsposition aktualisiert: '{bezeichnung}'{preis_str}"

    # 4. PATIENTEN
    elif table == "patienten":
        name = extract_patient_name(payload) or payload.get("id", "")[:8]
        if action == "update":
            if "p_zuzahlungsbefreit_bis" in payload:
                bis = payload.get("p_zuzahlungsbefreit_bis")
                return f"Patient {name}: Zuzahlungsbefreiung geändert ({bis})"
            elif "p_zuzahlungsbefreit" in payload:
                befreit = "befreit" if payload.get("p_zuzahlungsbefreit") else "pflichtig"
                return f"Patient {name}: Zuzahlungsstatus auf '{befreit}' gesetzt"
            return f"Patient Stammdaten aktualisiert: {name}"
        return f"Patient Stammdaten angelegt: {name}"

    # 5. REZEPTE & REZEPTE_EVENTS
    elif table == "rezepte":
        rezeptnr = payload.get("rezeptnr") or payload.get("id", "")[:8]
        diag = payload.get("diagnosegruppe", "")
        diag_str = f" ({diag})" if diag else ""
        if action == "insert":
            return f"Rezept #{rezeptnr}{diag_str} angelegt"
        return f"Rezept #{rezeptnr}{diag_str} aktualisiert"

    elif table == "rezepte_events":
        if action == "insert":
            return "Rezept-Verknüpfung (Event zu Rezept) hinzugefügt"
        return "Rezept-Verknüpfung aktualisiert"

    # 6. HISTORY
    elif table == "history":
        stichwort = payload.get("stichwort", "Notiz")
        text = payload.get("text", "")
        snippet = f": {text[:40]}..." if len(text) > 40 else (f": {text}" if text else "")
        return f"Historie-Eintrag '{stichwort}'{snippet}"

    # 7. SETTINGS
    elif table == "settings":
        setting_name = payload.get("name", "Einstellungen")
        return f"Systemeinstellung '{setting_name}' geändert"

    # 8. SQL EXEC / DELETE
    elif action in ("encexec", "encdelete"):
        sql = payload.get("sql", "").strip() if isinstance(payload, dict) else str(payload)
        first_word = sql.split()[0].upper() if sql else "SQL"
        if "events set abgerechnet=true" in sql:
            return "SQL: Termin als abgerechnet markiert"
        elif "Delete from events" in sql:
            return "SQL: Termin(e) aus Kalender gelöscht"
        return f"SQL-Operation ({first_word}): {sql[:50]}..."

    return f"{action.upper()} {table}" if table else action.upper()


def compute_field_diff(prev_payload, current_payload):
    """Compare two payload dicts and return changed fields."""
    if not isinstance(prev_payload, dict) or not isinstance(current_payload, dict):
        return None

    diff = {}
    all_keys = set(prev_payload.keys()) | set(current_payload.keys())
    for k in all_keys:
        old_val = prev_payload.get(k)
        new_val = current_payload.get(k)
        if old_val != new_val:
            diff[k] = {
                "old": old_val,
                "new": new_val
            }
    return diff
