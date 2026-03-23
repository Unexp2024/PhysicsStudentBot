from flask import Flask, request, jsonify
import os

app = Flask(__name__)

user_state = {}

def evaluate_student_response(response_text, state):
    topic = state.get("topic", "").lower()
    return topic and topic.lower() in response_text.lower()

def generate_task():
    topic = "Движение точки"
    task_text = (
        "Маленький груз весом 2 кг движется по горизонтали со скоростью 5 м/с. "
        "Если сила трения 10 Н, а коэффициент трения 0,3, какая скорость через 2 секунды?"
    )
    return topic, task_text

@app.route("/")
def index():
    return "PhysicsStudentBot работает!"

@app.route("/health")
def health():
    return "OK", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.get_json(force=True)
    except Exception as e:
        print("Ошибка при разборе JSON:", e)
        return jsonify({"bot_message": "⚠️ Некорректный JSON"}), 400

    print("Incoming webhook JSON:", data)

    user_id = data.get("user_id", "anon")
    user_msg = data.get("message", "").strip()

    if user_id not in user_state:
        topic, task_text = generate_task()
        user_state[user_id] = {"topic": topic, "task": task_text, "step": 1}

    state = user_state[user_id]

    if not user_msg:
        return jsonify({"bot_message": "⚠️ Я не получил сообщение. Пожалуйста, введите текст."})

    success = evaluate_student_response(user_msg, state)
    feedback = "👍 Отлично, вы движетесь в правильном направлении!" if success else "⚠️ Попробуйте ответить более по теме задачи."

    if success:
        topic, task_text = generate_task()
        state["topic"] = topic
        state["task"] = task_text
        state["step"] += 1
        next_task = f"\n\nНовая задача:\n{task_text}\nРЕШЕНИЕ УЧЕНИКА: Я попытался решить..."
    else:
        next_task = ""

    bot_reply = f"{feedback}{next_task}"
    return jsonify({"bot_message": bot_reply})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"🚀 APP STARTING on port {port}...")
    app.run(host="0.0.0.0", port=port)
