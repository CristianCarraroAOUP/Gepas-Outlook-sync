"""
GEPAS → ICS Generator - modalità DEBUG
Stampa la struttura completa dei primi 3 record per trovare
dove si trova la stringa "ISTRUZIONE RICERCA".
"""

import os
import re
import uuid
import json
import requests
from datetime import datetime, timedelta

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
            print(f"[API] Status: {resp.status_code}")
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[API] Errore: {e}")
            break

        records = []
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            for k in ["content","data","items","results","scioperi","list","rows"]:
                if isinstance(data.get(k), list):
                    records = data[k]
                    break

        if not records:
            break

        # Stampa i primi 3 record completi per debug
        if page == 1:
            print("\n" + "="*60)
            print("DEBUG: STRUTTURA COMPLETA PRIMI 3 RECORD")
            print("="*60)
            for i, r in enumerate(records[:3]):
                print(f"\n--- RECORD {i+1} ---")
                print(json.dumps(r, ensure_ascii=False, indent=2))
            print("="*60 + "\n")

            # Cerca la stringa "istruzione" in ogni record e mostra dove la trova
            print("DEBUG: RICERCA 'istruzione' NEI RECORD:")
            trovati = 0
            for i, r in enumerate(records):
                testo = json.dumps(r, ensure_ascii=False).lower()
                if "istruzione" in testo:
                    trovati += 1
                    print(f"  Record {i+1} CONTIENE 'istruzione': {r.get('denominazioneSciopero','')[:80]}")
                    # Trova esattamente in quale chiave
                    for k, v in r.items():
                        if "istruzione" in json.dumps(v, ensure_ascii=False).lower():
                            print(f"    → campo '{k}': {json.dumps(v, ensure_ascii=False)[:150]}")
            print(f"  Totale record con 'istruzione' in pagina 1: {trovati}/{len(records)}")

        tutti.extend(records)
        if len(records) < 100:
            break
        page += 1

    print(f"[API] Totale record: {len(tutti)}")
    return tutti


def filtra_istruzione(records):
    risultati = []
    for item in records:
        testo = json.dumps(item, ensure_ascii=False).lower()
        if FILTRO in testo:
            s = parse_item(item)
            if s:
                risultati.append(s)
                print(f"[FILTRO] ✅ {s['data_inizio']} – {s['titolo'][:60]}")
    return risultati


def parse_item(item):
    try:
        data_inizio = normalizza_data(
            item.get("dataInizioSciopero") or item.get("dataInizio") or
            item.get("data_inizio") or item.get("dataSciopero") or
            item.get("data") or item.get("startDate") or ""
        )
        data_fine = normalizza_data(
            item.get("dataFineSciopero") or item.get("dataFine") or
            item.get("data_fine") or item.get("endDate") or data_inizio
        )
        if not data_inizio:
            return None

        titolo = (
            item.get("denominazioneSciopero") or item.get("descrizione") or
            item.get("titolo") or "Sciopero – Istruzione e Ricerca"
        )
        proclamato_da = estrai_proclamato_da(item)
        soggetti      = estrai_soggetti(item)

        return {
            "uid":           str(item.get("id") or item.get("uid") or uuid.uuid4()),
            "titolo":        titolo,
            "data_inizio":   data_inizio,
            "data_fine":     data_fine,
            "proclamato_da": proclamato_da,
            "soggetti":      soggetti,
        }
    except Exception as e:
        print(f"[WARN] Errore parsing: {e}")
        return None


def estrai_proclamato_da(item):
    for campo in ["organizzazione","sindacato","soggettoProclamante","proclamatoDa","sigle","organizzazioni"]:
        c = item.get(campo)
        if not c:
            continue
        if isinstance(c, list):
            return ", ".join(
                str(x.get("sigla") or x.get("nome") or x.get("denominazione") or x)
                if isinstance(x, dict) else str(x) for x in c
            )
        if isinstance(c, dict):
            return str(c.get("nome") or c.get("denominazione") or c.get("sigla") or c)
        return str(c)
    return ""


def estrai_soggetti(item):
    for campo in ["soggettiCoinvolti","soggetti","categoriaPersonale","personale","lavoratoriCoinvolti","destinatari"]:
        c = item.get(campo)
        if not c:
            continue
        if isinstance(c, list):
            return ", ".join(
                str(x.get("nome") or x.get("descrizione") or x.get("categoria") or x)
                if isinstance(x, dict) else str(x) for x in c
            )
        if isinstance(c, dict):
            return str(c.get("nome") or c.get("descrizione") or c)
        return str(c)
    return ""


def normalizza_data(valore):
    if not valore:
        return ""
    valore = str(valore).strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", valore)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    m = re.match(r"(\d{2})[/\-](\d{2})[/\-](\d{4})", valore)
    if m:
        return f"{m.group(3)}{m.group(2)}{m.group(1)}"
    if re.match(r"^\d{13}$", valore):
        dt = datetime.utcfromtimestamp(int(valore) / 1000)
        return dt.strftime("%Y%m%d")
    return ""


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
            data_fine_ics = (datetime.strptime(data_fine_raw, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
        except Exception:
            data_fine_ics = data_inizio

        proclamato_da = (s.get("proclamato_da") or "").strip()
        soggetti      = (s.get("soggetti") or "").strip()
        descrizione   = "Comparto: Istruzione e Ricerca"
        if proclamato_da:
            descrizione += f"\\nPROCLAMATO DA: {proclamato_da}"
        if soggetti:
            descrizione += f"\\nSOGGETTI COINVOLTI: {soggetti}"
        descrizione += f"\\n\\nFonte: {GEPAS_URL}"

        lines += [
            "BEGIN:VEVENT",
            f"UID:{s.get('uid', str(uuid.uuid4()))}-gepas@scioperi",
            f"DTSTAMP:{ora}",
            f"DTSTART;VALUE=DATE:{data_inizio}",
            f"DTEND;VALUE=DATE:{data_fine_ics}",
            f"SUMMARY:{s['titolo']}",
            f"DESCRIPTION:{descrizione}",
            "CATEGORIES:Sciopero",
            "STATUS:CONFIRMED",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


def main():
    print("=" * 55)
    print("  GEPAS → ICS Generator [DEBUG]")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    tutti    = scarica_scioperi()
    scioperi = filtra_istruzione(tutti)
    print(f"[OK] Scioperi 'ISTRUZIONE RICERCA': {len(scioperi)}")

    os.makedirs("docs", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(genera_ics(scioperi))

    print(f"[FINE] {OUTPUT_FILE} generato con {len(scioperi)} eventi")
    print("=" * 55)


if __name__ == "__main__":
    main()
