import re
import json

def format_german_date(val):
    """Converts YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS to German DD.MM.YYYY format."""
    if not isinstance(val, str) or not val:
        return val

    # ISO datetime: 2026-08-18T09:15:00+02:00 or 2026-08-18 09:15:00
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}:\d{2})(?::\d{2})?.*$", val)
    if m:
        year, month, day, time = m.groups()
        return f"{day}.{month}.{year} um {time} Uhr"

    # Date only: 2026-08-18
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", val)
    if m:
        year, month, day = m.groups()
        return f"{day}.{month}.{year}"

    # Replace any embedded YYYY-MM-DD dates in text
    def replace_date(match):
        y, m, d = match.groups()
        return f"{d}.{m}.{y}"
    
    return re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", replace_date, val)


def extract_patient_name(data):
    """Extract patient or user name from data dictionary."""
    if not isinstance(data, dict):
        return None
    
    # Direct patient fields (p_vname + p_name)
    if "p_name" in data or "p_vname" in data:
        vname = data.get("p_vname", "") or ""
        name = data.get("p_name", "") or ""
        full = f"{vname} {name}".strip()
        if full:
            return full

    if "patient" in data:
        pat = data["patient"]
        if isinstance(pat, str):
            lines = pat.split('\n')
            return lines[0].strip() if lines else pat.strip()
        elif isinstance(pat, dict):
            return extract_patient_name(pat)

    # User / Person fields (vorname, nachname, vname, name, first_name, last_name)
    vname = data.get("vorname") or data.get("vname") or data.get("first_name") or data.get("firstname") or ""
    name = data.get("nachname") or data.get("name") or data.get("last_name") or data.get("lastname") or ""

    if vname or name:
        full = f"{vname} {name}".strip()
        if full and len(full) > 1:
            return full

    # Display name / full name / username / benutzername
    for key in ("display_name", "fullname", "full_name", "benutzername", "username"):
        if data.get(key) and isinstance(data[key], str):
            return str(data[key]).strip()

    # Fallback to email / mail / login
    for key in ("email", "mail", "emailadresse", "login"):
        if data.get(key) and isinstance(data[key], str):
            return str(data[key]).strip()

    return None

def get_business_description(entry, entity_names=None):
    action = entry.get("action")
    table = entry.get("table")
    payload = entry.get("payload") or {}
    entity_names = entity_names or {}

    if entry.get("error") or not action:
        return "Nicht lesbare Zeile (unbekanntes Log-Format)"

    if not isinstance(payload, dict):
        return f"{action.upper()} {table}" if table else action.upper()

    # Try direct name first, then fallback to lookup in entity_names
    patient_name = extract_patient_name(payload)
    if not patient_name:
        pat_id = payload.get("patient_id") or payload.get("patienten_id") or payload.get("refid") or payload.get("id")
        if pat_id and pat_id in entity_names:
            patient_name = entity_names[pat_id]

    # 1. EVENTS
    if table == "events":
        title = payload.get("title", "Termin")
        start = payload.get("start", "")
        start_fmt = format_german_date(start)

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
                if patient_name:
                    return f"Rechnung #{rechnungnr} ({referenz}) für {patient_name} aktualisiert"
                return f"Rechnung #{rechnungnr} ({referenz}) aktualisiert"
            if patient_name:
                return f"Rechnung ({referenz}) für {patient_name} aktualisiert"
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
        name = patient_name or payload.get("id", "")[:8]
        if action == "update":
            if "p_zuzahlungsbefreit_bis" in payload:
                bis = format_german_date(payload.get("p_zuzahlungsbefreit_bis"))
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
        pat_addon = f" für {patient_name}" if patient_name else ""
        if action == "insert":
            return f"Rezept #{rezeptnr}{diag_str}{pat_addon} angelegt"
        return f"Rezept #{rezeptnr}{diag_str}{pat_addon} aktualisiert"

    elif table == "rezepte_events":
        if action == "insert":
            return "Rezept-Verknüpfung (Event zu Rezept) hinzugefügt"
        return "Rezept-Verknüpfung aktualisiert"

    # 6. HISTORY
    elif table == "history":
        stichwort = payload.get("stichwort", "Notiz")
        text = payload.get("text", "")
        snippet = f": {text[:40]}..." if len(text) > 40 else (f": {text}" if text else "")
        pat_addon = f" für Patient {patient_name}" if patient_name else ""
        return f"Historie-Eintrag '{stichwort}'{pat_addon}{snippet}"

    # 7. SETTINGS
    elif table == "settings":
        setting_name = payload.get("name", "Einstellungen")
        return f"Systemeinstellung '{setting_name}' geändert"

    # 8. SQL EXEC / DELETE
    elif action in ("encexec", "encdelete"):
        sql = payload.get("sql", "").strip() if isinstance(payload, dict) else str(payload)
        params = payload.get("params", {}) if isinstance(payload, dict) else {}
        target = params.get("id") or params.get("rechnungid") or params.get("group_id")
        target_name = entity_names.get(target) if target else None

        first_word = sql.split()[0].upper() if sql else "SQL"
        if "events set abgerechnet=true" in sql:
            if target_name:
                return f"SQL: Termin für {target_name} als abgerechnet markiert"
            return "SQL: Termin als abgerechnet markiert"
        elif "Delete from events" in sql:
            return "SQL: Termin(e) aus Kalender gelöscht"
        return f"SQL-Operation ({first_word}): {format_german_date(sql[:50])}..."

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
