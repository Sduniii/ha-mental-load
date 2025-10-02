# Mental Load Assistant for Home Assistant

Dieses Projekt stellt eine benutzerdefinierte Home-Assistant-Integration bereit, die Kalender-Einträge und manuelle Aufgaben automatisch in übersichtliche Schritte aufteilt und nach Mental-Load-Kriterien strukturiert. Die erzeugten Aufgaben erscheinen als To-do-/Kanban-Liste innerhalb von Home Assistant.

## Funktionsumfang

- **Kalender-Analyse**: Überwachte Kalender (Google, Microsoft, lokale Kalender usw.) werden regelmäßig abgefragt. Jeder Termin wird per KI analysiert und in konkrete To-dos zerlegt.
- **Manuelle Aufgaben**: Eigene Einträge lassen sich direkt in der To-do-Liste oder per Service hinzufügen. Auch diese Aufgaben werden automatisch in Unteraufgaben aufgeteilt.
- **Mental-Load-Bewertung**: Für jede Aufgabe werden Hinweise zur mentalen Belastung sowie optionale Notizen bereitgestellt.
- **Fortschrittsstatus**: Aufgaben können als "In Bearbeitung" markiert werden, um laufende Arbeiten hervorzuheben.
- **Fallback ohne API-Schlüssel**: Falls kein KI-Dienst konfiguriert ist oder der Aufruf fehlschlägt, greift eine nachvollziehbare Heuristik zur Generierung der Teilaufgaben.
- **Service-Aufrufe**: Über `mental_load_assistant.add_manual_task` können Aufgaben samt Kontext (Beschreibung, Fälligkeitsdatum, Haushaltsinformationen) per Automatisierung hinzugefügt werden.

## Installation

1. Kopiere den Ordner `custom_components/mental_load_assistant` in dein Home-Assistant-Konfigurationsverzeichnis.
2. Starte Home Assistant neu.
3. Öffne *Einstellungen → Geräte & Dienste → Integration hinzufügen* und suche nach **Mental Load Assistant**.
4. Wähle die Kalender aus, die analysiert werden sollen. Optional kann ein KI-Anbieter (OpenAI oder Google Gemini), ein API-Schlüssel und ein Modellname hinterlegt werden.

### Installation über HACS

1. Öffne HACS in Home Assistant und wähle **Integrationen**.
2. Klicke rechts oben auf die drei Punkte und wähle **Benutzerdefiniertes Repository**.
3. Gib die URL dieses GitHub-Repositories an und wähle als Kategorie **Integration**.
4. Stelle sicher, dass du ein getaggtes Release (z.B. `v0.2.0` oder neuer) auswählst – reine Commit-Stände wie `62157c0` können von HACS nicht verarbeitet werden.
5. Nach dem Hinzufügen erscheint *Mental Load Assistant* als installierbare Integration in HACS. Installiere sie und starte Home Assistant neu.
6. Richte die Integration anschließend wie oben beschrieben ein.

> [!IMPORTANT]
> HACS benötigt veröffentlichte Releases, um Updates nachzuverfolgen. Verwende daher immer eine Release-Version und nicht einzelne Commit-Archive.

## Optionen

- **KI-Anbieter**: Auswahl zwischen OpenAI (Standard) und Google Gemini. Für Gemini wird ein API-Schlüssel von Google AI Studio benötigt.
- **Modell**: Name des Chat-Modells (Standard: `gpt-4o-mini` für OpenAI bzw. `gemini-1.5-flash` als bewährter Startpunkt für Gemini).
- **Abfrageintervall**: Wie oft Kalender synchronisiert werden.
- **Zeithorizont**: Zeitraum in die Zukunft, der aus dem Kalender analysiert wird.

## Services

```yaml
domain: mental_load_assistant
service: add_manual_task
data:
  summary: "Solaranlage reparieren"
  description: "Wechselrichter zeigt Fehlercode an"
  due: "2024-07-01T18:00:00+02:00"
  household_context: "Eigenheim mit PV-Anlage"
```

```yaml
domain: mental_load_assistant
service: mark_task_in_progress
data:
  uid: "5b3c9ef6-6a7d-4c55-9d60-6b66d1c95f44"
```

## Hinweise zur KI-Nutzung

- Die Integration unterstützt sowohl die OpenAI-kompatible Chat-Completions-API als auch die Google-Gemini-`generateContent`-API. API-Schlüssel werden ausschließlich zur Aufgabengenerierung genutzt.
- Ohne gültigen Schlüssel oder bei Kommunikationsproblemen werden sinnvolle Standard-Aufgaben erzeugt, damit die Liste nutzbar bleibt.
- Die erzeugten Aufgaben enthalten zusätzliche Metadaten (Quelle, Elternaufgabe, Mental-Load-Notizen) und können wie jede andere To-do-Liste in Home Assistant verwendet werden.

## Weiterentwicklung

- Unterstützung weiterer KI-Anbieter über konfigurierbare Endpunkte
- Persistente Speicherung bereits analysierter Ereignisse über den Neustart hinaus
- Erstellen mehrerer Listen mit unterschiedlichen Kalenderquellen
