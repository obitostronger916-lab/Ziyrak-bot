import os
import json
import requests
from flask import Flask, request

app = Flask(__name__)

# Environment variables dan olinadi
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

SYSTEM_PROMPT = """Sen "Ziyrak" nomli o'zbek tilidagi sun'iy intellektsan. 
Foydalanuvchi bilan faqat o'zbek tilida suhbatlash. 
Qisqa, aniq va do'stona javoblar ber."""

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

def ask_claude(user_message):
    response = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 1000,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_message}],
        },
    )
    data = response.json()
    return data["content"][0]["text"]

@app.route(f"/webhook", methods=["POST"])
def webhook():
    update = request.json
    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")
        if text:
            reply = ask_claude(text)
            send_message(chat_id, reply)
    return "ok"

@app.route("/")
def index():
    return "Ziyrak bot ishlamoqda! ✅"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
