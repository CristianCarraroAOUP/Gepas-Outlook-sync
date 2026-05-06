"""
GEPAS → ICS Generator
Usa il backend reale di GEPAS (asspa-api.perlapa.gov.it)
per leggere gli scioperi "Istruzione e Ricerca" e generare un .ics.
"""

import os
import re
import uuid
import json
import requests
from datetime import datetime, timedelta

OUTPUT_FILE     = "docs/scioperi.ics"
GEPAS_URL       = "https://crusc-gepas.perlapa.gov.it/home"
COMPARTO_TARGET = "istruzione e ricerca"
BASE_API        = "https://asspa-api.perlapa.gov.it/api/Public"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "it-IT,it;q=0.9",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://crusc-gepas.perlapa.gov.it/",
    "Origin": "https://crusc-gepas.perlapa.gov.it",
}


# ── 1. SCOPRI ENDPOINT API ─────────────────────
def scopri_endpoint():
    """Prova i possibili endpoint del backend asspa-api."""
    candidati = [
        f"{BASE_API}/Sciopero",
        f"{BASE_API}/Sciopero/Lista",
        f"{BASE_API}/Sciopero/Search",
        f"{BASE_API}/Scioperi",
        f"{BASE_API}/Adempimento/Sciopero",
        f"{BASE_API}/Adempimento/ListaScioperi",
        f"{BASE_API}/Adempimento/Scioperi",
        f"{BASE_API}/Proclamazione",
        f"{BASE_API}/Proclamazione/Lista",
        f"{BASE_API}/Adempimento/Lista",
        f"{BASE_API}/Adempimento",
        f"{BASE_API}/Cruscotto",
        f"{BASE_API}/Cruscotto/Scioperi",
        f"{BASE_API}/Cruscotto/Lista",
    ]

    # Prova prima a ottenere la lista delle "sigle" che sappiamo funziona
    # per capire la struttura dell'API
    print("[API] Analisi endpoint ListaSigle...")
    try:
        resp = requests.get(f"{BASE_API}/Adempimento/ListaSigle", headers=HEADERS, timeout=15)
        print(f"[API] ListaSigle: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"[API] Struttura ListaSigle: {json.dumps(data)[:300]}")
    except Exception as e:
        print(f"[API] Errore ListaSigle: {e}")

    # Prova tutti i candidati
    for url in candidati:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            print(f"[API] {resp.status_code} – {url}")
            if resp.status_code == 200:
                ct = resp.headers.get("content-type", "")
                if "json" in ct:
                    data = resp.json()
                    print(f"[API] ✅ JSON da {url}: {json.dumps(data)[:200]}")
                    records = estrai_lista(data)
                    if records:
                        return filtra_istruzione(records)
        except Exception as e:
            print(f"[API] Errore {url}: {e}")

    return []


# ── 2. PLAYWRIGHT CON URL NOTI ─────────────────
def prova_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[PW] Playwright non disponibile")
        return []

    api_data = []
    tutti_url = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--no-sandbox", "--disable-dev-shm-usage",
        ])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            locale="it-IT",
        )
        page = context.new_page()

        def handle_response(response):
            url = response.url
            tutti_url.append(f"{response.status} {url}")
            if response.status != 200:
                return
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            skip = ["googleapis", "gstatic", "analytics", "matomo", "cookie",
                    "i18n", "translation", "ListaSigle"]
            if any(s in url for s in skip):
                # Stampa comunque per debug
                try:
                    data = response.json()
                    print(f"[PW] (skip) {url[:80]}: {json.dumps(data)[:150]}")
                except Exception:
                    pass
                return
            try:
                data = response.json()
                print(f"[PW] JSON da {url}: {json.dumps(data)[:200]}")
                records = estrai_lista(data)
                if records:
                    api_data.extend(records)
                elif isinstance(data, dict) and any(
                    k in data for k in ["dataInizio", "data_inizio", "dataSciopero"]
                ):
                    api_data.append(data)
            except Exception:
                pass

        page.on("response", handle_response)

        print("[PW] Apertura GEPAS...")
        try:
            page.goto(GEPAS_URL, wait_until="networkidle", timeout=90000)
        except Exception as e:
            print(f"[PW] Timeout: {e}")

        page.wait_for_timeout(8000)

        # Tenta navigazione diretta alla sezione scioperi tramite URL hash
        for path in ["#/scioperi", "#/istruzione", "?comparto=istruzione", "/scioperi"]:
            try:
                page.goto(f"https://crusc-gepas.perlapa.gov.it{path}",
                          wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(4000)
            except Exception:
                pass

        # Scrolla
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(3000)

        # Stampa tutti gli URL visti
        print(f"[PW] Tutti gli URL intercettati ({len(tutti_url)}):")
        for u in tutti_url:
            if "asspa-api" in u or "gepas" in u.lower():
                print(f"  {u}")

        # Salva debug
        os.makedirs("docs", exist_ok=True)
        try:
            page.screenshot(path="docs/debug_screenshot.png", full_page=True)
            with open("docs/debug_page.html", "w", encoding="utf-8") as f:
                f.write(page.content())

            # Salva anche tutti gli URL per analisi
            with open("docs/debug_urls.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(tutti_url))
            print("[PW] Debug salvato")
        except Exception as e:
            print(f"[PW] Errore debug: {e}")

        browser.close()

    # Ora prova a chiamare direttamente tutti gli URL asspa-api trovati
    asspa_urls = [u.split(" ", 1)[1] for u in tutti_url
                  if "asspa-api" in u and u.startswith("200")]
    print(f"[PW] URL asspa-api con 200: {asspa_urls}")

    for url in asspa_urls:
        if "ListaSigle" in url:
            continue
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200 and "json" in resp.headers.get("content-type", ""):
                data = resp.json()
                print(f"[PW→API] Dati da {url}: {json.dumps(data)[:300]}")
                records = estrai_lista(data)
                if records:
                    api_data.extend(records)
        except Exception as e:
            print(f"[PW→API] Errore {url}: {e}")

    return filtra_istruzione(api_data) if api_data else []


# ── 3. UTILITIES ───────────────────────────────
def estrai_lista(data):
    if isinstance(data, list) and data:
        return data
    if isinstance(data, dict):
        for k in ["content", "data", "items", "results", "scioperi",
                  "proclamazioni", "list", "rows", "elementi"]:
            v = data.get(k)
            if isinstance(v, list) and v:
                return v
    return []


def filtra_istruzione(records):
    risultati = []
    for item in records:
        testo = json.dumps(item, ensure_ascii=False).lower()
        comparto = str(
            item.get("comparto") or item.get("compartoArea") or
            item.get("settore") or item.get("area") or
            item.get("compartoDescrizione") or ""
        ).lower()
        if COMPARTO_TARGET in comparto or COMPARTO_TARGET in testo:
            s = parse_item(item)
            if s:
                risultati.append(s)
    return risultati


def parse_item(item):
    try:
        data_inizio = normalizza_data(
            item.get("dataInizio") or item.get("data_inizio") or
            item.get("dataSciopero") or item.get("data") or
            item.get("startDate") or item.get("dataProclamazione") or ""
        )
        data_fine = normalizza_data(
            item.get("dataFine") or item.get("data_fine") or
            item.get("dataFineSciopero") or item.get("endDate") or data_inizio
        )
        if not data_inizio:
            return None

        sindacato = (
            item.get("organizzazione") or item.get("sindacato") or
            item.get("organizzazioni") or item.get("soggettoProclamante") or ""
        )
        if isinstance(sindacato, list):
            sindacato = ", ".join(
                str(x.get("nome", x) if isinstance(x, dict) else x) for x in sindacato
            )

        return {
            "uid":         str(item.get("id") or item.get("uid") or uuid.uuid4()),
            "titolo":      item.get("descrizione") or item.get("titolo") or "Sciopero Istruzione e Ricerca",
            "data_inizio": data_inizio,
            "data_fine":   data_fine,
            "sindacato":   str(sindacato),
            "comparto":    "Istruzione e Ricerca",
            "note":        str(item.get("note") or item.get("motivazione") or ""),
        }
    except Exception as e:
        print(f"[WARN] Errore parsing: {e}")
        return None


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


# ── 5. MAIN ────────────────────────────────────
def main():
    print("=" * 55)
    print("  GEPAS → ICS Generator")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    scioperi = []

    # Strategia 1: endpoint asspa-api diretti
    scioperi = scopri_endpoint()
    if scioperi:
        print(f"[OK] {len(scioperi)} scioperi via API dirette")

    # Strategia 2: Playwright
    if not scioperi:
        print("[INFO] Avvio Playwright...")
        scioperi = prova_playwright()
        print(f"[OK] {len(scioperi)} scioperi via Playwright")

    if not scioperi:
        print("[WARN] Nessuno sciopero trovato.")
        print("[INFO] Guarda docs/debug_urls.txt per vedere tutti gli URL intercettati")

    os.makedirs("docs", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(genera_ics(scioperi))

    print(f"[FINE] {OUTPUT_FILE} generato con {len(scioperi)} eventi")
    print("=" * 55)


if __name__ == "__main__":
    main()
