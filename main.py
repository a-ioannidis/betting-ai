import os
import requests
import feedparser
import json
import time
from datetime import datetime, timedelta
from urllib.parse import quote
from google import genai
from google.genai import types

# 1. Αρχικοποίηση Clients & Keys
client = genai.Client()
FOOTBALL_DATA_API_KEY = os.getenv("FOOTBALL_DATA_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HEADERS = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}

def send_telegram_message(message):
    """Στέλνει μήνυμα στο Telegram Bot."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials λείπουν, παράκαμψη αποστολής.")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("📱 Το τελικό συγκεντρωτικό μήνυμα στάλθηκε επιτυχώς στο Telegram!")
        else:
            print(f"⚠️ Σφάλμα Telegram API: {response.text}")
    except Exception as e:
        print(f"❌ Αποτυχία αποστολής στο Telegram: {e}")

def fetch_matches_for_dates(date_from, date_to):
    """Εκτελεί το αίτημα στο API του football-data.org."""
    url = f"https://api.football-data.org/v4/matches?dateFrom={date_from}&dateTo={date_to}"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            return response.json().get('matches', [])
        else:
            print(f"⚠️ Σφάλμα API {response.status_code}: {response.text}")
            return []
    except Exception as e:
        print(f"❌ Αποτυχία σύνδεσης: {e}")
        return []

def get_matches_smart():
    """Ψάχνει αγώνες για σήμερα ή για το ερχόμενο Σαββατοκύριακο."""
    now = datetime.now()
    today_str = now.strftime('%Y-%m-%d')
    
    print(f"🔍 Έλεγχος για σημερινούς αγώνες ({today_str})...")
    matches = fetch_matches_for_dates(today_str, today_str)
    
    if matches:
        return matches, "Σημερινοί Αγώνες"

    days_until_saturday = (5 - now.weekday()) % 7
    if days_until_saturday == 0 and now.weekday() != 5:
        days_until_saturday = 7
        
    saturday = now + timedelta(days=days_until_saturday)
    sunday = saturday + timedelta(days=1)
    
    sat_str = saturday.strftime('%Y-%m-%d')
    sun_str = sunday.strftime('%Y-%m-%d')
    
    print(f"📅 Αναζήτηση αγώνων Σαββατοκύριακου ({sat_str} έως {sun_str})...")
    weekend_matches = fetch_matches_for_dates(sat_str, sun_str)
    
    return weekend_matches, f"Αγώνες Σαββατοκύριακου ({sat_str} - {sun_str})"

def get_news(team_name):
    """Τραβάει ειδήσεις μέσω Google News RSS."""
    encoded_query = quote(f"{team_name} football")
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(rss_url)
    return [entry.title for entry in feed.entries[:2]]

def analyze_batch(batch_data):
    """Αναλύει ένα γκρουπ αγώνων (batch) και επιστρέφει τους επικρατέστερους με διευρυμένες στοιχηματικές αγορές."""
    prompt = f"""
    Είσαι επαγγελματίας αθλητικός αναλυτής. Εξέτασε το παρακάτω γκρουπ αγώνων.
    
    ΔΕΔΟΜΕΝΑ:
    {json.dumps(batch_data, ensure_ascii=False, indent=2)}

    Ξεχώρισε τους 2 αγώνες με τις υψηλότερες πιθανότητες επιβεβαίωσης.
    
    ΜΠΟΡΕΙΣ ΝΑ ΠΡΟΤΕΙΝΕΙΣ ΟΠΟΙΑΔΗΠΟΤΕ ΑΠΟ ΤΙΣ ΕΞΗΣ ΑΓΟΡΕΣ (Choose the best value option):
    - Τελικό Αποτέλεσμα / Διπλή Ευκαιρία (1, X, 2, 1X, 2X)
    - Γκολ (Over 1.5, Over 2.5, Goal/Goal, No Goal)
    - Combo Bets (π.χ. 1 & Over 1.5, 2 & Over 2.5, 1X & Over 1.5, G/G & Over 2.5)

    Επίστρεψε JSON μορφή ως ακολούθως:
    [
      {{
        "match": "Ομάδα A vs Ομάδα B",
        "league": "Διοργάνωση",
        "pick": "Πρόταση (π.χ. 1 & Over 1.5, Over 2.5, G/G)",
        "confidence": 78,
        "reason": "Σύντομη αιτιολογία"
      }}
    ]
    """

    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json"
        )
    )
    try:
        return json.loads(response.text)
    except:
        return []

def select_top_picks(candidates, total_matches):
    """Επιλέγει τις 3 κορυφαίες προτάσεις από όλους τους επικρατέστερους αγώνες."""
    prompt = f"""
    Είσαι ένας αυστηρός αναλυτής στοιχημάτων. Εξετάστηκαν συνολικά {total_matches} αγώνες.
    Από τους παρακάτω επικρατέστερους αγώνες, διάλεξε ΑΥΣΤΗΡΑ τις 3 ΚΑΛΥΤΕΡΕΣ προτάσεις (με την υψηλότερη αξιοπιστία):

    {json.dumps(candidates, ensure_ascii=False, indent=2)}

    ΜΟΡΦΗ ΑΠΑΝΤΗΣΗΣ (Strict Text Format for Telegram):
    🎯 TOP PROPICKS ({total_matches} Αγώνες Εξετάστηκαν)
    -----------------------------------
    1. [Ομάδα Α] vs [Ομάδα Β] ([Διοργάνωση])
       💡 Πρόταση: [Σημείο / Combo / Over/Under / G/G]
       📊 Πιθανότητα: [X%]
       📝 Αιτιολογία: [Σύντομη πρόταση]

    2. ...
    3. ...
    """

    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.1)
    )
    return response.text

def main():
    print("🚀 Εκκίνηση Smart Betting Pipeline (Full Coverage & Combo Bets)...")
    
    matches, match_type = get_matches_smart()
    total_matches = len(matches)
    print(f"⚽ Κατηγορία: {match_type} | Σύνολο: {total_matches} αγώνες.")

    if not matches:
        print("ℹ️ Δεν βρέθηκαν διαθέσιμοι αγώνες.")
        return

    BATCH_SIZE = 10
    candidates = []

    # Επεξεργασία όλων των αγώνων σε batches των 10
    for i in range(0, total_matches, BATCH_SIZE):
        batch_matches = matches[i:i + BATCH_SIZE]
        print(f"\n🔄 Επεξεργασία Batch {i//BATCH_SIZE + 1} ({len(batch_matches)} αγώνες)...")
        
        batch_payload = []
        for match in batch_matches:
            home_team = match['homeTeam']['name']
            away_team = match['awayTeam']['name']
            league = match['competition']['name']
            match_date = match['utcDate'][:10]
            
            batch_payload.append({
                "match": f"{home_team} vs {away_team}",
                "league": league,
                "date": match_date,
                "home_news": get_news(home_team),
                "away_news": get_news(away_team)
            })
            time.sleep(1)

        print(f"🧠 Αποστολή Batch {i//BATCH_SIZE + 1} στο Gemini...")
        batch_candidates = analyze_batch(batch_payload)
        candidates.extend(batch_candidates)
        time.sleep(2)

    print(f"\n📊 Συλλέχθηκαν {len(candidates)} υποψήφιοι αγώνες από όλα τα batches.")
    print("🏆 Τελική αξιολόγηση για τις 3 κορυφαίες προτάσεις...")
    
    final_picks = select_top_picks(candidates, total_matches)
    
    print("\n--- ΤΕΛΙΚΕΣ ΠΡΟΤΑΣΕΙΣ GEMINI ---")
    print(final_picks)
    
    # Αποστολή στο Telegram
    send_telegram_message(final_picks)

if __name__ == "__main__":
    main()
