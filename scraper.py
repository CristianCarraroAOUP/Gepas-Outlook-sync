"""
GEPAS → Outlook Calendar Sync
Legge gli scioperi "Istruzione e Ricerca" dal Cruscotto GEPAS
e li aggiunge automaticamente al calendario Outlook via Microsoft Graph API.
"""

import os
import json
import requests
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright

# ──────────────────────────────────────────────
# CONFIGURAZIONE (da variabili d'ambiente GitHub)
# ──────────────────────────────────────────────
TENANT_ID     = os.environ["MS_TENANT_ID"]
CLIENT_ID     = os.environ["MS_CLIENT_ID"]
CLIENT_SECRET = os.environ["MS_CLIENT_SECRET"]
USER_EMAIL    = os.environ["MS_USER_EMAIL"]   # es. tuonome@outlook.com

GEPAS_URL     = "https://crusc-gepas.perlapa.gov.it/home"
COMPARTO_TARGET = "istruzione e ricerca"


# ──────────────────────────────────────────────
# 1. SCRAPING DEL SITO GEPAS
# ──────────────────────────────────────────────
def scrape_scioperi():
    """Apre il sito GEPAS con Playwright e restituisce la lista degli scioperi."""
    scioperi = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        print(f"[GEPAS] Apertura pagina: {GEPAS_URL}")
        page.goto(GEPAS_URL, wait_until="networkidle", timeout=60000)

        # Attendi che la tabella/lista sia caricata
        page.wait_for_timeout(4000)

        # Intercetta le chiamate API interne del sito
        # Il sito usa Angular/React e carica i dati da endpoint JSON interni
        api_data = []

        def handle_response(response):
            if "scioperi" in response.url.lower() or "gepas" in response.url.lower():
                try:
                    data = response.json()
                    if isinstance(data, list) and len(data) > 0:
                        api_data.extend(data)
                except Exception:
                    pass

        page.on("response", handle_response)

        # Ricarica per intercettare le chiamate API
        page.reload(wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)

        if api_data:
            print(f"[GEPAS] Dati API intercettati: {len(api_data)} record")
            for item in api_data:
                comparto = str(item.get("comparto", "")).lower()
                if COMPARTO_TARGET in comparto:
                    scioperi.append(parse_sciopero_api(item))
        else:
            # Fallback: parsing DOM della pagina
            print("[GEPAS] Nessuna API intercettata, parsing DOM...")
            scioperi = parse_dom(page)

        browser.close()

    print(f"[GEPAS] Scioperi 'Istruzione e Ricerca' trovati: {len(scioperi)}")
    return [s for s in scioperi if s is not None]


def parse_sciopero_api(item):
    """Converte un record JSON dell'API GEPAS in dizionario normalizzato."""
    try:
        return {
            "id":          item.get("id") or item.get("uid") or "",
            "titolo":      item.get("descrizione") or item.get("titolo") or "Sciopero Istruzione e Ricerca",
            "data_inizio": item.get("dataInizio") or item.get("data_inizio") or "",
            "data_fine":   item.get("dataFine")   or item.get("data_fine")   or "",
            "sindacato":   item.get("organizzazione") or item.get("sindacato") or "",
            "comparto":    item.get("comparto") or "",
            "note":        item.get("note") or "",
        }
    except Exception as e:
        print(f"[WARN] Errore parsing item: {e}")
        return None


def parse_dom(page):
    """Parsing fallback: estrae dati direttamente dal DOM della pagina."""
    scioperi = []
    try:
        # Cerca righe della tabella o card contenenti "istruzione"
        rows = page.query_selector_all("tr, .card, .sciopero-item, [class*='row']")
        for row in rows:
            text = row.inner_text().lower()
            if COMPARTO_TARGET in text:
                scioperi.append({
                    "id":          "",
                    "titolo":      "Sciopero – Istruzione e Ricerca",
                    "data_inizio": estrai_data_da_testo(row.inner_text()),
                    "data_fine":   estrai_data_da_testo(row.inner_text()),
                    "sindacato":   "",
                    "comparto":    "Istruzione e Ricerca",
                    "note":        row.inner_text().strip()[:300],
                })
    except Exception as e:
        print(f"[WARN] Errore parsing DOM: {e}")
    return scioperi


def estrai_data_da_testo(testo):
    """Tenta di estrarre una data in formato DD/MM/YYYY o YYYY-MM-DD dal testo."""
    import re
    match = re.search(r"(\d{2})[/\-](\d{2})[/\-](\d{4})", testo)
    if match:
        d, m, y = match.groups()
        return f"{y}-{m}-{d}"
    match = re.search(r"(\d{4})[/\-](\d{2})[/\-](\d{2})", testo)
    if match:
        return match.group(0)
    return ""


# ──────────────────────────────────────────────
# 2. AUTENTICAZIONE MICROSOFT GRAPH
# ──────────────────────────────────────────────
def get_access_token():
    """Ottiene un access token OAuth2 da Microsoft per Graph API."""
    url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = {
        "grant_type":    "client_credentials",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope":         "https://graph.microsoft.com/.default",
    }
    resp = requests.post(url, data=data)
    resp.raise_for_status()
    token = resp.json()["access_token"]
    print("[GRAPH] Access token ottenuto.")
    return token


# ──────────────────────────────────────────────
# 3. LETTURA EVENTI GIÀ PRESENTI SU OUTLOOK
# ──────────────────────────────────────────────
def get_eventi_outlook(token):
    """Recupera gli eventi del calendario Outlook dei prossimi 12 mesi."""
    oggi = datetime.utcnow().strftime("%Y-%m-%dT00:00:00Z")
    tra_un_anno = (datetime.utcnow() + timedelta(days=365)).strftime("%Y-%m-%dT00:00:00Z")

    url = (
        f"https://graph.microsoft.com/v1.0/users/{USER_EMAIL}/calendarView"
        f"?startDateTime={oggi}&endDateTime={tra_un_anno}"
        f"&$select=subject,start,end,id"
        f"&$top=200"
    )
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    eventi = resp.json().get("value", [])
    print(f"[GRAPH] Eventi già presenti su Outlook: {len(eventi)}")
    return eventi


def evento_gia_presente(sciopero, eventi_outlook):
    """Controlla se uno sciopero è già presente nel calendario (evita duplicati)."""
    data_s = sciopero.get("data_inizio", "")[:10]
    titolo_s = sciopero.get("titolo", "").lower()

    for ev in eventi_outlook:
        data_ev = ev.get("start", {}).get("dateTime", ev.get("start", {}).get("date", ""))[:10]
        titolo_ev = ev.get("subject", "").lower()

        if data_s == data_ev and ("istruzione" in titolo_ev or "sciopero" in titolo_ev):
            return True
    return False


# ──────────────────────────────────────────────
# 4. CREAZIONE EVENTI SU OUTLOOK
# ──────────────────────────────────────────────
def crea_evento_outlook(token, sciopero):
    """Crea un nuovo evento nel calendario Outlook per uno sciopero."""
    data_inizio = sciopero.get("data_inizio", "")[:10]
    data_fine   = sciopero.get("data_fine",   "")[:10]

    if not data_inizio:
        print(f"[SKIP] Data mancante per: {sciopero.get('titolo')}")
        return False

    # Se data_fine non c'è o è uguale a data_inizio, evento di 1 giorno
    if not data_fine or data_fine == data_inizio:
        dt_fine = (datetime.strptime(data_inizio, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        dt_fine = data_fine

    sindacato = sciopero.get("sindacato", "")
    note      = sciopero.get("note", "")
    body_text = f"Comparto: Istruzione e Ricerca\n"
    if sindacato:
        body_text += f"Sindacato: {sindacato}\n"
    if note:
        body_text += f"\nNote: {note}\n"
    body_text += f"\nFonte: {GEPAS_URL}"

    evento = {
        "subject": f"🔴 SCIOPERO – Istruzione e Ricerca" + (f" ({sindacato})" if sindacato else ""),
        "body": {
            "contentType": "text",
            "content": body_text,
        },
        # Per eventi tutto il giorno, Graph API vuole "date" (senza orario)
        # e NON vuole il campo "timeZone"
        "start": {
            "date": data_inizio,
        },
        "end": {
            "date": dt_fine,
        },
        "isAllDay": True,
        "showAs": "free",
        "categories": ["Sciopero"],
        "importance": "high",
    }

    url = f"https://graph.microsoft.com/v1.0/users/{USER_EMAIL}/events"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }
    resp = requests.post(url, headers=headers, json=evento)

    if resp.status_code == 201:
        print(f"[GRAPH] ✅ Evento creato: {evento['subject']} – {data_inizio}")
        return True
    else:
        print(f"[GRAPH] ❌ Errore creazione evento: {resp.status_code} – {resp.text}")
        return False


# ──────────────────────────────────────────────
# 5. MAIN
# ──────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  GEPAS → Outlook Calendar Sync")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    # Step 1: Scarica scioperi da GEPAS
    scioperi = scrape_scioperi()
    if not scioperi:
        print("[INFO] Nessuno sciopero trovato. Fine.")
        return

    # Step 2: Autenticazione Microsoft
    token = get_access_token()

    # Step 3: Carica eventi già presenti su Outlook
    eventi_outlook = get_eventi_outlook(token)

    # Step 4: Aggiunge solo i nuovi scioperi
    aggiunti = 0
    saltati  = 0
    for sciopero in scioperi:
        if evento_gia_presente(sciopero, eventi_outlook):
            print(f"[SKIP] Già presente: {sciopero.get('titolo')} – {sciopero.get('data_inizio', '')[:10]}")
            saltati += 1
        else:
            if crea_evento_outlook(token, sciopero):
                aggiunti += 1

    print("-" * 55)
    print(f"[FINE] Aggiunti: {aggiunti} | Già presenti (saltati): {saltati}")
    print("=" * 55)


if __name__ == "__main__":
    main()
