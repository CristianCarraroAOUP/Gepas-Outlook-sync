"""
GEPAS → ICS Generator
Chiama direttamente gepas-api.perlapa.gov.it,
filtra gli scioperi con descrizioneComparto="ISTRUZIONE RICERCA"
e genera un file .ics per Outlook.
- Descrizione semplificata (solo comparto e fonte)
- Deduplicazione per titolo + data
"""

import os
import uuid
import requests
from datetime import datetime, timedelta, timezone

OUTPUT_FILE = "docs/scioperi.ics"
GEPAS_URL   = "https://crusc-gepas.perlapa.gov.it/home"
FILTRO      = "istruzione ricerca"

BASE_API = "https://gepas-api.perlapa.gov.it/api/Public/Scioperi/Pubblicati"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "it-IT,it;q=0.9",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://crusc-gepas.perlapa.gov.it/",
    "Origin": "https://crusc-gepas.perlapa.gov.it",
}


# ── 1. SCARICA TUTTI GLI SCIOPERI ─────────────
def scarica_scioperi():
    tutti = []
    page  = 1
    while True:
        params = {
            "pageNumber": page,
            "pageSize":   100,
            "ScioperoDeiProssimi30Giorni": "false",
            "OrderBy":    "DataInizioSciopero",
            "Ascending":  "true",
        }
        print(f"[API] Pagina {page}...")
        try:
            resp = requests.get(BASE_API, headers=HEADERS, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[API] Errore: {e}")
            break

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


# ── 2. FILTRA E DEDUPLICA ─────────────────────
def filtra_e_parse(records):
    eventi = []
    chiavi_viste = set()  # per deduplicazione: (titolo_normalizzato, data)

    for item in records:
        # Cerca dateSciopero che coinvolgono ISTRUZIONE RICERCA
        for ds in item.get("dateSciopero", []):
            trovato = any(
                FILTRO in str(c.get("descrizioneComparto", "")).lower()
                for c in ds.get("compartiCoinvolti", [])
            )
            if not trovato:
                continue

            data_inizio = timestamp_ms_to_date(ds.get("data", ""))
            if not data_inizio:
                continue

            titolo = (
                item.get("denominazioneSciopero") or
                item.get("descrizione") or
                "Sciopero – Istruzione e Ricerca"
            ).replace("\n", " ").replace("\r", " ").strip()

            # Chiave di deduplicazione: titolo normalizzato + data
            chiave = (titolo.lower(), data_inizio)
            if chiave in chiavi_viste:
                print(f"[SKIP] Duplicato: {data_inizio} – {titolo[:60]}")
                continue
            chiavi_viste.add(chiave)

            print(f"[OK] {data_inizio} – {titolo[:60]}")
            eventi.append({
                "uid":         str(item.get("id") or uuid.uuid4()),
                "titolo":      titolo,
                "data_inizio": data_inizio,
            })

    return eventi


def timestamp_ms_to_date(valore):
    if not valore:
        return ""
    try:
        ts = int(str(valore).strip())
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        return dt.strftime("%Y%m%d")
    except Exception:
        return ""


# ── 3. GENERA ICS ──────────────────────────────
def genera_ics(eventi):
    ora = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//GEPAS Sync//Scioperi Istruzione e Ricerca//IT",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Scioperi - Istruzione e Ricerca",
        "X-WR-TIMEZONE:Europe/Rome",
        f"X-WR-CALDESC:Aggiornato automaticamente da {GEPAS_URL}",
        "REFRESH-INTERVAL;VALUE=DURATION:P1D",
        "X-PUBLISHED-TTL:P1D",
    ]

    for e in eventi:
        data_inizio = e["data_inizio"]
        try:
            data_fine = (datetime.strptime(data_inizio, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
        except Exception:
            data_fine = data_inizio

        lines += [
            "BEGIN:VEVENT",
            f"UID:{e['uid']}-{data_inizio}-gepas@scioperi",
            f"DTSTAMP:{ora}",
            f"DTSTART;VALUE=DATE:{data_inizio}",
            f"DTEND;VALUE=DATE:{data_fine}",
            f"SUMMARY:{e['titolo']}",
            f"DESCRIPTION:Comparto: Istruzione e Ricerca\\n\\nFonte: {GEPAS_URL}",
            "CATEGORIES:Sciopero",
            "STATUS:CONFIRMED",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


# ── 4. MAIN ────────────────────────────────────
def main():
    print("=" * 55)
    print("  GEPAS → ICS Generator")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    tutti  = scarica_scioperi()
    eventi = filtra_e_parse(tutti)
    print(f"[OK] Eventi unici 'ISTRUZIONE RICERCA': {len(eventi)}")

    os.makedirs("docs", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(genera_ics(eventi))

    print(f"[FINE] {OUTPUT_FILE} generato con {len(eventi)} eventi")
    print("=" * 55)


if __name__ == "__main__":
    main()
