"""
GEPAS → ICS Generator
Chiama direttamente gepas-api.perlapa.gov.it,
filtra gli scioperi con comparto "ISTRUZIONE RICERCA"
e genera un file .ics per Outlook.
"""

import os
import re
import uuid
import json
import requests
from datetime import datetime, timedelta

OUTPUT_FILE = "docs/scioperi.ics"
GEPAS_URL   = "https://crusc-gepas.perlapa.gov.it/home"
FILTRO      = "istruzione ricerca"   # ricerca esatta (case-insensitive)

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
            print(f"[API] Status: {resp.status_code}")
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[API] Errore: {e}")
            break

        # Debug: struttura primo record
        if page == 1:
            campione = data if isinstance(data, list) else next(
                (data[k] for k in ["content","data","items","results","scioperi","list","rows"]
                 if isinstance(data.get(k), list)), []
            )
            if campione:
                print(f"[DEBUG] Primo record:\n{json.dumps(campione[0], ensure_ascii=False, indent=2)[:1000]}")

        records = []
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            for k in ["content","data","items","results","scioperi","list","rows"]:
                if isinstance(data.get(k), list):
                    records = data[k]
                    break

        if not records:
            print(f"[API] Fine paginazione a pagina {page}.")
            break

        print(f"[API] Pagina {page}: {len(records)} record")
        tutti.extend(records)

        if len(records) < 100:
            break
        page += 1

    print(f"[API] Totale record scaricati: {len(tutti)}")
    return tutti


# ── 2. FILTRA "ISTRUZIONE RICERCA" ────────────
def filtra_istruzione(records):
    """
    Cerca la frase esatta 'istruzione ricerca' (case-insensitive)
    in tutti i campi stringa del record JSON.
    Stampa anche i comparti unici trovati per debug.
    """
    risultati    = []
    comparti_log = set()

    for item in records:
        # Raccoglie i valori dei campi comparto per debug
        for campo in ["comparto","compartoArea","settore","area",
                      "compartoDescrizione","tipoComparto","comparti","compartoPA"]:
            v = item.get(campo)
            if v:
                comparti_log.add(str(v))

        # Cerca la frase esatta nel JSON completo
        testo = json.dumps(item, ensure_ascii=False).lower()
        if FILTRO in testo:
            s = parse_item(item)
            if s:
                risultati.append(s)
                print(f"[FILTRO] ✅ {s['data_inizio']} – {s['titolo'][:60]}")

    print(f"[DEBUG] Valori campo comparto trovati: {comparti_log}")
    return risultati


# ── 3. PARSING RECORD ─────────────────────────
def parse_item(item):
    try:
        # Date
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

        # Titolo (oggetto calendario)
        titolo = (
            item.get("denominazioneSciopero") or
            item.get("descrizione") or
            item.get("titolo") or
            "Sciopero – Istruzione e Ricerca"
        )

        # PROCLAMATO DA
        proclamato_da = estrai_proclamato_da(item)

        # SOGGETTI COINVOLTI
        soggetti = estrai_soggetti(item)

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
    """Estrae chi ha proclamato lo sciopero."""
    candidati = [
        item.get("organizzazione"),
        item.get("sindacato"),
        item.get("soggettoProclamante"),
        item.get("proclamatoDa"),
        item.get("sigle"),
        item.get("organizzazioni"),
    ]
    for c in candidati:
        if not c:
            continue
        if isinstance(c, list):
            return ", ".join(
                str(x.get("sigla") or x.get("nome") or x.get("denominazione") or x)
                if isinstance(x, dict) else str(x)
                for x in c
            )
        if isinstance(c, dict):
            return str(c.get("nome") or c.get("denominazione") or c.get("sigla") or c)
        return str(c)
    return ""


def estrai_soggetti(item):
    """Estrae i soggetti coinvolti nello sciopero."""
    candidati = [
        item.get("soggettiCoinvolti"),
        item.get("soggetti"),
        item.get("categoriaPersonale"),
        item.get("personale"),
        item.get("lavoratoriCoinvolti"),
        item.get("destinatari"),
    ]
    for c in candidati:
        if not c:
            continue
        if isinstance(c, list):
            return ", ".join(
                str(x.get("nome") or x.get("descrizione") or x.get("categoria") or x)
                if isinstance(x, dict) else str(x)
                for x in c
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


# ── 4. GENERA ICS ──────────────────────────────
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

        proclamato_da = (s.get("proclamato_da") or "").strip()
        soggetti      = (s.get("soggetti") or "").strip()

        # Oggetto = titolo dello sciopero
        soggetto = s["titolo"]

        # Descrizione con sezioni
        descrizione = f"Comparto: Istruzione e Ricerca"
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
            f"SUMMARY:{soggetto}",
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
