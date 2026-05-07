"""
GEPAS → ICS Generator
Chiama direttamente gepas-api.perlapa.gov.it,
filtra gli scioperi con compartoId=121 / descrizioneComparto="ISTRUZIONE RICERCA"
e genera un file .ics per Outlook.
"""

import os
import re
import uuid
import json
import requests
from datetime import datetime, timedelta, timezone

OUTPUT_FILE = "docs/scioperi.ics"
GEPAS_URL   = "https://crusc-gepas.perlapa.gov.it/home"
FILTRO      = "istruzione ricerca"   # case-insensitive, esatto

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


# ── 2. CONTROLLA SE UN RECORD RIGUARDA ISTRUZIONE RICERCA ──
def contiene_istruzione_ricerca(item):
    """
    Cerca 'ISTRUZIONE RICERCA' dentro dateSciopero → compartiCoinvolti → descrizioneComparto.
    Restituisce le dateSciopero che contengono il comparto cercato.
    """
    date_trovate = []
    for data_sciopero in item.get("dateSciopero", []):
        for comparto in data_sciopero.get("compartiCoinvolti", []):
            desc = str(comparto.get("descrizioneComparto", "")).lower()
            if FILTRO in desc:
                date_trovate.append(data_sciopero)
                break  # basta trovarlo una volta per questa data
    return date_trovate


# ── 3. FILTRA E GENERA EVENTI ─────────────────
def filtra_e_parse(records):
    eventi = []
    for item in records:
        date_istruzione = contiene_istruzione_ricerca(item)
        if not date_istruzione:
            continue

        titolo = (
            item.get("denominazioneSciopero") or
            item.get("descrizione") or
            "Sciopero – Istruzione e Ricerca"
        )
        print(f"[FILTRO] ✅ {titolo[:70]}")

        # Un evento per ogni data dello sciopero che coinvolge Istruzione Ricerca
        for ds in date_istruzione:
            data_inizio = timestamp_ms_to_date(ds.get("data", ""))
            if not data_inizio:
                continue

            # PROCLAMATO DA: sigleSindacaliCheIndicono
            proclamato = ds.get("sigleSindacaliCheIndicono", [])
            if isinstance(proclamato, list):
                proclamato_str = ", ".join(str(x) for x in proclamato)
            else:
                proclamato_str = str(proclamato)

            # SOGGETTI COINVOLTI: soggettiCoinvolti del record specifico
            soggetti_str = str(ds.get("soggettiCoinvolti", ""))

            # Cerca anche soggetti specifici per comparto Istruzione Ricerca
            for comparto in ds.get("compartiCoinvolti", []):
                desc = str(comparto.get("descrizioneComparto", "")).lower()
                if FILTRO in desc:
                    qualifiche = comparto.get("qualifiche", [])
                    if qualifiche and not soggetti_str:
                        soggetti_str = ", ".join(
                            str(q.get("descrizione", "")) for q in qualifiche
                        )
                    break

            eventi.append({
                "uid":           str(item.get("id") or uuid.uuid4()),
                "titolo":        titolo,
                "data_inizio":   data_inizio,
                "data_fine":     data_inizio,  # stessa giornata
                "proclamato_da": proclamato_str,
                "soggetti":      soggetti_str,
            })

    return eventi


def timestamp_ms_to_date(valore):
    """Converte timestamp in millisecondi (es. 1780012800000) in YYYYMMDD."""
    if not valore:
        return ""
    try:
        ts = int(str(valore).strip())
        dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
        return dt.strftime("%Y%m%d")
    except Exception:
        return ""


# ── 4. GENERA ICS ──────────────────────────────
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
            data_fine = (
                datetime.strptime(data_inizio, "%Y%m%d") + timedelta(days=1)
            ).strftime("%Y%m%d")
        except Exception:
            data_fine = data_inizio

        proclamato_da = (e.get("proclamato_da") or "").strip()
        soggetti      = (e.get("soggetti") or "").strip()

        descrizione = "Comparto: Istruzione e Ricerca"
        if proclamato_da:
            descrizione += f"\\nPROCLAMATO DA: {proclamato_da}"
        if soggetti:
            descrizione += f"\\nSOGGETTI COINVOLTI: {soggetti}"
        descrizione += f"\\n\\nFonte: {GEPAS_URL}"

        # Sanifica il titolo (rimuove newline)
        titolo = e["titolo"].replace("\n", " ").replace("\r", " ")

        lines += [
            "BEGIN:VEVENT",
            f"UID:{e['uid']}-{data_inizio}-gepas@scioperi",
            f"DTSTAMP:{ora}",
            f"DTSTART;VALUE=DATE:{data_inizio}",
            f"DTEND;VALUE=DATE:{data_fine}",
            f"SUMMARY:{titolo}",
            f"DESCRIPTION:{descrizione}",
            "CATEGORIES:Sciopero",
            "STATUS:CONFIRMED",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


# ── 5. MAIN ────────────────────────────────────
def main():
    print("=" * 55)
    print("  GEPAS → ICS Generator")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    tutti  = scarica_scioperi()
    eventi = filtra_e_parse(tutti)
    print(f"[OK] Eventi 'ISTRUZIONE RICERCA': {len(eventi)}")

    os.makedirs("docs", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(genera_ics(eventi))

    print(f"[FINE] {OUTPUT_FILE} generato con {len(eventi)} eventi")
    print("=" * 55)


if __name__ == "__main__":
    main()
