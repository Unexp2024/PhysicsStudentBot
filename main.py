import os
import requests
from flask import Flask, request, jsonify

# ----------------------------
# Конфигурация
# ----------------------------
TOKEN = os.environ.get("TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

app = Flask(__name__)

# ----------------------------
# Health check (Render)
# ----------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/")
def home():
    return "Bot is running"

# ----------------------------
# Telegram send
# ----------------------------
def send_message(chat_id, text):
    url = f"{TELEGRAM_API}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    requests.post(url, json=payload)

# ----------------------------
# Генерация ответа (СТАБИЛЬНАЯ)
# ----------------------------
def generate_response(user_text):
    user_text = user_text.lower()

    # СТАРТ
    if user_text in ["/start", "start", "начать"]:
        return """Учитель! Что-то я плохо понял тему скорости.

Давайте я попробую решить задачу по ней:

Задача: Машина проехала 100 м за 5 секунд. Найти скорость.

Моё решение:
1. v = s + t
2. v = 100 + 5 = 105 м/с
3. Значит скорость 105 м/с

Ответ: 105 м/с

Я правильно решил?"""

    # Обычный ответ
    return "А можете объяснить это на простом примере из жизни?"

# ----------------------------
# Webhook
# ----------------------------
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()

    if not data:
        return jsonify({"ok": True})

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        user_text = data["message"].get("text", "")

        response = generate_response(user_text)
        send_message(chat_id, response)

    return jsonify({"ok": True})

# ----------------------------
# Run
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
