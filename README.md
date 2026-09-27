# 📊 PyLogAnalyzer

> Eine moderne, leistungsstarke Standalone-Desktop-Anwendung zur Analyse, Aufbereitung und Abfrage komplexer Software-Logdateien mit automatischer Stammdaten-Verknüpfung und interaktiver SQL-Konsole.

![Python Version](https://img.shields.io/badge/python->=3.11-3776AB?style=flat&logo=python&logoColor=white)
![Package Manager](https://img.shields.io/badge/uv-supported-DE5B8D?style=flat&logo=astral&logoColor=white)
![GUI Framework](https://img.shields.io/badge/GUI-pywebview-blue?style=flat)
![Database](https://img.shields.io/badge/SQL-SQLite%20(in--memory)-003B57?style=flat&logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green?style=flat)

---

## 📋 Übersicht

Das Lesen und Analysieren technischer Logdateien aus Softwaresystemen kann aufgrund verschachtelter JSON-Payloads, kryptischer IDs und unübersichtlicher Zeilenmengen extrem zeitaufwendig sein. **PyLogAnalyzer** löst dieses Problem:

Er verwandelt unstrukturierte oder komplexe Log-Einträge in eine **menschenlesbare, chronologische Zeitleiste**, löst technische Referenz-IDs (wie Patienten-, Nutzer- oder Termin-IDs) automatisch in echte Namen auf und stellt eine **integrierte SQL-Konsole** für tiefergehende Auswertungen bereit.

---

## ✨ Hauptfunktionen

### 🔍 1. Klartext-Übersetzung & Chronologische Timeline

- **Automatische Aufbereitung**: Verwandelt Rohdaten (z. B. `update events id {"title":"Sensomotorisch-perz..."}`) in verständliche Sätze (z. B. *„Termin aktualisiert: Sensomotorisch-perz. Beh. für Ursula Wintzen“*).
- **Rausch-Reduzierung**: Fasst schnelle, aufeinanderfolgende Tastatureingaben und Tipp-Änderungen automatisch in übersichtliche Einheiten zusammen.
- **Anomalie-Erkennung**: Highlights bei `NULL`-Parametern in SQL-Befehlen, Gleitkomma-Ungenauigkeiten oder Löschvorgängen.

### 📂 2. Multi-Logdateien Import & ZIP-Archiv Support

- **Mehrfachauswahl**: Beliebig viele Logdateien (`.log`, `.txt`, `.json`) gleichzeitig auswählen oder direkt ein `.zip`-Archiv hochladen.
- **Einheitliche Zeitleiste**: Führt alle Zeilen aus allen Dateien automatisch nach Datum/Uhrzeit sortiert zusammen.
- **Quelldatei-Badges & Filter**: Farbige Dateinamen-Kennzeichnungen pro Zeile sowie ein Dropdown-Filter zur gezielten Auswahl einzelnen Logdateien.

### 👤 3. Namensauflösung & Stammdaten-Import

- **2-Pass Entitäts-Indexing**: Liest Namen direkt aus den Logdaten oder importiert externe Datenbanktabellen (`patienten`, `users`, `events`, `rezepte`, `rechnung` etc.).
- **Unterstützte Stammdaten-Formate**: CSV, JSON, SQLite-Datenbanken (`.db`, `.sqlite`) oder ZIP-Archive mit Stammdaten.
- **Nutzer- & Patienten-Zuordnung**: Löst IDs in Vor- und Nachnamen oder E-Mail-Adressen auf (z. B. `👤 Max Mustermann` statt `MKXR5SKB-BU684`).

### 🏷️ 4. Typ-Klassifizierung & Entitäts-Tracer

- **IDs auf einen Blick**: Automatische Badges für Entitäts-Typen (`Group-ID`, `Patient-ID`, `Termin-ID`, `Rechnungs-ID`, `Nutzer-ID`).
- **1-Klick Timeline Filter**: Ein Klick auf eine ID im Entitäts-Tracer filtert die gesamte Master-Zeitleiste auf alle Ereignisse dieser Entität.

### 💻 5. Interaktive SQL-Konsole

- **In-Memory SQLite Engine**: Wandelt Logeinträge und importierte Stammdaten automatisch in abfragbare relationalen SQL-Tabellen um.
- **Vollwertiges SQL**: Unterstützt `SELECT`, `JOIN`, `UPDATE`, `INSERT` und `CREATE TABLE`.
- **Komfort-Features**: Visual Schema Browser (Tabellennamen & Zeilenanzahl), SQL-Vorlagen, `Ctrl+Enter` Tastenkürzel und CSV-Export.

### 🎨 6. Flexible Benutzeroberfläche

- **Anpassbare Spaltenbreiten**: Spalten der Haupttabelle lassen sich bequem per Drag & Drop in der Breite verstellen.
- **Resizable Split-Screen**: Flexibles Anpassen des Größenverhältnisses zwischen Timeline und Detail-Inspector.
- **Dark & Light Mode**: Nahtloser Wechsel zwischen hellem und dunklem Design.

---

## 🛠️ Technologien

- **Backend**: Python 3.11+
- **Desktop Window**: `pywebview` (Native Windows GUI Frame)
- **Database Engine**: SQLite 3 (In-Memory `:memory:`)
- **Frontend**: HTML5, Vanilla CSS3 (Custom Design System, Glassmorphism, CSS Variables), JavaScript (ES6+)
- **Package Manager & Tooling**: `uv`, PyInstaller

---

## 🚀 Installation & Schnellstart

### Voraussetzungen

- Python `>= 3.11`
- Empfohlen: [`uv`](https://github.com/astral-sh/uv) als extrem schneller Package Manager.

### 1. Repository klonen

```bash
git clone https://github.com/IhrUsername/py-log-analyzer.git
cd py-log-analyzer
```

### 2. Abhängigkeiten installieren

#### Mit `uv` (Empfohlen)

```bash
uv sync --extra dev
```

#### Alternativ mit Standard `pip`

```bash
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
pip install pywebview pyinstaller
```

### 3. Anwendung starten (Entwicklungsmodus)

```bash
python app.py
```

---

## 📦 Standalone Exe erstellen (`.exe`)

Um eine eigenständig ausführbare Windows `.exe`-Datei im Ordner `dist/` zu erstellen:

```bash
uv run pyinstaller --onefile --noconsole --name "PyLogAnalyzer" --add-data "index.html;." --add-data "style.css;." --add-data "gui.js;." --add-data "sample.log;." app.py
```

Nach dem Build-Vorgang finden Sie die einsatzbereite Datei unter:
`dist/PyLogAnalyzer.exe`

---

## 📁 Projektstruktur

```text
py-log-analyzer/
├── app.py              # Haupt-Backend & HTTP API Server mit pywebview Frame
├── parser.py           # Log-Line Parsing Engine & Multi-File / ZIP Reader
├── analyzer.py         # 2-Pass Indexing Engine, Entitäts-Resolution & Anomalien
├── mapper.py           # Business-Logik für Klartext-Beschreibungen & Namen
├── sql_engine.py       # In-Memory SQLite Query Engine & Schema Inspector
├── index.html          # Frontend Struktur (Master-Timeline, Inspector, SQL Konsole)
├── style.css           # Styling System (Dark/Light Mode, Custom Layout, Badges)
├── gui.js              # Interaktive Client-Logik & Event Handler
├── sample.log          # Beispiel-Logdatei zum direkten Testen
├── pyproject.toml      # Projektkonfiguration & Dependencies
└── README.md           # Dokumentation
```

---

## 🧪 Tests ausführen

Zur Überprüfung aller Komponenten stehen Unittests bereit:

```bash
# Analyzer Tests ausführen
python test_analyzer.py

# SQL Engine Tests ausführen
python test_sql_engine.py
```

---

## 📄 Lizenz

Dieses Projekt ist unter der **MIT-Lizenz** lizenziert. Weitere Details finden Sie in der Datei `LICENSE`.
