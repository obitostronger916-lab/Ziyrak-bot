import os
import random
import requests
from flask import Flask, request

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

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


# ─── GEMINI AI ───

def ask_gemini(chat_id, user_message):
    """Gemini API bilan suhbat"""
    history = get_history(chat_id)

    # Gemini formatida tarix
    gemini_history = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        gemini_history.append({
            "role": role,
            "parts": [{"text": msg["content"]}]
        })

    # Yangi xabar
    gemini_history.append({
        "role": "user",
        "parts": [{"text": user_message}]
    })

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "system_instruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": gemini_history,
        "generationConfig": {
            "maxOutputTokens": 1000,
            "temperature": 0.7
        }
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"Xatolik yuz berdi: {str(e)}"

def ask_gemini_with_image(chat_id, image_url, caption):
    """Gemini Vision — rasm tahlili"""
    question = caption if caption else "Bu rasmda nima ko'rinyapti? O'zbek tilida tushuntir."

    # Rasmni base64 ga o'girish
    try:
        img_data = requests.get(image_url, timeout=15).content
        import base64
        img_b64 = base64.b64encode(img_data).decode()
    except Exception:
        return ask_gemini(chat_id, f"Foydalanuvchi rasm yubordi: {question}")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "system_instruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": [{
            "role": "user",
            "parts": [
                {"inline_data": {"mime_type": "image/jpeg", "data": img_b64}},
                {"text": question}
            ]
        }],
        "generationConfig": {"maxOutputTokens": 1000}
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return ask_gemini(chat_id, question)

def translate_to_english(text):
    """Tarjima uchun Gemini"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": f"Translate to English. Return ONLY translation: {text}"}]}],
        "generationConfig": {"maxOutputTokens": 200}
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        d = r.json()
        return d["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return text

def generate_image(prompt):
    """Pollinations AI bilan rasm yaratish"""
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

    # Rasm
    if "photo" in message:
        send_typing(chat_id)
        photo = message["photo"][-1]
        file_url = get_file_url(photo["file_id"])
        if file_url:
            reply = ask_gemini_with_image(chat_id, file_url, caption)
        else:
            reply = "Rasmni yuklab bo'lmadi."
        add_to_history(chat_id, "user", f"[Rasm] {caption}" if caption else "[Rasm yubordi]")
        add_to_history(chat_id, "assistant", reply)
        send_message(chat_id, reply)
        return "ok"

    # Fayl
    if "document" in message:
        send_typing(chat_id)
        doc = message["document"]
        mime = doc.get("mime_type", "")
        name = doc.get("file_name", "fayl")
        if mime.startswith("image/"):
            file_url = get_file_url(doc["file_id"])
            if file_url:
                reply = ask_gemini_with_image(chat_id, file_url, caption)
            else:
                reply = "Faylni yuklab bo'lmadi."
        else:
            reply = ask_gemini(chat_id, caption if caption else f"'{name}' nomli fayl yuborildi.")
        add_to_history(chat_id, "user", f"[Fayl: {name}]")
        add_to_history(chat_id, "assistant", reply)
        send_message(chat_id, reply)
        return "ok"

    if not text:
        return "ok"

    # /start
    if text == "/start":
        clear_history(chat_id)
        send_message(chat_id,
            "🤖 <b>Ziyrak AI</b> ga xush kelibsiz!\n\n"
        
            "💬 Har qanday savol — shunchaki yozing\n"
            "🖼 Rasm yuboring — tahlil qilaman\n"
            "🎨 Rasm yaratish — <b>/rasm [tavsif]</b>\n"
            "🔄 Suhbatni tozalash — <b>/yangi</b>"
        )
        return "ok"

    if text == "/yangi":
        clear_history(chat_id)
        send_message(chat_id, "🔄 Suhbat tozalandi!")
        return "ok"

    if text == "/help":
        send_message(chat_id,
            "📖 <b>Ziyrak AI — Yordam</b>\n\n"
            "🔹 Savol yozing — javob beraman\n"
            "🔹 Rasm yuboring — tahlil qilaman\n"
            "🔹 /rasm [tavsif] — rasm yaratish\n"
            "🔹 /yangi — suhbatni tozalash"
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

    # Oddiy suhbat
    send_typing(chat_id)
    reply = ask_gemini(chat_id, text)
    add_to_history(chat_id, "user", text)
    add_to_history(chat_id, "assistant", reply)
    send_message(chat_id, reply)
    return "ok"


@app.route("/")
def index():
    return "Ziyrak AI (Gemini) ishlamoqda! ✅"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    
