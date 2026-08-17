import os
import requests
import feedparser
import json
from google import genai
from google.genai import types

# 1. Αρχικοποίηση του Google GenAI Client
# Παίρνει αυτόματα το GEMINI_API_KEY από τα Environment Variables (GitHub Secrets)
client = genai.Client()

def get_news(team_name):
    """Τραβάει ειδήσεις μέσω Google News RSS."""
    rss_url = f"https://news.google.com/rss/search?q={team_name}+football&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(rss_url)
    return [entry.title for entry in feed.entries[:3]]

def analyze_with_gemini(match_data):
    """Στέλνει τα δεδομένα απευθείας στο Gemini 2.5 Flash."""
    prompt = f"""
    Είσαι ένας επαγγελματίας αθλητικός αναλυτής. 
    Ανάλυσε τα παρακάτω δεδομένα για τον αγώνα:

    {json.dumps(match_data, ensure_ascii=False, indent=2)}

    Υπολόγισε τις πιθανότητες νίκης/ισοπαλίας (1, X, 2) σε ποσοστά (%) και δώσε μια σύντομη αιτιολόγηση.
    """

    print("🧠 Αποστολή απευθείας στο Gemini 2.5 Flash...")
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2, # Χαμηλό temperature για πιο στατιστική/λογική ανάλυση
            system_instruction="Είσαι αναλυτής στοιχηματικών δεδομένων. Να είσαι αυστηρά αντικειμενικός."
        )
    )
    
    return response.text

def main():
    print("🚀 Εκκίνηση Pipeline (Direct Google API)...")
    
    # Παράδειγμα δεδομένων αγώνα
    sample_match = {
        "match": "Arsenal vs Chelsea",
        "home_news": get_news("Arsenal FC"),
        "away_news": get_news("Chelsea FC")
    }

    print(f"📊 Συλλέχθηκαν ειδήσεις για: {sample_match['match']}")
    
    # Ανάλυση με Gemini
    analysis = analyze_with_gemini(sample_match)
    
    print("\n--- ΑΠΟΤΕΛΕΣΜΑ GEMINI ---")
    print(analysis)

if __name__ == "__main__":
    main()