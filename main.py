from flask import Flask, request, jsonify
from utils import choose_task, wrong_solution
import os
import requests

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


# -----------------------------
# Отправка сообщения в Telegram
# -----------------------------
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print("Ошибка отправки:", e)


# -----------------------------
# Health check (Render)
# -----------------------------
@app.route("/health")
def health():
    return "OK", 200


# -----------------------------
# Root (чтобы не было пусто)
# -----------------------------
@app.route("/")
def index():
    return "Bot is running", 200


# -----------------------------
# Webhook
# -----------------------------
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json()
        print("Incoming webhook JSON:", data)

        # Проверка структуры
        if not data or "message" not in data:
            return "ok"

        message = data["message"]

        # chat_id
        chat_id = message["chat"]["id"]

        # текст сообщения (ВАЖНО!)
        user_msg = message.get("text", "")

        # если вдруг не текст (например, стикер)
        if not isinstance(user_msg, str):
            user_msg = ""

        user_msg = user_msg.strip()

        # лог
        print("User message:", user_msg)

        # ответ бота (пока тест)
        if user_msg == "/start":
            reply = "Бот работает"
        else:
            reply = "Я получил сообщение: " + user_msg

        send_message(chat_id, reply)

        return "ok"

    except Exception as e:
        print("ERROR:", e)
        return "error", 500

        # -----------------------------
        # /start
        # -----------------------------
        if user_text.startswith("/start"):
            grade, topic, task_text, params = choose_task()
            solution = wrong_solution(grade, topic, params)

            reply = (
                f"Учитель! Что-то я плохо понял тему {topic}. "
                f"Давайте я попробую решить задачу по ней:\n\n"
                f"{task_text}\n\n"
                f"{solution}\n\n"
                f"Я правильно решил?"
            )

        # -----------------------------
        # Любой другой текст
        # -----------------------------
        else:
            grade, topic, task_text, params = choose_task()
            solution = wrong_solution(grade, topic, params)

            reply = (
                f"Я попробовал ещё раз:\n\n"
                f"{task_text}\n\n"
                f"{solution}\n\n"
                f"Я правильно решил?"
            )

        # ✅ Отправка в Telegram
        send_message(chat_id, reply)

        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print("🔥 ERROR:", e)
        return str(e), 500


# -----------------------------
# Запуск
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print("🚀 APP STARTING...")
    app.run(host="0.0.0.0", port=port)
