"""
GEPAS → ICS Generator
Cerca gli scioperi "Istruzione e Ricerca" tramite ricerca web
e genera un file .ics pubblicato su GitHub Pages.
Outlook sottoscrive l'URL e si aggiorna automaticamente.
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

# ── API DIRETTE GEPAS ──────────────────────────
# Il backend del cruscotto espone questi endpoint REST
GEPAS_API_URLS = [
    "https://crusc-gepas.perlapa.gov.it/api/scioperi?comparto=ISTRUZIONE_E_RICERCA&size=100",
    "https://crusc-gepas.perlapa.gov.it/api/scioperi?size=200",
    "https://crusc-gepas.perlapa.gov.it/api/proclamazioni?size=200",
    "https://crusc-gepas.perlapa.gov.it/api/v1/scioperi",
    "https://crusc-gepas.perlapa.gov.it/rest/scioperi",
]

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "it-IT,it;q=0.9",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://crusc-gepas.perlapa.gov.it/home",
    "Origin": "https://crusc-gepas.perlapa.gov.it",
    "X-Requested-With": "XMLHttpRequest",
}


# ── 1. PROVA API DIRETTE ───────────────────────
def prova_api_dirette():
    print("[API] Tentativo endpoint GEPAS diretti...")
    for url in GEPAS_API_URLS:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            print(f"[API] {resp.status_code} – {url}")
            if resp.status_code == 200:
                ct = resp.headers.get("content-type", "")
                if "json" in ct:
                    data = resp.json()
                    records = estrai_lista(data)
                    if records:
                        print(f"[API] ✅ {len(records)} record da {url}")
                        return filtra_istruzione(records)
        except Exception as e:
            print(f"[API] Errore: {e}")
    return []


def estrai_lista(data):
    if isinstance(data, list) and data:
        return data
    if isinstance(data, dict):
        for k in ["content", "data", "items", "results", "scioperi", "proclamazioni", "list"]:
            v = data.get(k)
            if isinstance(v, list) and v:
                return v
    return []


# ── 2. PLAYWRIGHT CON INTERCETTAZIONE AVANZATA ─
def prova_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[PW] Playwright non disponibile")
        return []

    api_data = []
    api_urls_visti = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="it-IT",
            viewport={"width": 1280, "height": 800},
        )

        # Intercetta tutte le risposte di rete
        def handle_response(response):
            url = response.url
            if response.status != 200:
                return
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            skip = ["googleapis", "gstatic", "analytics", "favicon", "matomo",
                    "cookie", "config", "version", "i18n", "translation"]
            if any(s in url.lower() for s in skip):
                return
            try:
                data = response.json()
                records = estrai_lista(data)
                if records and len(records) >= 1:
                    print(f"[PW] JSON ({len(records)} record) da: {url}")
                    api_data.extend(records)
                    api_urls_visti.append(url)
                elif isinstance(data, dict) and data:
                    # Potrebbe essere un singolo sciopero
                    if "dataInizio" in data or "data_inizio" in data or "dataSciopero" in data:
                        api_data.append(data)
            except Exception:
                pass

        page = context.new_page()
        page.on("response", handle_response)

        print("[PW] Apertura pagina GEPAS...")
        try:
            page.goto(GEPAS_URL, wait_until="networkidle", timeout=90000)
        except Exception as e:
            print(f"[PW] Timeout iniziale: {e}")

        page.wait_for_timeout(8000)

        # Scrolla la pagina
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(3000)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(2000)

        # Cerca e clicca eventuale filtro "Istruzione"
        selectors_filtro = [
            "text=Istruzione",
            "text=ISTRUZIONE",
            "[value*='istruzione' i]",
            "option[value*='istruzione' i]",
            "mat-option:has-text('Istruzione')",
            ".filter-comparto",
        ]
        for sel in selectors_filtro:
            try:
                el = page.query_selector(sel)
                if el:
                    el.click()
                    page.wait_for_timeout(4000)
                    print(f"[PW] Cliccato filtro: {sel}")
                    break
            except Exception:
                pass

        # Salva debug
        os.makedirs("docs", exist_ok=True)
        try:
            page.screenshot(path="docs/debug_screenshot.png", full_page=True)
            with open("docs/debug_page.html", "w", encoding="utf-8") as f:
                f.write(page.content())
            print("[PW] Debug salvato in docs/")
        except Exception as e:
            print(f"[PW] Errore salvataggio debug: {e}")

        # Log URL intercettati
        if api_urls_visti:
            print(f"[PW] URL API intercettati: {api_urls_visti}")
        else:
            print("[PW] Nessun URL API intercettato")
            # Prova a chiamare direttamente gli URL che il browser avrebbe chiamato
            # basandosi sugli script JS della pagina
            try:
                scripts = page.query_selector_all("script[src]")
                for s in scripts[:5]:
                    src = s.get_attribute("src")
                    if src:
                        print(f"[PW] Script trovato: {src}")
            except Exception:
                pass

        browser.close()

    return filtra_istruzione(api_data) if api_data else []


# ── 3. FILTRAGGIO E PARSING ────────────────────
def filtra_istruzione(records):
    risultati = []
    for item in records:
        comparto = str(
            item.get("comparto") or item.get("compartoArea") or
            item.get("settore") or item.get("area") or
            item.get("compartoDescrizione") or item.get("tipoComparto") or ""
        ).lower()
        # Accetta anche se comparto è vuoto ma c'è "istruzione" altrove nel record
        testo_record = json.dumps(item, ensure_ascii=False).lower()
        if COMPARTO_TARGET in comparto or (COMPARTO_TARGET in testo_record and comparto == ""):
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
            sindacato = ", ".join(str(x.get("nome", x) if isinstance(x, dict) else x) for x in sindacato)

        return {
            "uid":         str(item.get("id") or item.get("uid") or uuid.uuid4()),
            "titolo":      item.get("descrizione") or item.get("titolo") or item.get("oggetto") or "Sciopero Istruzione e Ricerca",
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
            data_fine_ics = (datetime.strptime(data_fine_raw, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
        except Exception:
            data_fine_ics = data_inizio

        sindacato = (s.get("sindacato") or "").strip()
        note      = (s.get("note") or "").strip()

        soggetto = "SCIOPERO - Istruzione e Ricerca"
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

    # Strategia 1: API dirette
    scioperi = prova_api_dirette()
    if scioperi:
        print(f"[OK] {len(scioperi)} scioperi via API dirette")

    # Strategia 2: Playwright
    if not scioperi:
        print("[INFO] Avvio Playwright come fallback...")
        scioperi = prova_playwright()
        print(f"[OK] {len(scioperi)} scioperi via Playwright")

    if not scioperi:
        print("[WARN] Nessuno sciopero trovato.")
        print("[INFO] Guarda docs/debug_screenshot.png per diagnosticare il problema")

    os.makedirs("docs", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(genera_ics(scioperi))

    print(f"[FINE] {OUTPUT_FILE} generato con {len(scioperi)} eventi")
    print("=" * 55)


if __name__ == "__main__":
    main()
