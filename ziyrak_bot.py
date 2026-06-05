import os
import random
import base64
import logging
import requests
from flask import Flask, request

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

SYSTEM_PROMPT = """Sen "Ziyrak" nomli o'zbek tilidagi sun'iy intellektsan.
Seni Inferiq jamoasi yaratgan.
Foydalanuvchi bilan faqat o'zbek tilida suhbatlash.
Qisqa, aniq va do'stona javoblar ber.
Agar kim yaratgan deb so'rashsa: "Meni Inferiq jamoasi yaratgan" deb javob ber.
Agar qaysi AI yoki texnologiya haqida so'rashsa:
"Men Ziyrak AI — Inferiq jamoasi tomonidan yaratilgan maxsus sun'iy intellektman" deb javob ber.
Hech qachon boshqa AI kompaniyalar nomini tilga olma."""

conversations = {}
waiting_for_image = {}
MAX_HISTORY = 20


def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        data["reply_markup"] = reply_markup
    try:
        requests.post(url, json=data, timeout=10)
    except Exception as e:
        logger.error(f"send_message error: {e}")

def send_typing(chat_id):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"}, timeout=5
        )
    except Exception:
        pass

def send_upload_photo(chat_id):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction",
            json={"chat_id": chat_id, "action": "upload_photo"}, timeout=5
        )
    except Exception:
        pass

def send_photo(chat_id, photo_url, caption=""):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
            json={"chat_id": chat_id, "photo": photo_url, "caption": caption},
            timeout=15
        )
    except Exception as e:
        logger.error(f"send_photo error: {e}")

def get_file_url(file_id):
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}",
            timeout=10
        )
        data = r.json()
        if data.get("ok"):
            return f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{data['result']['file_path']}"
    except Exception as e:
        logger.error(f"get_file_url error: {e}")
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
    conversations.pop(chat_id, None)
    waiting_for_image.pop(chat_id, None)


def ask_groq(chat_id, user_message):
    history = get_history(chat_id)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [{"role": "user", "content": user_message}]
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={"model": "llama-3.3-70b-versatile", "messages": messages, "max_tokens": 1000},
            timeout=30
        )
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Groq error: {e}")
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
    return f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&nologo=true&enhance=true&seed={seed}"

def main_menu():
    return {
        "keyboard": [
            [{"text": "🎨 Rasm yaratish"}, {"text": "🔄 Yangi suhbat"}],
            [{"text": "❓ Yordam"}]
        ],
        "resize_keyboard": True
    }


@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.json
    if not update:
        return "ok"

    message = update.get("message") or update.get("business_message")
    if not message:
        return "ok"

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
        send_message(chat_id, reply, reply_markup=main_menu())
        waiting_for_image[chat_id] = False
        return "ok"

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
        send_message(chat_id, reply, reply_markup=main_menu())
        return "ok"

    if not text:
        return "ok"

    # /start
    if text == "/start":
        clear_history(chat_id)
        send_message(chat_id,
            "🤖 <b>Ziyrak AI</b> ga xush kelibsiz!\n\n"
            "💬 Har qanday savol yozing — javob beraman\n"
            "🖼 Rasm yuboring — tahlil qilaman\n"
            "🎨 Rasm yaratish tugmasini bosing\n\n"
            "✅ Men oldingi suhbatni eslab qolaman!\n\n"
            "<i>Inferiq jamoasi tomonidan yaratilgan</i>",
            reply_markup=main_menu()
        )
        return "ok"

    if text in ["🔄 Yangi suhbat", "/yangi"]:
        clear_history(chat_id)
        send_message(chat_id, "🔄 Suhbat tozalandi! Yangi suhbat boshlang.", reply_markup=main_menu())
        return "ok"

    if text in ["❓ Yordam", "/help"]:
        send_message(chat_id,
            "📖 <b>Ziyrak AI — Yordam</b>\n\n"
            "🔹 Savol yozing — javob beraman\n"
            "🔹 Rasm yuboring — tahlil qilaman\n"
            "🔹 🎨 Rasm yaratish — tugmani bosing\n"
            "🔹 🔄 Yangi suhbat — tarixni tozalash\n\n"
            "<i>Inferiq jamoasi</i>",
            reply_markup=main_menu()
        )
        return "ok"

    if text in ["🎨 Rasm yaratish", "/rasm"]:
        waiting_for_image[chat_id] = True
        send_message(chat_id,
            "🎨 <b>Rasm yaratish</b>\n\n"
            "Qanday rasm yaratishni xohlaysiz?\n"
            "Tavsifini yozing — men yarataman!\n\n"
            "<i>Misol: tog'lar orasida qo'rg'on, kech kuz</i>",
            reply_markup={"keyboard": [[{"text": "❌ Bekor qilish"}]], "resize_keyboard": True}
        )
        return "ok"

    if text == "❌ Bekor qilish":
        waiting_for_image[chat_id] = False
        send_message(chat_id, "❌ Bekor qilindi.", reply_markup=main_menu())
        return "ok"

    if waiting_for_image.get(chat_id):
        waiting_for_image[chat_id] = False
        send_upload_photo(chat_id)
        send_message(chat_id, "🎨 Rasm yaratilmoqda... ⏳")
        image_url = generate_image(text)
        send_photo(chat_id, image_url, f"🎨 {text[:80]}")
        send_message(chat_id, "✅ Rasm tayyor!", reply_markup=main_menu())
        return "ok"

    # Oddiy suhbat
    send_typing(chat_id)
    reply = ask_groq(chat_id, text)
    add_to_history(chat_id, "user", text)
    add_to_history(chat_id, "assistant", reply)
    send_message(chat_id, reply, reply_markup=main_menu())
    return "ok"


@app.route("/")
def index():
    return "Ziyrak AI — Inferiq jamoasi ✅"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
        
