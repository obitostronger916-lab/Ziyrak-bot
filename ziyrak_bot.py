import os
import random
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

# Suhbat tarixi
conversations = {}
MAX_HISTORY = 20


# ─── YORDAMCHI FUNKSIYALAR ───

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
    """Telegram file_id dan to'liq URL olish"""
    r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}")
    data = r.json()
    if data.get("ok"):
        file_path = data["result"]["file_path"]
        return f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
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


# ─── AI FUNKSIYALAR ───

def ask_groq(chat_id, user_message):
    """Matn savoli uchun Groq AI"""
    history = get_history(chat_id)
    messages = history + [{"role": "user", "content": user_message}]
    try:
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
            timeout=30,
        )
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Xatolik yuz berdi: {str(e)}"

def ask_groq_with_image(chat_id, image_url, caption):
    """Rasm tahlili uchun — Groq vision"""
    question = caption if caption else "Bu rasmda nima ko'rinyapti? O'zbek tilida tushuntir."
    history = get_history(chat_id)

    messages = history + [{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": image_url}},
            {"type": "text", "text": question}
        ]
    }]

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.2-90b-vision-preview",
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
                "max_tokens": 1000,
            },
            timeout=30,
        )
        data = response.json()
        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        else:
            return ask_groq(chat_id, f"Foydalanuvchi rasm yubordi va shunday dedi: {question}")
    except Exception:
        return ask_groq(chat_id, f"Foydalanuvchi rasm yubordi va shunday dedi: {question}")

def translate_to_english(text):
    """O'zbekchadan inglizchaga tarjima"""
    try:
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
            timeout=15,
        )
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception:
        return text

def generate_image(prompt):
    """Pollinations AI bilan rasm yaratish — har safar boshqacha"""
    english_prompt = translate_to_english(prompt)
    encoded = requests.utils.quote(english_prompt)
    seed = random.randint(1, 999999)
    return f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true&enhance=true&seed={seed}"


# ─── WEBHOOK ───

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.json

    if "message" not in update:
        return "ok"

    message = update["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()
    caption = message.get("caption", "").strip()

    # ── Rasm yuborilgan bo'lsa ──
    if "photo" in message:
        send_typing(chat_id)
        photo = message["photo"][-1]  # Eng katta o'lchamdagi rasm
        file_url = get_file_url(photo["file_id"])
        if file_url:
            reply = ask_groq_with_image(chat_id, file_url, caption)
        else:
            reply = "Rasmni yuklab bo'lmadi. Qayta urinib ko'ring."
        add_to_history(chat_id, "user", f"[Rasm yubordi] {caption}" if caption else "[Rasm yubordi]")
        add_to_history(chat_id, "assistant", reply)
        send_message(chat_id, reply)
        return "ok"

    # ── Hujjat (fayl) yuborilgan bo'lsa ──
    if "document" in message:
        send_typing(chat_id)
        doc = message["document"]
        mime = doc.get("mime_type", "")
        name = doc.get("file_name", "fayl")

        # Agar rasm fayl bo'lsa
        if mime.startswith("image/"):
            file_url = get_file_url(doc["file_id"])
            if file_url:
                reply = ask_groq_with_image(chat_id, file_url, caption)
            else:
                reply = "Faylni yuklab bo'lmadi."
        else:
            question = caption if caption else f"'{name}' nomli fayl yuborildi."
            reply = ask_groq(chat_id, question)

        add_to_history(chat_id, "user", f"[Fayl: {name}] {caption}" if caption else f"[Fayl: {name}]")
        add_to_history(chat_id, "assistant", reply)
        send_message(chat_id, reply)
        return "ok"

    # ── Matn xabarlari ──
    if not text:
        return "ok"

    # /start
    if text == "/start":
        clear_history(chat_id)
        send_message(chat_id,
            "🤖 <b>Ziyrak AI</b> ga xush kelibsiz!\n\n"
            "Men sizga quyidagilarda yordam bera olaman:\n\n"
            "💬 Har qanday savol — shunchaki yozing\n"
            "🖼 Rasm yuboring — tahlil qilaman\n"
            "🎨 Rasm yaratish — <b>/rasm [tavsif]</b>\n"
            "🔄 Suhbatni tozalash — <b>/yangi</b>\n\n"
            "✅ Men oldingi suhbatni eslab qolaman!"
        )
        return "ok"

    # /yangi
    if text == "/yangi":
        clear_history(chat_id)
        send_message(chat_id, "🔄 Suhbat tozalandi! Yangi suhbat boshlang.")
        return "ok"

    # /help
    if text == "/help":
        send_message(chat_id,
            "📖 <b>Ziyrak AI — Yordam</b>\n\n"
            "🔹 Savol yozing — javob beraman\n"
            "🔹 Rasm yuboring — tahlil qilaman\n"
            "🔹 /rasm [tavsif] — rasm yaratish\n"
            "🔹 /yangi — suhbatni tozalash\n"
            "🔹 /start — boshlash"
        )
        return "ok"

    # /rasm
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

    # Oddiy suhbat
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
        
