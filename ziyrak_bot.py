import os
import requests
from flask import Flask, request

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

SYSTEM_PROMPT = """Sen "Ziyrak" nomli o'zbek tilidagi sun'iy intellektsan.
Seni yaratgan dasturchi tomonidan ishlab chiqilgan.
Foydalanuvchi bilan faqat o'zbek tilida suhbatlash.
Qisqa, aniq va do'stona javoblar ber.
Agar kim yaratgan deb so'rashsa: "Meni iste'dodli o'zbek dasturchisi yaratgan" deb javob ber."""

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

def send_photo(chat_id, photo_url, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    requests.post(url, json={"chat_id": chat_id, "photo": photo_url, "caption": caption})

def send_typing(chat_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction"
    requests.post(url, json={"chat_id": chat_id, "action": "upload_photo"})

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

def translate_to_english(text):
    """O'zbek matnni inglizchaga tarjima qilish"""
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "Translate the following text to English. Return ONLY the translation, nothing else."},
                {"role": "user", "content": text},
            ],
            "max_tokens": 200,
        },
    )
    data = response.json()
    return data["choices"][0]["message"]["content"]

def generate_image(prompt):
    """Pollinations AI orqali rasm yaratish"""
    english_prompt = translate_to_english(prompt)
    english_prompt = english_prompt.replace(" ", "%20")
    image_url = f"https://image.pollinations.ai/prompt/{english_prompt}?width=1024&height=1024&nologo=true&enhance=true"
    return image_url

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.json
    if "message" in update:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")

        if not text:
            return "ok"

        # /start buyrug'i
        if text == "/start":
            send_message(chat_id, 
                "🤖 <b>Ziyrak AI</b> ga xush kelibsiz!\n\n"
                "Men sizga quyidagilarda yordam bera olaman:\n\n"
                "💬 Har qanday savol — shunchaki yozing\n"
                "🎨 Rasm yaratish — <b>/rasm [tavsif]</b>\n\n"
                "Misol: /rasm tog'lar orasida uy"
            )
            return "ok"

        # /help buyrug'i
        if text == "/help":
            send_message(chat_id,
                "📖 <b>Ziyrak AI — Yordam</b>\n\n"
                "🔹 Oddiy suhbat — istalgan savol yozing\n"
                "🔹 /rasm [tavsif] — rasm yaratish\n"
                "🔹 /start — boshlash\n\n"
                "Misol: /rasm koinotda uchayotgan ot"
            )
            return "ok"

        # /rasm buyrug'i
        if text.startswith("/rasm"):
            prompt = text.replace("/rasm", "").strip()
            if not prompt:
                send_message(chat_id, "❗ Rasm tavsifini yozing!\nMisol: /rasm tog'lar orasida uy")
                return "ok"
            
            send_typing(chat_id)
            send_message(chat_id, "🎨 Rasm yaratilmoqda... biroz kuting ⏳")
            
            image_url = generate_image(prompt)
            send_photo(chat_id, image_url, f"🎨 {prompt}")
            return "ok"

        # Oddiy suhbat
        reply = ask_groq(text)
        send_message(chat_id, reply)

    return "ok"

@app.route("/")
def index():
    return "Ziyrak bot ishlamoqda! ✅"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    
