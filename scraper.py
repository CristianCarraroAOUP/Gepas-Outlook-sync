"""
GEPAS → ICS Generator
Chiama direttamente il backend gepas-api.perlapa.gov.it
per leggere gli scioperi "Istruzione e Ricerca" e generare un .ics.
"""

import os
import re
import uuid
import requests
from datetime import datetime, timedelta

OUTPUT_FILE     = "docs/scioperi.ics"
GEPAS_URL       = "https://crusc-gepas.perlapa.gov.it/home"
COMPARTO_TARGET = "istruzione e ricerca"

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
    """Scarica tutti gli scioperi pubblicati paginando l'API."""
    tutti = []
    page = 1

    while True:
        params = {
            "pageNumber": page,
            "pageSize": 100,
            "ScioperoDeiProssimi30Giorni": "false",
            "OrderBy": "DataInizioSciopero",
            "Ascending": "true",
        }
        url = BASE_API
        print(f"[API] Pagina {page}: {url}")
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
            print(f"[API] Status: {resp.status_code}")
            resp.raise_for_status()
            data = resp.json()
            print(f"[API] Risposta: {str(data)[:300]}")
        except Exception as e:
            print(f"[API] Errore: {e}")
            break

        # Estrai lista records
        records = []
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            for k in ["content", "data", "items", "results", "scioperi", "list", "rows"]:
                if isinstance(data.get(k), list):
                    records = data[k]
                    break

        if not records:
            print(f"[API] Nessun record in pagina {page}, fine paginazione.")
            break

        print(f"[API] Pagina {page}: {len(records)} scioperi")
        tutti.extend(records)

        # Se la pagina è incompleta siamo all'ultima
        if len(records) < 100:
            break
        page += 1

    print(f"[API] Totale scioperi scaricati: {len(tutti)}")
    return tutti


# ── 2. FILTRA PER ISTRUZIONE E RICERCA ────────
def filtra_istruzione(records):
    risultati = []
    for item in records:
        # Cerca il comparto in tutti i possibili campi
        comparto = str(
            item.get("comparto") or
            item.get("compartoArea") or
            item.get("settore") or
            item.get("area") or
            item.get("compartoDescrizione") or
            item.get("tipoComparto") or
            item.get("comparti") or ""
        ).lower()

        # Cerca anche nella descrizione
        descrizione = str(item.get("denominazioneSciopero") or item.get("descrizione") or "").lower()

        if COMPARTO_TARGET in comparto or COMPARTO_TARGET in descrizione:
            s = parse_item(item)
            if s:
                risultati.append(s)
                print(f"[FILTRO] ✅ Trovato: {s['titolo']} – {s['data_inizio']}")

    return risultati


def parse_item(item):
    try:
        # Cerca date in tutti i possibili campi
        data_inizio = normalizza_data(
            item.get("dataInizioSciopero") or
            item.get("dataInizio") or
            item.get("data_inizio") or
            item.get("dataSciopero") or
            item.get("data") or
            item.get("startDate") or ""
        )
        data_fine = normalizza_data(
            item.get("dataFineSciopero") or
            item.get("dataFine") or
            item.get("data_fine") or
            item.get("endDate") or
            data_inizio
        )
        if not data_inizio:
            return None

        sindacato = (
            item.get("organizzazione") or
            item.get("sindacato") or
            item.get("soggettoProclamante") or
            item.get("organizzazioni") or
            item.get("sigle") or ""
        )
        if isinstance(sindacato, list):
            sindacato = ", ".join(
                str(x.get("sigla") or x.get("nome") or x.get("denominazione") or x)
                if isinstance(x, dict) else str(x)
                for x in sindacato
            )

        titolo = (
            item.get("denominazioneSciopero") or
            item.get("descrizione") or
            item.get("titolo") or
            "Sciopero – Istruzione e Ricerca"
        )

        return {
            "uid":         str(item.get("id") or item.get("uid") or uuid.uuid4()),
            "titolo":      titolo,
            "data_inizio": data_inizio,
            "data_fine":   data_fine,
            "sindacato":   str(sindacato),
            "note":        str(item.get("note") or item.get("motivazione") or ""),
        }
    except Exception as e:
        print(f"[WARN] Errore parsing: {e}")
        return None


def normalizza_data(valore):
    if not valore:
        return ""
    valore = str(valore).strip()
    # ISO: 2026-05-06 o 2026-05-06T00:00:00
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", valore)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    # Italiano: 06/05/2026
    m = re.match(r"(\d{2})[/\-](\d{2})[/\-](\d{4})", valore)
    if m:
        return f"{m.group(3)}{m.group(2)}{m.group(1)}"
    # Timestamp ms
    if re.match(r"^\d{13}$", valore):
        dt = datetime.utcfromtimestamp(int(valore) / 1000)
        return dt.strftime("%Y%m%d")
    return ""


# ── 3. GENERA ICS ──────────────────────────────
def genera_ics(scioperi):
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

    for s in scioperi:
        data_inizio   = s["data_inizio"]
        data_fine_raw = s.get("data_fine") or data_inizio
        try:
            data_fine_ics = (
                datetime.strptime(data_fine_raw, "%Y%m%d") + timedelta(days=1)
            ).strftime("%Y%m%d")
        except Exception:
            data_fine_ics = data_inizio

        sindacato = (s.get("sindacato") or "").strip()
        note      = (s.get("note") or "").strip()
        soggetto  = "SCIOPERO - Istruzione e Ricerca"
        if sindacato:
            soggetto += f" ({sindacato[:60]})"

        descrizione = "Comparto: Istruzione e Ricerca"
        if sindacato:
            descrizione += f"\\nSindacato: {sindacato}"
        if note:
            descrizione += f"\\nNote: {note[:200]}"
        descrizione += f"\\n\\nFonte: {GEPAS_URL}"

        lines += [
            "BEGIN:VEVENT",
            f"UID:{s.get('uid', str(uuid.uuid4()))}-gepas@scioperi",
            f"DTSTAMP:{ora}",
            f"DTSTART;VALUE=DATE:{data_inizio}",
            f"DTEND;VALUE=DATE:{data_fine_ics}",
            f"SUMMARY:{soggetto}",
            f"DESCRIPTION:{descrizione}",
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

    # Scarica tutti gli scioperi dal backend reale
    tutti_scioperi = scarica_scioperi()

    # Filtra solo "Istruzione e Ricerca"
    scioperi = filtra_istruzione(tutti_scioperi)
    print(f"[OK] Scioperi Istruzione e Ricerca: {len(scioperi)}")

    if not scioperi:
        print("[WARN] Nessuno sciopero trovato per Istruzione e Ricerca.")
        # Stampa i comparti disponibili per debug
        comparti = set()
        for item in tutti_scioperi[:20]:
            c = (item.get("comparto") or item.get("compartoArea") or
                 item.get("settore") or item.get("area") or "?")
            comparti.add(str(c).lower())
        if comparti:
            print(f"[DEBUG] Comparti disponibili nei primi 20 record: {comparti}")

    os.makedirs("docs", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(genera_ics(scioperi))

    print(f"[FINE] {OUTPUT_FILE} generato con {len(scioperi)} eventi")
    print("=" * 55)


if __name__ == "__main__":
    main()
