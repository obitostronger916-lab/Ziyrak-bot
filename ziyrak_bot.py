import os
import requests
from flask import Flask, request

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

SYSTEM_PROMPT = """Sen "Ziyrak" nomli o'zbek tilidagi sun'iy intellektsan. 
Foydalanuvchi bilan faqat o'zbek tilida suhbatlash. 
Qisqa, aniq va do'stona javoblar ber."""

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

def ask_groq(user_message):
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": 1000,
        },
    )
    data = response.json()
    return data["choices"][0]["message"]["content"]

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.json
    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")
        if text:
            reply = ask_groq(text)
            send_message(chat_id, reply)
    return "ok"

@app.route("/")
def index():
    return "Ziyrak bot ishlamoqda! ✅"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    
