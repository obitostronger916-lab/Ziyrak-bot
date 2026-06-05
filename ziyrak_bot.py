import os
import random
import base64
import logging
from functools import lru_cache

import requests
from flask import Flask, request
from openai import OpenAI

app = Flask(__name__)

# ================== CONFIG ==================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
    logger.error("TELEGRAM_TOKEN yoki OPENAI_API_KEY topilmadi!")

SYSTEM_PROMPT = """Sen "Ziyrak" nomli o'zbek tilidagi sun'iy intellektsan.
Seni Inferiq jamoasi yaratgan.
Foydalanuvchi bilan faqat o'zbek tilida suhbatlash.
Qisqa, aniq va do'stona javoblar ber.
Agar kim yaratgan deb so'rashsa: "Meni Inferiq jamoasi yaratgan" deb javob ber.
Agar qaysi AI yoki texnologiya haqida so'rashsa:
"Men Ziyrak AI — Inferiq jamoasi tomonidan yaratilgan maxsus sun'iy intellektman" deb javob ber.
Hech qachon boshqa AI kompaniyalar nomini tilga olma."""

# In-memory storage (Productionda Redis tavsiya qilinadi)
conversations = {}
waiting_for_image = {}
MAX_HISTORY = 20

client = OpenAI(api_key=OPENAI_API_KEY)


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
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction",
        json={"chat_id": chat_id, "action": "typing"}, timeout=5
    )


def send_upload_photo(chat_id):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendChatAction",
        json={"chat_id": chat_id, "action": "upload_photo"}, timeout=5
    )


def send_photo(chat_id, photo_url, caption=""):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
        json={"chat_id": chat_id, "photo": photo_url, "caption": caption},
        timeout=15
    )


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


@lru_cache(maxsize=100)
def translate_to_english(text: str) -> str:
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Translate to English. Return ONLY the translation."},
                {"role": "user", "content": text}
            ],
            max_tokens=300,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Translate error: {e}")
        return text


def generate_image(prompt: str):
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


def ask_openai(chat_id, user_message):
    history = get_history(chat_id)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [{"role": "user", "content": user_message}]

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",          # tez va arzon
            messages=messages,
            max_tokens=1200,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI error: {e}")
        return "Vaqtinchalik xatolik yuz berdi. Iltimos, qayta urinib ko'ring."


def ask_openai_with_image(chat_id, image_url, caption):
    question = caption if caption else "Bu rasmda nima ko'rinayapti? O'zbek tilida batafsil tushuntirib ber."

    try:
        img_data = requests.get(image_url, timeout=15).content
        img_b64 = base64.b64encode(img_data).decode('utf-8')

        response = client.chat.completions.create(
            model="gpt-4o",               # Vision uchun eng yaxshisi
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": question},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}
                        }
                    ]
                }
            ],
            max_tokens=1200
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Vision error: {e}")
        return ask_openai(chat_id, question)


# ===================== WEBHOOK =====================
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

    # Rasm yuborilganda
    if "photo" in message:
        send_typing(chat_id)
        file_url = get_file_url(message["photo"][-1]["file_id"])
        reply = ask_openai_with_image(chat_id, file_url, caption) if file_url else "Rasmni yuklab bo'lmadi."
        add_to_history(chat_id, "user", "[Rasm]")
        add_to_history(chat_id, "assistant", reply)
        send_message(chat_id, reply, reply_markup=main_menu())
        waiting_for_image[chat_id] = False
        return "ok"

    # Document (agar rasm bo'lsa)
    if "document" in message:
        send_typing(chat_id)
        doc = message["document"]
        name = doc.get("file_name", "fayl")
        if doc.get("mime_type", "").startswith("image/"):
            file_url = get_file_url(doc["file_id"])
            reply = ask_openai_with_image(chat_id, file_url, caption) if file_url else "Faylni yuklab bo'lmadi."
        else:
            reply = "Hozircha faqat rasmlar bilan ishlay olaman."
        add_to_history(chat_id, "user", f"[Fayl: {name}]")
        add_to_history(chat_id, "assistant", reply)
        send_message(chat_id, reply, reply_markup=main_menu())
        return "ok"

    if not text:
        return "ok"

    # Buyruqlar
    if text == "/start":
        clear_history(chat_id)
        send_message(chat_id,
            "🤖 <b>Ziyrak AI</b> ga xush kelibsiz!\n\n"
            "💬 Har qanday savol yozing\n"
            "🖼 Rasm yuboring — tahlil qilaman\n"
            "🎨 Rasm yaratish tugmasini bosing\n\n"
            "<i>Inferiq jamoasi tomonidan yaratilgan</i>",
            reply_markup=main_menu())
        return "ok"

    if text in ["🔄 Yangi suhbat", "/yangi"]:
        clear_history(chat_id)
        send_message(chat_id, "🔄 Suhbat tarixi tozalandi. Yangi suhbat boshlandi!", reply_markup=main_menu())
        return "ok"

    if text in ["❓ Yordam", "/help"]:
        send_message(chat_id,
            "📖 <b>Yordam</b>\n\n"
            "• Oddiy savollaringizga javob beraman\n"
            "• Rasm yuborsangiz — tahlil qilaman\n"
            "• 🎨 tugmasi orqali rasm yarataman\n\n"
            "<i>Inferiq jamoasi</i>",
            reply_markup=main_menu())
        return "ok"

    if text in ["🎨 Rasm yaratish", "/rasm"]:
        waiting_for_image[chat_id] = True
        send_message(chat_id,
            "🎨 Qanday rasm yaratmoqchisiz?\n\nTavsifini yozing (masalan: tog'lar orasidagi qadimiy qal'a, kechqurun)",
            reply_markup={"keyboard": [[{"text": "❌ Bekor qilish"}]], "resize_keyboard": True})
        return "ok"

    if text == "❌ Bekor qilish":
        waiting_for_image[chat_id] = False
        send_message(chat_id, "❌ Bekor qilindi.", reply_markup=main_menu())
        return "ok"

    # Rasm yaratish rejimi
    if waiting_for_image.get(chat_id):
        waiting_for_image[chat_id] = False
        send_upload_photo(chat_id)
        send_message(chat_id, "🎨 Rasm yaratilmoqda... ⏳")
        image_url = generate_image(text)
        send_photo(chat_id, image_url, f"🎨 {text[:80]}")
        send_message(chat_id, "✅ Rasm tayyor! Yana yaratamizmi?", reply_markup=main_menu())
        return "ok"

    # Oddiy suhbat
    send_typing(chat_id)
    reply = ask_openai(chat_id, text)
    add_to_history(chat_id, "user", text)
    add_to_history(chat_id, "assistant", reply)
    send_message(chat_id, reply, reply_markup=main_menu())

    return "ok"


@app.route("/")
def index():
    return "Ziyrak AI — OpenAI + Inferiq ✅"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
