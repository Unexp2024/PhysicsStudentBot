import os
import random
from flask import Flask, request, jsonify

app = Flask(__name__)

# -------------------------
# Состояние пользователя
# -------------------------
user_state = {}

# -------------------------
# Генерация задач
# -------------------------
PHYSICS_TOPICS = [
    "Движение точки", "Сила тяжести", "Электрическое поле",
    "Ток", "Плотность", "Архимедова сила"
]

TASK_TEMPLATES = [
    "Маленький груз весом {mass} кг под действием силы тяжести движется по горизонтальной плоскости со скоростью {v0} м/с. Если сила трения равна {f} Н, а коэффициент трения {mu}, то какая скорость груза будет в конце {t} секунд?",
    "Объект массой {mass} кг падает с высоты {h} м. Определите скорость при падении.",
    "Мяч бросают под углом {angle}° с начальной скоростью {v0} м/с. Найдите расстояние по горизонтали до удара о землю."
]

def generate_task():
    topic = random.choice(PHYSICS_TOPICS)
    template = random.choice(TASK_TEMPLATES)
    task_text = template.format(
        mass=random.randint(1, 20),
        v0=random.randint(1, 20),
        f=random.randint(5, 15),
        mu=round(random.uniform(0.1, 0.5), 2),
        t=random.randint(1,5),
        h=random.randint(5,30),
        angle=random.choice([30,45,60])
    )
    return topic, task_text

# -------------------------
# Проверка ответа пользователя
# -------------------------
def evaluate_student_response(user_msg, state):
    if not user_msg.strip():
        return False
    topic_keywords = state.get("topic", "").lower().split()
    if any(k in user_msg.lower() for k in topic_keywords):
        return True
    math_terms = ["v=", "скорость", "масса", "сила", "ускорение", "t=", "расстояние", "градусов", "Н"]
    if any(term in user_msg for term in math_terms):
        return True
    return False

# -------------------------
# Маршруты
# -------------------------
@app.route("/")
def home():
    return "OK"

@app.route("/health")
def health():
    return "healthy", 200

@app.route("/start", methods=["POST"])
def start():
    user_id = request.json.get("user_id", "anon")
    topic, task_text = generate_task()
    user_state[user_id] = {"topic": topic, "task": task_text, "step": 1}
    
    message = (
        f"Учитель! Я плохо понял тему \"{topic}\".\n\n"
        f"Я тут решил задачу:\n\n{task_text}\n\n"
        "РЕШЕНИЕ УЧЕНИКА:\n"
        "Я попытался решить эту задачу, но не уверен в результате. Я правильно решил?"
    )
    return jsonify({"bot_message": message})

@app.route("/webhook", methods=["POST"])
def webhook():
    user_id = request.json.get("user_id", "anon")
    user_msg = request.json.get("message", "")
    state = user_state.get(user_id)
    
    if not state:
        return jsonify({"bot_message": "Сначала нажмите 'Старт'."})
    
    success = evaluate_student_response(user_msg, state)
    feedback = "👍 Отлично, Вы направляете ученика к пониманию!" if success else "⚠️ Попробуйте ответить более по теме задачи."
    
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

# -------------------------
# Локальный запуск (dev)
# -------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
