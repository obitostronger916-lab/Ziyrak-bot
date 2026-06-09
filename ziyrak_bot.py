import os
import random
import logging
import requests
from flask import Flask, request

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHANNEL = "@Inferiq"

# Faqat shu ID uchun ishlaydi
VALID_ID = "1695385923"


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

def check_subscription(user_id):
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getChatMember",
            params={"chat_id": CHANNEL, "user_id": user_id},
            timeout=10
        )
        data = r.json()
        if data.get("ok"):
            status = data["result"]["status"]
            return status in ["member", "administrator", "creator"]
        return False
    except Exception:
        return False

def send_subscribe_message(chat_id):
    send_message(chat_id,
        "⚠️ <b>Botdan foydalanish uchun kanalga obuna bo'ling!</b>\n\n"
        f"📢 Kanal: {CHANNEL}\n\n"
        "Obuna bo'lgandan so'ng /start bosing ✅",
        reply_markup={
            "inline_keyboard": [[
                {"text": f"📢 {CHANNEL} ga obuna bo'lish", "url": "https://t.me/Inferiq"}
            ], [
                {"text": "✅ Obuna bo'ldim", "callback_data": "check_sub"}
            ]]
        }
    )

def main_menu():
    return {
        "keyboard": [
            [{"text": "🚀 Signal Olish"}],
            [{"text": "❓ Yordam"}]
        ],
        "resize_keyboard": True
    }

def id_menu():
    return {
        "keyboard": [
            [{"text": "⬅️ Orqaga"}]
        ],
        "resize_keyboard": True
    }

def get_signal():
    """Tasodifiy signal yaratish"""
    number = random.randint(1, 5)
    emojis = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣"}
    return number, emojis[number]

waiting_for_id = {}

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.json
    if not update:
        return "ok"

    # Callback query
    if "callback_query" in update:
        cb = update["callback_query"]
        chat_id = cb["message"]["chat"]["id"]
        user_id = cb["from"]["id"]
        callback_id = cb["id"]

        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery",
            json={"callback_query_id": callback_id}
        )

        if cb["data"] == "check_sub":
            if check_subscription(user_id):
                send_message(chat_id,
                    "✅ Rahmat! Endi botdan foydalanishingiz mumkin.",
                    reply_markup=main_menu()
                )
            else:
                send_message(chat_id,
                    f"❌ Siz hali {CHANNEL} kanaliga obuna bo'lmadingiz!",
                    reply_markup={
                        "inline_keyboard": [[
                            {"text": f"📢 {CHANNEL} ga obuna bo'lish", "url": "https://t.me/Inferiq"}
                        ], [
                            {"text": "✅ Obuna bo'ldim", "callback_data": "check_sub"}
                        ]]
                    }
                )
        return "ok"

    message = update.get("message")
    if not message:
        return "ok"

    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    text = message.get("text", "").strip()

    if not text:
        return "ok"

    # Obuna tekshirish
    if not check_subscription(user_id):
        send_subscribe_message(chat_id)
        return "ok"

    # /start
    if text == "/start":
        waiting_for_id[chat_id] = False
        send_message(chat_id,
            "🍎 <b>WinWin Signal Bot</b>\n\n"
            "Signal olish uchun tugmani bosing!\n\n"
            "<i>Inferiq jamoasi tomonidan yaratilgan</i>",
            reply_markup=main_menu()
        )
        return "ok"

    # Signal olish tugmasi
    if text == "🚀 Signal Olish":
        waiting_for_id[chat_id] = True
        send_message(chat_id,
            "🔐 <b>WinWin ID ni kiriting:</b>\n\n"
            "Hisob raqamingizni yozing",
            reply_markup=id_menu()
        )
        return "ok"

    # Orqaga
    if text == "⬅️ Orqaga":
        waiting_for_id[chat_id] = False
        send_message(chat_id, "🏠 Bosh menyu", reply_markup=main_menu())
        return "ok"

    # Yordam
    if text in ["❓ Yordam", "/help"]:
        send_message(chat_id,
            "📖 <b>Yordam</b>\n\n"
            "1. 🚀 Signal Olish tugmasini bosing\n"
            "2. WinWin ID ingizni kiriting\n"
            "3. Signal oling!\n\n"
            f"📢 Kanal: {CHANNEL}",
            reply_markup=main_menu()
        )
        return "ok"

    # ID tekshirish
    if waiting_for_id.get(chat_id):
        entered_id = text.strip()

        # Format tekshirish — faqat raqam va 10 xona
        if not entered_id.isdigit():
            send_message(chat_id,
                "❌ <b>Noto'g'ri ID!</b>\n\n"
                "ID faqat raqamlardan iborat bo'lishi kerak.\n"
                "Qayta kiriting:",
                reply_markup=id_menu()
            )
            return "ok"

        if len(entered_id) != 10:
            send_message(chat_id,
                f"❌ <b>Noto'g'ri ID!</b>\n\n"
                f"ID 10 ta raqamdan iborat bo'lishi kerak.\n"
                f"Siz {len(entered_id)} ta raqam kiritdingiz.\n\n"
                "Qayta kiriting:",
                reply_markup=id_menu()
            )
            return "ok"

        # ID tekshirish
        if entered_id != VALID_ID:
            send_message(chat_id,
                "❌ <b>Xato ID!</b>\n\n"
                "Bu ID WinWin da topilmadi.\n"
                "ID ni tekshirib qayta kiriting:",
                reply_markup=id_menu()
            )
            return "ok"

        # To'g'ri ID — signal berish
        waiting_for_id[chat_id] = False
        send_typing(chat_id)

        number, emoji = get_signal()

        send_message(chat_id,
            f"✅ <b>ID tasdiqlandi!</b>\n\n"
            f"━━━━━━━━━━━━━━\n"
            f"🎯 <b>Signal:</b>\n\n"
            f"{emoji} - Kattakni tanlang ✅\n"
            f"━━━━━━━━━━━━━━\n\n"
            f"🍀 Omad!",
            reply_markup=main_menu()
        )
        return "ok"

    # Boshqa xabarlar
    send_message(chat_id,
        "🚀 Signal olish uchun tugmani bosing!",
        reply_markup=main_menu()
    )
    return "ok"


@app.route("/")
def index():
    return "WinWin Signal Bot — Inferiq ✅"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
            
