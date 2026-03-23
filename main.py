import os
import requests
from flask import Flask, request

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


# =========================
# Отправка сообщения
# =========================
def send_message(chat_id, text):
    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    requests.post(url, json=payload)


# =========================
# Health check (Render)
# =========================
@app.route("/health", methods=["GET"])
def health():
    return "ok"


# =========================
# Webhook
# =========================
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        print("Incoming webhook JSON:", data)

        # Если нет message — игнорируем
        if not data or "message" not in data:
            return "ok"

        message = data["message"]

        chat_id = message["chat"]["id"]

        # ✅ ПРАВИЛЬНОЕ получение текста
        user_msg = message.get("text", "")

        if not isinstance(user_msg, str):
            user_msg = ""

        user_msg = user_msg.strip()

        print("User message:", user_msg)

        # =========================
        # Логика бота
        # =========================

        if user_msg == "/start":
            reply = (
                "Учитель! Что-то я плохо понял тему скорость. "
                "Давайте я попробую решить задачу по ней:\n\n"
                "Автомобиль проехал 100 км за 2 часа. "
                "Я думаю скорость = 100 / 2 = 50 км/ч.\n"
                "Но вроде надо ещё умножить на 2, значит 100 км/ч.\n\n"
                "Я правильно решил?"
            )
        else:
            reply = "Я получил сообщение: " + user_msg

        send_message(chat_id, reply)

        return "ok"

    except Exception as e:
        print("ERROR:", e)
        return "error", 500


# =========================
# Запуск
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
