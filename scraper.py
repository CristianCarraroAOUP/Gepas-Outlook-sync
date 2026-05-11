import os
import uuid
import requests
from datetime import datetime, timedelta, timezone

OUTPUT_FILE = "docs/scioperi.ics"
GEPAS_URL   = "https://crusc-gepas.perlapa.gov.it/home"
FILTRO      = "istruzione ricerca"
BASE_API    = "https://gepas-api.perlapa.gov.it/api/Public/Scioperi/Pubblicati"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "it-IT,it;q=0.9",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://crusc-gepas.perlapa.gov.it/",
    "Origin": "https://crusc-gepas.perlapa.gov.it",
}


def scarica_pagine(prossimi30=False):
    tutti = []
    page  = 1
    while True:
        params = {
            "pageNumber": page,
            "pageSize": 100,
            "ScioperoDeiProssimi30Giorni": "true" if prossimi30 else "false",
            "OrderBy": "DataInizioSciopero",
            "Ascending": "true",
        }
        try:
            resp = requests.get(BASE_API, headers=HEADERS, params=params, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print("[API] Errore (prossimi30=" + str(prossimi30) + "): " + str(e))
            break

        records = data if isinstance(data, list) else next(
            (data[k] for k in ["content", "data", "items", "results", "scioperi", "list", "rows"]
             if isinstance(data.get(k), list)), []
        )

        if not records:
            break

        print("[API] prossimi30=" + str(prossimi30) + " pagina " + str(page) + ": " + str(len(records)) + " record")
        tutti.extend(records)

        if len(records) < 100:
            break
        page += 1

    return tutti


def scarica_scioperi():
    # Chiamata 1: tutti gli scioperi (non filtrati per prossimi 30 gg)
    tutti = scarica_pagine(prossimi30=False)
    ids_visti = {str(r.get("id", "")) for r in tutti}

    # Chiamata 2: scioperi prossimi 30 giorni (potrebbero includere futuri non nella prima)
    prossimi = scarica_pagine(prossimi30=True)
    for r in prossimi:
        if str(r.get("id", "")) not in ids_visti:
            tutti.append(r)
            ids_visti.add(str(r.get("id", "")))

    print("[API] Totale record unici: " + str(len(tutti)))
    return tutti


def filtra_e_parse(records):
    eventi = []

    for item in records:
        titolo = (
            item.get("denominazioneSciopero") or
            item.get("descrizione") or
            "Sciopero - Istruzione e Ricerca"
        ).replace("\n", " ").replace("\r", " ").strip()

        stato_raw = ""
        stato_obj = item.get("statoSciopero")
        if isinstance(stato_obj, dict):
            stato_raw = str(stato_obj.get("descrizione") or "").strip()
        elif isinstance(stato_obj, str):
            stato_raw = stato_obj.strip()
        stato = stato_raw.upper() if stato_raw else ""

        item_id = str(item.get("id") or uuid.uuid4())

        for idx, ds in enumerate(item.get("dateSciopero", [])):
            comparti_istruzione = [
                c for c in ds.get("compartiCoinvolti", [])
                if FILTRO in str(c.get("descrizioneComparto", "")).lower()
            ]
            if not comparti_istruzione:
                continue

            data_inizio = timestamp_ms_to_date(ds.get("data", ""))
            if not data_inizio:
                continue

            proclamato = ds.get("sigleSindacaliCheIndicono", [])
            proclamato_str = ", ".join(str(x).strip() for x in proclamato) if proclamato else ""

            aderenti = ds.get("sigleSindacaliChePartecipano", [])
            aderenti_str = ", ".join(str(x).strip() for x in aderenti) if aderenti else ""

            comparti_str = ", ".join(
                str(c.get("descrizioneComparto", "")).strip()
                for c in comparti_istruzione
            )

            soggetti_str = str(ds.get("soggettiCoinvolti", "")).strip()
            if not soggetti_str:
                qualifiche = []
                for c in comparti_istruzione:
                    for q in c.get("qualifiche", []):
                        desc = str(q.get("descrizione", "")).strip()
                        if desc and desc not in qualifiche:
                            qualifiche.append(desc)
                soggetti_str = ", ".join(qualifiche)

            oggetto = ("[" + stato + "] " + titolo) if stato else titolo

            print("[OK] " + data_inizio + " - " + oggetto[:70])

            eventi.append({
                "uid":         item_id + "-" + str(idx) + "-gepas@scioperi",
                "oggetto":     oggetto,
                "data_inizio": data_inizio,
                "proclamato":  proclamato_str,
                "comparti":    comparti_str,
                "soggetti":    soggetti_str,
                "aderenti":    aderenti_str,
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
        "X-WR-CALDESC:Aggiornato automaticamente da " + GEPAS_URL,
        "REFRESH-INTERVAL;VALUE=DURATION:P1D",
        "X-PUBLISHED-TTL:P1D",
    ]

    for e in eventi:
        data_inizio = e["data_inizio"]
        try:
            data_fine = (datetime.strptime(data_inizio, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
        except Exception:
            data_fine = data_inizio

        desc_parts = []
        if e.get("proclamato"):
            desc_parts.append("PROCLAMATO DA: " + e["proclamato"])
        if e.get("comparti"):
            desc_parts.append("COMPARTI PA: " + e["comparti"])
        if e.get("soggetti"):
            desc_parts.append("SOGGETTI COINVOLTI: " + e["soggetti"])
        if e.get("aderenti"):
            desc_parts.append("SINDACATI ADERENTI: " + e["aderenti"])
        desc_parts.append("Fonte: " + GEPAS_URL)
        descrizione = "\\n".join(desc_parts)

        lines += [
            "BEGIN:VEVENT",
            "UID:" + e["uid"],
            "DTSTAMP:" + ora,
            "DTSTART;VALUE=DATE:" + data_inizio,
            "DTEND;VALUE=DATE:" + data_fine,
            "SUMMARY:" + e["oggetto"],
            "DESCRIPTION:" + descrizione,
            "CATEGORIES:Sciopero",
            "STATUS:CONFIRMED",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


def main():
    print("=" * 55)
    print("  GEPAS -> ICS Generator")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 55)

    tutti  = scarica_scioperi()
    eventi = filtra_e_parse(tutti)
    print("[OK] Totale eventi ISTRUZIONE RICERCA: " + str(len(eventi)))

    os.makedirs("docs", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(genera_ics(eventi))

    print("[FINE] " + OUTPUT_FILE + " generato con " + str(len(eventi)) + " eventi")
    print("=" * 55)


if __name__ == "__main__":
    main()
