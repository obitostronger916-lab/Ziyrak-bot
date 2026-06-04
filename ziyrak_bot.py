import os
import random
import base64
import requests
from flask import Flask, request

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

SYSTEM_PROMPT = """Sen "Ziyrak" nomli o'zbek tilidagi sun'iy intellektsan.
Seni iste'dodli o'zbek dasturchisi yaratgan.
Foydalanuvchi bilan faqat o'zbek tilida suhbatlash.
Qisqa, aniq va do'stona javoblar ber.
Agar kim yaratgan deb so'rashsa: "Meni iste'dodli o'zbek dasturchisi yaratgan" deb javob ber.
Agar qaysi AI yoki texnologiya haqida so'rashsa:
"Men Ziyrak AI — o'zbek dasturchilari tomonidan yaratilgan maxsus sun'iy intellektman" deb javob ber."""

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

def get_file_url(file_id):
    r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}")
    data = r.json()
    if data.get("ok"):
        return f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{data['result']['file_path']}"
    return None

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
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
                "max_tokens": 1000
            },
            timeout=30
        )
        return r.json()["choices"][0]["message"]["content"]
    except Exception:
        return "Vaqtinchalik xatolik. Qayta urinib ko'ring."

def ask_groq_with_image(chat_id, image_url, caption):
    question = caption if caption else "Bu rasmda nima ko'rinyapti? O'zbek tilida tushuntir."
    try:
        img_data = requests.get(image_url, timeout=15).content
        img_b64 = base64.b64encode(img_data).decode()
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.2-90b-vision-preview",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                        {"type": "text", "text": question}
                    ]}
                ],
                "max_tokens": 1000
            },
            timeout=30
        )
        d = r.json()
        if "choices" in d:
            return d["choices"][0]["message"]["content"]
        return ask_groq(chat_id, question)
    except Exception:
        return ask_groq(chat_id, question)

def translate_to_english(text):
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": "Translate to English. Return ONLY the translation."},
                    {"role": "user", "content": text}
                ],
                "max_tokens": 200
            },
            timeout=15
        )
        return r.json()["choices"][0]["message"]["content"]
    except Exception:
        return text

def generate_image(prompt):
    english = translate_to_english(prompt)
    encoded = requests.utils.quote(english)
    seed = random.randint(1, 999999)
    return f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true&enhance=true&seed={seed}&model=nanobanana

def handle_message(message):
    """Xabarni qayta ishlash — oddiy va business xabarlar uchun"""
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    caption = message.get("caption", "").strip()

    # Rasm
    if "photo" in message:
        send_typing(chat_id)
        file_url = get_file_url(message["photo"][-1]["file_id"])
        reply = ask_groq_with_image(chat_id, file_url, caption) if file_url else "Rasmni yuklab bo'lmadi."
        add_to_history(chat_id, "user", "[Rasm]")
        add_to_history(chat_id, "assistant", reply)
        send_message(chat_id, reply)
        return

    # Fayl
    if "document" in message:
        send_typing(chat_id)
        doc = message["document"]
        name = doc.get("file_name", "fayl")
        if doc.get("mime_type", "").startswith("image/"):
            file_url = get_file_url(doc["file_id"])
            reply = ask_groq_with_image(chat_id, file_url, caption) if file_url else "Faylni yuklab bo'lmadi."
        else:
            reply = ask_groq(chat_id, caption if caption else f"'{name}' fayl yuborildi.")
        add_to_history(chat_id, "user", f"[Fayl: {name}]")
        add_to_history(chat_id, "assistant", reply)
        send_message(chat_id, reply)
        return

    if not text:
        return

    if text == "/start":
        clear_history(chat_id)
        send_message(chat_id,
            "🤖 <b>Ziyrak AI</b> ga xush kelibsiz!\n\n"
            "💬 Har qanday savol — shunchaki yozing\n"
            "🖼 Rasm yuboring — tahlil qilaman\n"
            "🎨 Rasm yaratish — <b>/rasm [tavsif]</b>\n"
            "🔄 Suhbatni tozalash — <b>/yangi</b>\n\n"
            "✅ Men oldingi suhbatni eslab qolaman!")
        return

    if text == "/yangi":
        clear_history(chat_id)
        send_message(chat_id, "🔄 Suhbat tozalandi!")
        return

    if text == "/help":
        send_message(chat_id,
            "📖 <b>Ziyrak AI — Yordam</b>\n\n"
            "🔹 Savol yozing — javob beraman\n"
            "🔹 Rasm yuboring — tahlil qilaman\n"
            "🔹 /rasm [tavsif] — rasm yaratish\n"
            "🔹 /yangi — suhbatni tozalash")
        return

    if text.startswith("/rasm"):
        prompt = text.replace("/rasm", "").strip()
        if not prompt:
            send_message(chat_id, "❗ Misol: /rasm tog'lar orasida uy")
            return
        send_typing(chat_id)
        send_message(chat_id, "🎨 Rasm yaratilmoqda... ⏳")
        send_photo(chat_id, generate_image(prompt), f"🎨 {prompt}")
        return

    # Oddiy suhbat
    send_typing(chat_id)
    reply = ask_groq(chat_id, text)
    add_to_history(chat_id, "user", text)
    add_to_history(chat_id, "assistant", reply)
    send_message(chat_id, reply)


@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.json

    # Oddiy xabar
    if "message" in update:
        handle_message(update["message"])

    # Telegram Business xabari
    if "business_message" in update:
        handle_message(update["business_message"])

    return "ok"


@app.route("/")
def index():
    return "Ziyrak AI ishlamoqda! ✅"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    
