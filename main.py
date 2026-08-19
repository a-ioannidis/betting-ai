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

# Τα διαθέσιμα πρωταθλήματα του Free Tier
COMPETITIONS = ["PL", "ELC", "PD", "BL1", "SA", "FL1", "DED", "PPL", "BSA"]

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
            print("📱 Το μήνυμα στάλθηκε επιτυχώς στο Telegram!")
        else:
            print(f"⚠️ Σφάλμα Telegram API: {response.text}")
    except Exception as e:
        print(f"❌ Αποτυχία αποστολής στο Telegram: {e}")

def fetch_matches_for_dates(date_from, date_to):
    """Εκτελεί το αίτημα στο API του football-data.org για αγώνες."""
    url = f"https://api.football-data.org/v4/matches?dateFrom={date_from}&dateTo={date_to}"
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            return response.json().get('matches', [])
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
    """Καλεί το gemini-3.6-flash με ασφαλή διαχείριση ορίων RPD/RPM."""
    model_name = 'gemini-3.6-flash'
    
    for attempt in range(retries):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.2)
            )
            return response.text
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                match = re.search(r'retryDelay.*?:.*?(\d+)', err_msg)
                wait_time = int(match.group(1)) + 2 if match else 35
                print(f"⚠️ Προσέγγιση Quota Limit (429). Αναμονή {wait_time}s...")
                time.sleep(wait_time)
            elif "503" in err_msg or "UNAVAILABLE" in err_msg:
                wait_time = (attempt + 1) * 8
                print(f"⚠️ Υψηλός φόρτος (503). Αναμονή {wait_time}s...")
                time.sleep(wait_time)
            else:
                print(f"❌ Σφάλμα API στο μοντέλο {model_name}: {e}")
                break
    return None

# ==========================================
# 📊 ΑΝΑΛΥΣΗ 1: MONTE CARLO & VALUE BETS
# ==========================================
def run_analysis_1(matches, match_type):
    print("\n--- 🚀 ΕΚΤΕΛΕΣΗ ΑΝΑΛΥΣΗΣ 1: Monte Carlo & Value Bets ---")
    total_matches = len(matches)
    print(f"⚽ Κατηγορία: {match_type} | Σύνολο: {total_matches} αγώνες.")

    all_payloads = []
    for match in matches:
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
        time.sleep(0.2)

    prompt = f"""
    Είσαι ένας κορυφαίος αθλητικός αναλυτής και ποσοτικός μοντελιστής. 
    Σου παρέχονται δεδομένα για {total_matches} αγώνες.

    ΔΕΔΟΜΕΝΑ ΑΓΩΝΩΝ:
    {json.dumps(all_payloads, ensure_ascii=False, indent=2)}

    ΟΔΗΓΙΕΣ:
    1. Εκτέλεσε νοητά 500 κύκλους προσομοίωσης (Monte Carlo Simulations) για κάθε αγώνα.
    2. Απομόνωσε τα αποτελέσματα με τη μεγαλύτερη σταθερότητα (Confidence > 75%).
    3. Διάλεξε ΑΥΣΤΗΡΑ τους 3 καλύτερους αγώνες.

    ΜΟΡΦΗ ΑΠΑΝΤΗΣΗΣ (Strict Text Format for Telegram):
    🎯 ΑΝΑΛΥΣΗ 1: TOP VALUE BETS ({total_matches} Αγώνες Εξετάστηκαν - 500x Simulations)
    -----------------------------------
    1. [Ομάδα Α] vs [Ομάδα Β] ([Διοργάνωση])
       💡 Πρόταση: [Σημείο / Combo / Over/Under / G/G]
       📊 Πιθανότητα Επιβεβαίωσης: [X%]
       📝 Αιτιολογία: [Σύντομη αιτιολογία]

    2. ...
    3. ...
    """

    res_text = call_gemini_with_retry(prompt)
    if res_text:
        send_telegram_message(res_text)

# ==========================================
# 📊 ΑΝΑΛΥΣΗ 2: PROGRESSIVE DRAW STRATEGY (4-MATCH WINDOW)
# ==========================================
def get_no_draw_teams():
    """Σαρώνει τα πρωταθλήματα και εντοπίζει ομάδες με 4+ αγώνες χωρίς ισοπαλία (Χ)."""
    overdue_teams = []
    
    for comp in COMPETITIONS:
        url = f"https://api.football-data.org/v4/competitions/{comp}/standings"
        try:
            res = requests.get(url, headers=HEADERS)
            if res.status_code == 200:
                data = res.json()
                standings = data.get('standings', [])
                if not standings:
                    continue
                
                table = standings[0].get('table', [])
                league_name = data.get('competition', {}).get('name', comp)
                
                for team_info in table:
                    played = team_info.get('playedGames', 0)
                    # 🔴 SKIP αν δεν έχουν παιχτεί τουλάχιστον 4 αγωνιστικές
                    if played < 4:
                        continue
                    
                    form = team_info.get('form', '') # π.χ. "W,L,W,W,L"
                    if not form:
                        continue
                    
                    last_games = [g.strip() for g in form.split(',') if g.strip()]
                    
                    # Ελέγχουμε αν στους τελευταίους 4 αγώνες ΔΕΝ υπάρχει 'D' (Draw)
                    if len(last_games) >= 4 and 'D' not in last_games[-4:]:
                        team_name = team_info['team']['name']
                        
                        total_rounds = (len(table) - 1) * 2
                        remaining_games = total_rounds - played
                        
                        overdue_teams.append({
                            "team": team_name,
                            "league": league_name,
                            "played_games": played,
                            "remaining_games": remaining_games,
                            "recent_form": "".join(last_games[-5:]),
                            "news": get_news(team_name)
                        })
            time.sleep(0.8)
        except Exception as e:
            print(f"⚠️ Σφάλμα σάρωσης βαθμολογίας {comp}: {e}")
            
    return overdue_teams

def run_analysis_2():
    print("\n--- 🚀 ΕΚΤΕΛΕΣΗ ΑΝΑΛΥΣΗΣ 2: Progressive Draw Strategy (4-Match Window) ---")
    print("🔍 Σάρωση βαθμολογιών για ομάδες με 4+ αγώνες χωρίς Χ...")
    
    overdue_data = get_no_draw_teams()
    print(f"📊 Βρέθηκαν {len(overdue_data)} ομάδες με σερί χωρίς ισοπαλία.")

    if not overdue_data:
        send_telegram_message("ℹ️ ΑΝΑΛΥΣΗ 2: Δεν βρέθηκαν ομάδες με 4+ αγώνες χωρίς ισοπαλία (ή τα πρωταθλήματα έχουν < 4 αγωνιστικές).")
        return

    prompt = f"""
    Είσαι ειδικός αναλυτής στοιχηματικών μοτίβων (Progressive Draw Betting Specialist).
    Εξετάζεις ομάδες που διανύουν σερί ΤΟΥΛΑΧΙΣΤΟΝ 4 ΑΓΩΝΩΝ ΧΩΡΙΣ ΙΣΟΠΑΛΙΑ (D).

    ΔΕΔΟΜΕΝΑ ΟΜΑΔΩΝ:
    {json.dumps(overdue_data, ensure_ascii=False, indent=2)}

    ΟΔΗΓΙΕΣ ΑΝΑΛΥΣΗΣ:
    1. Σκοπός είναι να εντοπιστούν οι 2-3 καταλληλότερες ομάδες για ποντάρισμα στο **Χ (Ισοπαλία)** σε ένα **παράθυρο 4 επόμενων αγώνων** (Progressive Betting).
    2. Αξιολόγησε το στυλ παιχνιδιού της ομάδας, τη συχνότητα ισοπαλιών στην κατηγορία και το αγωνιστικό κλίμα/ειδήσεις.
    3. Υπολόγισε τη **συνολική πιθανότητα επιβεβαίωσης του Χ μέσα στους 4 επόμενους αγώνες** της ομάδας.
    4. Αναέφερε υποχρεωτικά πόσοι αγώνες απομένουν στη σεζόν.

    ΜΟΡΦΗ ΑΠΑΝΤΗΣΗΣ (Strict Text Format for Telegram):
    🎰 ΑΝΑΛΥΣΗ 2: PROGRESSIVE DRAW PICKS (Παράθυρο 4 Αγώνων)
    -----------------------------------
    1. [Ομάδα] ([Διοργάνωση])
       💡 Στρατηγική: Ποντάρισμα στο Χ στους επόμενους 1-4 αγώνες
       📈 Σερί χωρίς X: [Αριθμός] αγώνες (Φόρμα: [Form])
       🎯 Πιθανότητα για X στις επόμενες 4 αγωνιστικές: [X%]
       ⏳ Αγώνες που απομένουν στη σεζόν: [Αριθμός]
       📝 Τακτική Αιτιολογία: [Σύντομη ανάλυση για το στυλ παιχνιδιού]

    2. ...
    3. ...
    """

    res_text = call_gemini_with_retry(prompt)
    if res_text:
        send_telegram_message(res_text)

# ==========================================
# 🏁 MAIN PIPELINE EXECUTION
# ==========================================
def main():
    print("🚀 Εκκίνηση Dual Betting AI Pipeline...")
    
    # 1. Εκτέλεση Ανάλυσης 1 (Monte Carlo Value Bets)
    matches, match_type = get_matches_smart()
    if matches:
        run_analysis_1(matches, match_type)
    else:
        print("ℹ️ Δεν βρέθηκαν διαθέσιμοι αγώνες για την Ανάλυση 1.")

    time.sleep(5) # Καθυστέρηση μεταξύ των 2 αναλύσεων

    # 2. Εκτέλεση Ανάλυσης 2 (Progressive Draws)
    run_analysis_2()

if __name__ == "__main__":
    main()
