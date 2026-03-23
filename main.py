import os
import requests
from flask import Flask, request

print("=== NEW CODE VERSION 100 ===")

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def send_message(chat_id, text):
    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    requests.post(url, json=payload)


@app.route("/health", methods=["GET"])
def health():
    return "ok"


@app.route("/webhook", methods=["POST"])
def webhook():
    print("=== WEBHOOK HIT ===")

    data = request.get_json()
    print("DATA:", data)

    # Жёстко безопасный парсинг
    if not data:
        return "ok"

    message = data.get("message")
    if not message:
        return "ok"

    chat = message.get("chat", {})
    chat_id = chat.get("id")

    text = message.get("text")

    if not isinstance(text, str):
        text = ""

    user_msg = text.strip()

    print("USER_MSG:", user_msg)

    if user_msg == "/start":
        reply = "Бот жив. Новая версия работает."
    else:
        reply = f"Эхо: {user_msg}"

    if chat_id:
        send_message(chat_id, reply)

    return "ok"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
