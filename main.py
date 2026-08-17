import os
import requests
import feedparser
import json
import time
from datetime import datetime
from urllib.parse import quote
from google import genai
from google.genai import types

# 1. Αρχικοποίηση Clients & Keys
client = genai.Client()
FOOTBALL_DATA_API_KEY = os.getenv("FOOTBALL_DATA_API_KEY")

HEADERS = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}

def get_todays_matches():
    """Τραβάει τους σημερινούς αγώνες από το football-data.org."""
    today = datetime.now().strftime('%Y-%m-%d')
    url = f"https://api.football-data.org/v4/matches?dateFrom={today}&dateTo={today}"
    
    try:
        response = requests.get(url, headers=HEADERS)
        if response.status_code == 200:
            data = response.json()
            matches = data.get('matches', [])
            return matches
        else:
            print(f"⚠️ Σφάλμα API {response.status_code}: {response.text}")
            return []
    except Exception as e:
        print(f"❌ Αποτυχία σύνδεσης με football-data.org: {e}")
        return []

def get_news(team_name):
    """Τραβάει ειδήσεις μέσω Google News RSS με ασφαλές URL encoding."""
    encoded_query = quote(f"{team_name} football")
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(rss_url)
    return [entry.title for entry in feed.entries[:3]]

def analyze_with_gemini(match_data):
    """Στέλνει τα δεδομένα στο Gemini API."""
    prompt = f"""
    Είσαι ένας επαγγελματίας αθλητικός αναλυτής. 
    Ανάλυσε τα παρακάτω δεδομένα για τον αγώνα:

    {json.dumps(match_data, ensure_ascii=False, indent=2)}

    Υπολόγισε τις πιθανότητες νίκης/ισοπαλίας (1, X, 2) σε ποσοστά (%) και δώσε μια σύντομη αιτιολόγηση.
    """

    response = client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            system_instruction="Είσαι αναλυτής στοιχηματικών δεδομένων. Να είσαι αυστηρά αντικειμενικός."
        )
    )
    return response.text

def main():
    print("🚀 Εκκίνηση Pipeline - Λήψη Σημερινών Αγώνων...")
    
    matches = get_todays_matches()
    print(f"⚽ Βρέθηκαν {len(matches)} αγώνες για σήμερα.")

    if not matches:
        print("ℹ️ Δεν υπάρχουν διαθέσιμοι αγώνες σήμερα ή δεν βρέθηκαν δεδομένα.")
        return

    # Αναλύουμε έως 5 αγώνες για να τηρήσουμε τα δωρεάν όρια
    for match in matches[:5]:
        home_team = match['homeTeam']['name']
        away_team = match['awayTeam']['name']
        league = match['competition']['name']
        
        print(f"\n🔄 Επεξεργασία: {home_team} vs {away_team} ({league})")
        
        match_payload = {
            "match": f"{home_team} vs {away_team}",
            "league": league,
            "status": match['status'],
            "home_news": get_news(home_team),
            "away_news": get_news(away_team)
        }
        
        analysis = analyze_with_gemini(match_payload)
        
        print(f"\n--- ΑΝΑΛΥΣΗ: {home_team} vs {away_team} ---")
        print(analysis)
        
        # Καθυστέρηση 6 δευτερολέπτων για σεβασμό των 10 calls/min
        time.sleep(6)

if __name__ == "__main__":
    main()
