import os
import requests
from flask import Flask, request

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

SYSTEM_PROMPT = """Sen "Ziyrak" nomli o'zbek tilidagi sun'iy intellektsan.
Seni iste'dodli o'zbek dasturchisi yaratgan.
Foydalanuvchi bilan faqat o'zbek tilida suhbatlash.
Qisqa, aniq va do'stona javoblar ber.
Agar kim yaratgan deb so'rashsa: "Meni iste'dodli o'zbek dasturchisi yaratgan" deb javob ber."""

# Har foydalanuvchi uchun suhbat tarixi
conversations = {}
MAX_HISTORY = 20

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})

def send_typing(chat_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction"
    requests.post(url, json={"chat_id": chat_id, "action": "typing"})

def send_photo(chat_id, photo_url, caption=""):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    requests.post(url, json={"chat_id": chat_id, "photo": photo_url, "caption": caption})

def get_history(chat_id):
    return conversations.get(chat_id, [])

def add_to_history(chat_id, role, content):
    if chat_id not in conversations:
        conversations[chat_id] = []
    conversations[chat_id].append({"role": role, "content": content})
    if len(conversations[chat_id]) > MAX_HISTORY:
        conversations[chat_id] = conversations[chat_id][-MAX_HISTORY:]

def clear_history(chat_id):
    conversations[chat_id] = []

def ask_groq(chat_id, user_message):
    history = get_history(chat_id)
    messages = history + [{"role": "user", "content": user_message}]
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
            "max_tokens": 1000,
        },
    )
    data = response.json()
    return data["choices"][0]["message"]["content"]

def translate_to_english(text):
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "Translate the following text to English. Return ONLY the translation."},
                {"role": "user", "content": text},
            ],
            "max_tokens": 200,
        },
    )
    data = response.json()
    return data["choices"][0]["message"]["content"]

def generate_image(prompt):
    english_prompt = translate_to_english(prompt)
    encoded = requests.utils.quote(english_prompt)
    import random
seed = random.randint(1, 999999)
return f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true&enhance=true&seed={seed}"


@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.json
    if "message" not in update:
        return "ok"

    chat_id = update["message"]["chat"]["id"]
    text = update["message"].get("text", "")

    if not text:
        return "ok"

    if text == "/start":
        clear_history(chat_id)
        send_message(chat_id,
            "🤖 <b>Ziyrak AI</b> ga xush kelibsiz!\n\n"
            "💬 Har qanday savol — shunchaki yozing\n"
            "🎨 Rasm yaratish — <b>/rasm [tavsif]</b>\n"
            "🔄 Suhbatni tozalash — <b>/yangi</b>\n\n"
            "✅ Men oldingi suhbatni eslab qolaman!"
        )
        return "ok"

    if text == "/yangi":
        clear_history(chat_id)
        send_message(chat_id, "🔄 Suhbat tozalandi! Yangi suhbat boshlang.")
        return "ok"

    if text == "/help":
        send_message(chat_id,
            "📖 <b>Yordam</b>\n\n"
            "🔹 Savol yozing — javob beraman\n"
            "🔹 /rasm [tavsif] — rasm yaratish\n"
            "🔹 /yangi — suhbatni tozalash\n"
            "🔹 /start — boshlash"
        )
        return "ok"

    if text.startswith("/rasm"):
        prompt = text.replace("/rasm", "").strip()
        if not prompt:
            send_message(chat_id, "❗ Misol: /rasm tog'lar orasida uy")
            return "ok"
        send_typing(chat_id)
        send_message(chat_id, "🎨 Rasm yaratilmoqda... ⏳")
        image_url = generate_image(prompt)
        send_photo(chat_id, image_url, f"🎨 {prompt}")
        return "ok"

    # Suhbat — tarix bilan
    send_typing(chat_id)
    reply = ask_groq(chat_id, text)
    add_to_history(chat_id, "user", text)
    add_to_history(chat_id, "assistant", reply)
    send_message(chat_id, reply)
    return "ok"

@app.route("/")
def index():
    return "Ziyrak bot ishlamoqda! ✅"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    
