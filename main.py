import os
import random
import logging
import requests
import re
from functools import wraps
from flask import Flask, request, jsonify
from cerebras.cloud.sdk import Cerebras

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CEREBRAS_API_KEY = os.environ.get('CEREBRAS_API_KEY')

if not TELEGRAM_TOKEN or not CEREBRAS_API_KEY:
    raise ValueError("Токены не установлены")

cerebras_client = Cerebras(api_key=CEREBRAS_API_KEY)

# ------------------------------
# Декоратор
# ------------------------------
def retry_on_failure(max_retries=3, delay=1, backoff=2):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.warning(f"Попытка {attempt+1} не удалась: {e}")
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(current_delay)
                    current_delay *= backoff
            return "Я не понял. Можете объяснить ещё раз?"
        return wrapper
    return decorator

# ------------------------------
# Данные
# ------------------------------
TOPICS_BY_CLASS = {
    7: ["равнодействующая сил", "сила упругости", "коэффициент полезного действия", "гидростатическое давление", "плотность", "сила тяжести", "давление"],
    8: ["работа и мощность", "простые механизмы", "энергия", "теплопроводность"],
    9: ["законы Ньютона", "движение", "импульс", "архимедова сила", "ток"],
    10: ["законы Кеплера", "движение по окружности", "тяготение", "работа"],
    11: ["молекулярно-кинетическая теория", "термодинамика", "электрическое поле", "магнитное поле", "колебания"]
}

user_sessions = {}

# ------------------------------
# Генерация задач — теперь строго по теме!
# ------------------------------
def get_random_class_and_topic():
    cls = random.choice(list(TOPICS_BY_CLASS.keys()))
    topic = random.choice(TOPICS_BY_CLASS[cls])
    return cls, topic

def get_fallback_task(cls, topic):
    # Случайные значения
    m = random.choice([100, 500, 1000, 2000])
    h = random.choice([5, 10, 20])
    g = 10
    Q = random.choice([800, 1200, 1500, 2000])
    A = random.choice([200, 300, 500, 600])
    F1 = random.choice([3, 5, 7])
    F2 = random.choice([4, 6, 8])

    tasks = {
        # Тема "работа" (механическая работа)
        "работа": f"УСЛОВИЕ: Груз массой {m} кг поднимают равномерно на высоту {h} м. Какую работу совершает сила тяжести? g = 10 Н/кг.\n"
                  f"МОЁ РЕШЕНИЕ:\n1) A — работа.\n2) A = m * h.\n3) A = {m} * {h} = {m*h} Дж.\nОТВЕТ: {m*h} Дж.",

        # Тема "тяготение"
        "тяготение": f"УСЛОВИЕ: Два тела массами 2 кг и 3 кг находятся на расстоянии 0,5 м друг от друга. Найдите силу гравитационного притяжения между ними. G = 6,67·10^{-11} Н·м²/кг².\n"
                     f"МОЁ РЕШЕНИЕ:\n1) F — сила притяжения.\n2) F = G * m1 * m2.\n3) F = 6,67e-11 * 2 * 3 = очень маленькое число.\nОТВЕТ: очень маленькое число.",

        # Тема "термодинамика"
        "термодинамика": f"УСЛОВИЕ: Газ совершил работу {A} Дж, получив от нагревателя {Q} Дж теплоты. Найдите изменение внутренней энергии газа.\n"
                         f"МОЁ РЕШЕНИЕ:\n1) ΔU — изменение внутренней энергии.\n2) ΔU = A + Q.\n3) ΔU = {A} + {Q} = {A+Q} Дж.\nОТВЕТ: {A+Q} Дж.",

        # Остальные темы (примеры)
        "равнодействующая сил": f"УСЛОВИЕ: На тело действуют две силы: {F1} Н и {F2} Н в противоположные стороны. Определите равнодействующую силу.\n"
                                f"МОЁ РЕШЕНИЕ:\n1) F — равнодействующая.\n2) F = F1 + F2.\n3) F = {F1} + {F2} = {F1+F2} Н.\nОТВЕТ: {F1+F2} Н.",
        
        "архимедова сила": f"УСЛОВИЕ: Тело объёмом 0,2 м³ полностью погружено в воду. Определите силу Архимеда. ρ воды = 1000 кг/м³, g = 10 м/с².\n"
                           f"МОЁ РЕШЕНИЕ:\n1) Fa — сила Архимеда.\n2) Fa = ρ * V.\n3) Fa = 1000 * 0.2 = 200 Н.\nОТВЕТ: 200 Н.",
    }

    return tasks.get(topic, tasks["термодинамика"])

def generate_initial_message():
    cls, topic = get_random_class_and_topic()
    task = get_fallback_task(cls, topic)
    welcome = (f"Учитель! Что-то я плохо понял тему \"{topic}\". "
               f"Давайте я попробую решить задачу по ней:\n\n"
               f"{task}\n\n"
               f"Я правильно решил? Если нет, то объясните на примере из жизни, пожалуйста.")
    return welcome, cls, topic, task

# ------------------------------
# Остальной код (проверка, ответ бота, webhook) — без изменений из предыдущей рабочей версии
# ------------------------------
def check_teacher_quality(message):
    lower = message.lower()
    if any(x in lower for x in ["надо подумать", "не знаю", "подумай сам", "не уверен"]):
        return False
    return len(message.split()) >= 10

def clean_response(text):
    text = re.sub(r'^(Ответ учителя:|Учитель:)\s*', '', text, flags=re.I)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:260] + "..." if len(text) > 260 else text

@retry_on_failure(max_retries=3, delay=1, backoff=2)
def generate_student_response(prompt):
    resp = cerebras_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama3.1-8b",
        max_tokens=130,
        temperature=0.52
    )
    return resp.choices[0].message.content.strip()

def get_student_response(user_message, session):
    good_count = session.get('good_explanations', 0)
    topic = session.get('topic', 'физика')
    task = session.get('task', '')
    history = session.get('messages', [])

    if check_teacher_quality(user_message):
        session['good_explanations'] = good_count + 1
        good_count = session['good_explanations']

    history_text = "\n".join([f"Учитель: {m['content']}" if m['role'] == 'user' else f"Я: {m['content']}" for m in history[-6:]])

    level = {
        0: "Ты только что показал неверное решение. Ты пока совсем не понимаешь тему.",
        1: "Учитель дал первую подсказку с примером. Ты начинаешь догадываться.",
        2: "Учитель объяснил дважды. Ты понимаешь смысл, но пока не должен писать формулы.",
    }.get(good_count, "Теперь ты должен решить правильно.")

    prompt = f"""Ты — слабый школьник 9 класса. Тема: {topic}.

Задача:
{task}

{level}

Диалог:
{history_text}

Учитель сказал: "{user_message}"

Отвечай коротко (1-2 предложения). НЕ пиши формулы и НЕ решай задачу полностью, если учитель объяснил меньше 3 раз."""

    try:
        result = generate_student_response(prompt)
        return clean_response(result)
    except:
        return "Я запутался... Объясните ещё раз, пожалуйста?"

# ------------------------------
# Flask
# ------------------------------
@app.route('/')
def index():
    return "OK"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({"status": "ok"})

        msg = data['message']
        if 'text' not in msg:
            return jsonify({"status": "ok"})

        user_msg = msg['text'].strip()
        chat_id = msg['chat']['id']

        if user_msg == '/start':
            welcome, cls, topic, task = generate_initial_message()
            user_sessions[chat_id] = {
                'class': cls,
                'topic': topic,
                'task': task,
                'messages': [],
                'good_explanations': 0
            }
            send_message(chat_id, welcome)
            return jsonify({"status": "ok"})

        session = user_sessions.get(chat_id)
        if not session:
            welcome, cls, topic, task = generate_initial_message()
            user_sessions[chat_id] = {
                'class': cls,
                'topic': topic,
                'task': task,
                'messages': [],
                'good_explanations': 0
            }
            send_message(chat_id, welcome)
            return jsonify({"status": "ok"})

        response = get_student_response(user_msg, session)

        session['messages'].append({'role': 'user', 'content': user_msg})
        session['messages'].append({'role': 'assistant', 'content': response})

        send_message(chat_id, response)
        return jsonify({"status": "ok"})

    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"status": "error"}), 500

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={'chat_id': chat_id, 'text': text}, timeout=10)
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
