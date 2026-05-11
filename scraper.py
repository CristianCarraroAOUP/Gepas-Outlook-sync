“””
GEPAS → ICS Generator
Chiama direttamente gepas-api.perlapa.gov.it,
filtra gli scioperi con descrizioneComparto=“ISTRUZIONE RICERCA”.

- Un evento per ogni sciopero (nessuna deduplicazione)
- Oggetto: [STATO] Titolo
- Descrizione: PROCLAMATO DA, COMPARTI PA, SOGGETTI COINVOLTI, SINDACATI ADERENTI
  “””

import os
import uuid
import requests
from datetime import datetime, timedelta, timezone

OUTPUT_FILE = “docs/scioperi.ics”
GEPAS_URL   = “https://crusc-gepas.perlapa.gov.it/home”
FILTRO      = “istruzione ricerca”

BASE_API = “https://gepas-api.perlapa.gov.it/api/Public/Scioperi/Pubblicati”

HEADERS = {
“Accept”: “application/json, text/plain, */*”,
“Accept-Language”: “it-IT,it;q=0.9”,
“User-Agent”: “Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36”,
“Referer”: “https://crusc-gepas.perlapa.gov.it/”,
“Origin”: “https://crusc-gepas.perlapa.gov.it”,
}

# ── 1. SCARICA TUTTI GLI SCIOPERI ─────────────

def scarica_scioperi():
tutti = []
page  = 1
while True:
params = {
“pageNumber”: page,
“pageSize”:   100,
// rimosso filtro 30 giorni
“OrderBy”:    “DataInizioSciopero”,
“Ascending”:  “true”,
}
print(f”[API] Pagina {page}…”)
try:
resp = requests.get(BASE_API, headers=HEADERS, params=params, timeout=20)
resp.raise_for_status()
data = resp.json()
except Exception as e:
print(f”[API] Errore: {e}”)
break

```
    records = data if isinstance(data, list) else next(
        (data[k] for k in ["content","data","items","results","scioperi","list","rows"]
         if isinstance(data.get(k), list)), []
    )

    if not records:
        break

    print(f"[API] Pagina {page}: {len(records)} record")
    tutti.extend(records)

    if len(records) < 100:
        break
    page += 1

print(f"[API] Totale record scaricati: {len(tutti)}")
return tutti
```

# ── 2. FILTRA E PARSE ─────────────────────────

def filtra_e_parse(records):
eventi = []

```
for item in records:
    titolo = (
        item.get("denominazioneSciopero") or
        item.get("descrizione") or
        "Sciopero – Istruzione e Ricerca"
    ).replace("\n", " ").replace("\r", " ").strip()

    # Stato sciopero (es. "pubblicato", "revocato", ecc.)
    stato_raw = ""
    stato_obj = item.get("statoSciopero")
    if isinstance(stato_obj, dict):
        stato_raw = str(stato_obj.get("descrizione") or "").strip()
    elif isinstance(stato_obj, str):
        stato_raw = stato_obj.strip()
    stato = stato_raw.upper() if stato_raw else ""

    item_id = str(item.get("id") or uuid.uuid4())

    for idx, ds in enumerate(item.get("dateSciopero", [])):
        # Controlla se questa data coinvolge ISTRUZIONE RICERCA
        comparti_istruzione = [
            c for c in ds.get("compartiCoinvolti", [])
            if FILTRO in str(c.get("descrizioneComparto", "")).lower()
        ]
        if not comparti_istruzione:
            continue

        data_inizio = timestamp_ms_to_date(ds.get("data", ""))
        if not data_inizio:
            continue

        # PROCLAMATO DA
        proclamato = ds.get("sigleSindacaliCheIndicono", [])
        proclamato_str = ", ".join(str(x).strip() for x in proclamato) if proclamato else ""

        # SINDACATI ADERENTI
        aderenti = ds.get("sigleSindacaliChePartecipano", [])
        aderenti_str = ", ".join(str(x).strip() for x in aderenti) if aderenti else ""

        # COMPARTI PA (solo quelli istruzione ricerca)
        comparti_str = ", ".join(
            str(c.get("descrizioneComparto", "")).strip()
            for c in comparti_istruzione
        )

        # SOGGETTI COINVOLTI
        soggetti_str = str(ds.get("soggettiCoinvolti", "")).strip()
        if not soggetti_str:
            # Prendi dalle qualifiche del comparto istruzione
            qualifiche = []
            for c in comparti_istruzione:
                for q in c.get("qualifiche", []):
                    desc = str(q.get("descrizione", "")).strip()
                    if desc and desc not in qualifiche:
                        qualifiche.append(desc)
            soggetti_str = ", ".join(qualifiche)

        # Oggetto: [STATO] Titolo
        oggetto = f"[{stato}] {titolo}" if stato else titolo

        print(f"[OK] {data_inizio} – {oggetto[:70]}")

        eventi.append({
            "uid":          f"{item_id}-{idx}-gepas@scioperi",
            "oggetto":      oggetto,
            "data_inizio":  data_inizio,
            "proclamato":   proclamato_str,
            "comparti":     comparti_str,
            "soggetti":     soggetti_str,
            "aderenti":     aderenti_str,
        })

return eventi
```

def timestamp_ms_to_date(valore):
if not valore:
return “”
try:
ts = int(str(valore).strip())
dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
return dt.strftime(”%Y%m%d”)
except Exception:
return “”

# ── 3. GENERA ICS ──────────────────────────────

def genera_ics(eventi):
ora = datetime.utcnow().strftime(”%Y%m%dT%H%M%SZ”)
lines = [
“BEGIN:VCALENDAR”,
“VERSION:2.0”,
“PRODID:-//GEPAS Sync//Scioperi Istruzione e Ricerca//IT”,
“CALSCALE:GREGORIAN”,
“METHOD:PUBLISH”,
“X-WR-CALNAME:Scioperi - Istruzione e Ricerca”,
“X-WR-TIMEZONE:Europe/Rome”,
f”X-WR-CALDESC:Aggiornato automaticamente da {GEPAS_URL}”,
“REFRESH-INTERVAL;VALUE=DURATION:P1D”,
“X-PUBLISHED-TTL:P1D”,
]

```
for e in eventi:
    data_inizio = e["data_inizio"]
    try:
        data_fine = (datetime.strptime(data_inizio, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
    except Exception:
        data_fine = data_inizio

    # Costruisce descrizione
    desc_parts = []
    if e.get("proclamato"):
        desc_parts.append(f"PROCLAMATO DA: {e['proclamato']}")
    if e.get("comparti"):
        desc_parts.append(f"COMPARTI PA: {e['comparti']}")
    if e.get("soggetti"):
        desc_parts.append(f"SOGGETTI COINVOLTI: {e['soggetti']}")
    if e.get("aderenti"):
        desc_parts.append(f"SINDACATI ADERENTI: {e['aderenti']}")
    desc_parts.append(f"Fonte: {GEPAS_URL}")
    descrizione = "\\n".join(desc_parts)

    lines += [
        "BEGIN:VEVENT",
        f"UID:{e['uid']}",
        f"DTSTAMP:{ora}",
        f"DTSTART;VALUE=DATE:{data_inizio}",
        f"DTEND;VALUE=DATE:{data_fine}",
        f"SUMMARY:{e['oggetto']}",
        f"DESCRIPTION:{descrizione}",
        "CATEGORIES:Sciopero",
        "STATUS:CONFIRMED",
        "TRANSP:TRANSPARENT",
        "END:VEVENT",
    ]

lines.append("END:VCALENDAR")
return "\r\n".join(lines)
```

# ── 4. MAIN ────────────────────────────────────

def main():
print(”=” * 55)
print(”  GEPAS → ICS Generator”)
print(f”  {datetime.now().strftime(’%Y-%m-%d %H:%M:%S’)}”)
print(”=” * 55)

```
tutti  = scarica_scioperi()
eventi = filtra_e_parse(tutti)
print(f"[OK] Totale eventi 'ISTRUZIONE RICERCA': {len(eventi)}")

os.makedirs("docs", exist_ok=True)
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(genera_ics(eventi))

print(f"[FINE] {OUTPUT_FILE} generato con {len(eventi)} eventi")
print("=" * 55)
```

if **name** == “**main**”:
main()