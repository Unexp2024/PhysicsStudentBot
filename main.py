from flask import Flask, request, jsonify
from utils import choose_task, wrong_solution
import os

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

@app.route("/health")
def health():
    return "OK", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if not data:
        return "No JSON", 400

    try:
        message = data.get("message") or data.get("edited_message")
        text = message.get("text", "") if message else ""
        chat_id = message["chat"]["id"] if message else None

        if text.startswith("/start"):
            grade, topic, task_text, params = choose_task()
            solution = wrong_solution(grade, topic, params)
            response_text = f"Учитель! Что-то я плохо понял тему {topic}. Давайте я попробую решить задачу по ней:\n{task_text}\n{solution}\nЯ правильно решил?"
        else:
            grade, topic, task_text, params = choose_task()
            solution = wrong_solution(grade, topic, params)
            response_text = f"Я думаю ещё раз:\n{task_text}\n{solution}\nЯ правильно решил?"

        return jsonify({"chat_id": chat_id, "text": response_text}), 200

    except Exception as e:
        print("Ошибка в webhook:", e)
        print("Incoming webhook JSON:", data)
        return str(e), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
