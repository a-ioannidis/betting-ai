import os
import requests
import feedparser
import json
from urllib.parse import quote
from google import genai
from google.genai import types

client = genai.Client()

def get_news(team_name):
    """Τραβάει ειδήσεις μέσω Google News RSS με ασφαλές URL encoding."""
    encoded_query = quote(f"{team_name} football")
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
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
            temperature=0.2,
            system_instruction="Είσαι αναλυτής στοιχηματικών δεδομένων. Να είσαι αυστηρά αντικειμενικός."
        )
    )
    
    return response.text

def main():
    print("🚀 Εκκίνηση Pipeline (Direct Google API)...")
    
    sample_match = {
        "match": "Arsenal vs Chelsea",
        "home_news": get_news("Arsenal FC"),
        "away_news": get_news("Chelsea FC")
    }

    print(f"📊 Συλλέχθηκαν ειδήσεις για: {sample_match['match']}")
    
    analysis = analyze_with_gemini(sample_match)
    
    print("\n--- ΑΠΟΤΕΛΕΣΜΑ GEMINI ---")
    print(analysis)

if __name__ == "__main__":
    main()
