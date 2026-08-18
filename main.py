import os
import requests
import feedparser
import json
import time
import re
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
            print("📱 Το συγκεντρωτικό μήνυμα στάλθηκε επιτυχώς στο Telegram!")
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

def call_gemini_with_retry(prompt, retries=3):
    """
    Καλεί το gemini-3.6-flash με ασφαλή διαχείριση ορίων RPD/RPM.
    """
    model_name = 'gemini-3.6-flash'
    
    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.1)
            )
            return response.text
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                match = re.search(r'retryDelay.*?:.*?(\d+)', err_msg)
                wait_time = int(match.group(1)) + 2 if match else 35
                print(f"⚠️ Προσέγγιση Quota Limit (429). Αναμονή {wait_time}s (Προσπάθεια {attempt + 1}/{retries})...")
                time.sleep(wait_time)
            elif "503" in err_msg or "UNAVAILABLE" in err_msg:
                wait_time = (attempt + 1) * 8
                print(f"⚠️ Υψηλός φόρτος (503). Αναμονή {wait_time}s (Προσπάθεια {attempt + 1}/{retries})...")
                time.sleep(wait_time)
            else:
                print(f"❌ Σφάλμα API στο μοντέλο {model_name}: {e}")
                break
    return None

def analyze_all_matches_in_single_call(all_matches_data, total_matches):
    """
    Στέλνει ΟΛΟΥΣ τους αγώνες σε 1 μόνο API call στο Gemini για μέγιστη εξοικονόμηση ορίων RPD.
    """
    prompt = f"""
    Είσαι ένας αυστηρός αναλυτής αθλητικών στοιχημάτων. 
    Εξετάζεις ένα σύνολο {total_matches} αγώνων.

    ΔΕΔΟΜΕΝΑ ΑΓΩΝΩΝ:
    {json.dumps(all_matches_data, ensure_ascii=False, indent=2)}

    ΟΔΗΓΙΕΣ ΑΝΑΛΥΣΗΣ:
    1. Αξιολόγησε όλους τους αγώνες συνδυάζοντας την έδρα, τις ειδήσεις/κλίμα των ομάδων και τη δυναμική.
    2. Επιλογή: Ξεχώρισε ΑΥΣΤΗΡΑ τους 3 αγώνες που έχουν τις ΥΨΗΛΟΤΕΡΕΣ ΠΙΘΑΝΟΤΗΤΕΣ επιβεβαίωσης (High Confidence Bets).
    3. Μπορείς να προτείνεις οποιαδήποτε αγορά: 1X2, Διπλή Ευκαιρία, Over/Under 1.5/2.5, Goal/Goal ή Combo Bets (π.χ. 1 & Over 1.5).

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

    res_text = call_gemini_with_retry(prompt)
    return res_text if res_text else "⚠️ Αδυναμία παραγωγής τελικών προτάσεων λόγω εξάντλησης ημερήσιου ορίου API."

def main():
    print("🚀 Εκκίνηση Smart Betting Pipeline (1-Call Ultra-Optimized)...")
    
    matches, match_type = get_matches_smart()
    total_matches = len(matches)
    print(f"⚽ Κατηγορία: {match_type} | Σύνολο: {total_matches} αγώνες.")

    if not matches:
        print("ℹ️ Δεν βρέθηκαν διαθέσιμοι αγώνες.")
        return

    # Συλλογή δεδομένων για όλους τους διαθέσιμους αγώνες (έως 30)
    all_payloads = []
    for match in matches[:30]:
        home_team = match['homeTeam']['name']
        away_team = match['awayTeam']['name']
        league = match['competition']['name']
        match_date = match['utcDate'][:10]
        
        all_payloads.append({
            "match": f"{home_team} vs {away_team}",
            "league": league,
            "date": match_date,
            "home_news": get_news(home_team),
            "away_news": get_news(away_team)
        })
        time.sleep(0.3)

    print(f"\n🧠 Αποστολή και των {len(all_payloads)} αγώνων σε 1 μόνο API call στο Gemini...")
    final_picks = analyze_all_matches_in_single_call(all_payloads, total_matches)
    
    print("\n--- ΤΕΛΙΚΕΣ ΠΡΟΤΑΣΕΙΣ GEMINI ---")
    print(final_picks)
    
    # Αποστολή στο Telegram
    send_telegram_message(final_picks)

if __name__ == "__main__":
    main()
