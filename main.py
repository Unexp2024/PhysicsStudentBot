import os
import json
import random
import logging
import requests
import re
import time
from functools import wraps
from flask import Flask, request, jsonify
from cerebras.cloud.sdk import Cerebras

# ------------------------------
# Конфигурация
# ------------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
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
# Генерация задач (теперь задачи соответствуют теме!)
# ------------------------------
def get_random_class_and_topic():
    cls = random.choice(list(TOPICS_BY_CLASS.keys()))
    topic = random.choice(TOPICS_BY_CLASS[cls])
    return cls, topic

def get_fallback_task(cls, topic):
    # Общие случайные значения
    m_kg = random.choice([0.5, 1, 2, 5])
    delta_t = random.choice([20, 40, 60, 80])
    c_water = 4200
    Q_given = random.choice([500, 800, 1200])
    A_given = random.choice([200, 300, 500])

    fallbacks = {
        8: {
            "работа и мощность": f"УСЛОВИЕ: Кран поднимает бетонную плиту массой 2 т на высоту 10 м. Какую работу совершает кран? Ускорение свободного падения g = 10 Н/кг.\nМОЁ РЕШЕНИЕ:\n1) A — работа, F — сила, s — высота.\n2) F = m = 2 (просто масса). s = 10.\n3) A = 2 * 10 = 20 Дж.\nОТВЕТ: 20 Дж."
        },
        11: {
            "термодинамика": f"УСЛОВИЕ: Газ совершил работу {A_given} Дж, получив от нагревателя {Q_given} Дж теплоты. Найдите изменение внутренней энергии газа.\nМОЁ РЕШЕНИЕ:\n1) ΔU — изменение внутренней энергии, A — работа, Q — теплота.\n2) ΔU = A + Q.\n3) ΔU = {A_given} + {Q_given} = {A_given + Q_given} Дж.\nОТВЕТ: {A_given + Q_given} Дж."
        },
        7: {
            "плотность": f"УСЛОВИЕ: Металлическая деталь имеет массу 800 г и объём 200 см³. Определите плотность металла.\nМОЁ РЕШЕНИЕ:\n1) ρ — плотность, m — масса, V — объём.\n2) ρ = m + V.\n3) ρ = 800 + 200 = 1000 г/см³.\nОТВЕТ: 1000 г/см³."
        }
    }

    # Возвращаем задачу по теме, если есть, иначе дефолтную
    return fallbacks.get(cls, {}).get(topic, fallbacks[11]["термодинамика"])

def generate_initial_message():
    cls, topic = get_random_class_and_topic()
    task = get_fallback_task(cls, topic)
    welcome = (f"Учитель! Что-то я плохо понял тему \"{topic}\". "
               f"Давайте я попробую решить задачу по ней:\n\n"
               f"{task}\n\n"
               f"Я правильно решил? Если нет, то объясните на примере из жизни, пожалуйста.")
    return welcome, cls, topic, task

# ------------------------------
# Проверка качества учителя
# ------------------------------
def check_teacher_quality(message):
    lower = message.lower()
    if any(word in lower for word in ["надо подумать", "не знаю", "подумай сам", "не уверен"]):
        return False
    return len(message.split()) >= 12

# ------------------------------
# Очистка ответа
# ------------------------------
def clean_response(text):
    text = re.sub(r'^(Ответ учителя:|Учитель:)\s*', '', text, flags=re.I)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > 250:
        text = text[:250] + "..."
    return text

# ------------------------------
# Ответ школьника
# ------------------------------
@retry_on_failure(max_retries=3, delay=1, backoff=2)
def generate_student_response(prompt):
    resp = cerebras_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama3.1-8b",
        max_tokens=130,
        temperature=0.5
    )
    return resp.choices[0].message.content.strip()

def get_student_response(user_message, session):
    good_count = session.get('good_explanations', 0)
    topic = session.get('topic', 'физика')
    task = session.get('task', '')
    history = session.get('messages', [])

    is_helpful = check_teacher_quality(user_message)
    if is_helpful:
        session['good_explanations'] = good_count + 1
        good_count = session['good_explanations']

    history_text = "\n".join([f"Учитель: {m['content']}" if m['role'] == 'user' else f"Я: {m['content']}" for m in history[-6:]])

    if good_count == 0:
        level = "Ты только что показал своё неверное решение. Ты пока совсем не понимаешь тему."
    elif good_count == 1:
        level = "Учитель дал первую подсказку с примером из жизни. Ты начинаешь догадываться, но пока не знаешь формулы."
    elif good_count == 2:
        level = "Учитель объяснил уже два раза. Ты понимаешь смысл, но ещё не должен выводить готовые формулы."
    else:
        level = "Теперь ты должен решить задачу правильно."

    prompt = f"""Ты — слабый ученик 8-9 класса по физике. Тема: {topic}.

Задача и твоё неверное решение:
{task}

Текущий уровень понимания:
{level}

Диалог:
{history_text}

Последнее сообщение учителя: "{user_message}"

Правила ответа:
- Отвечай коротко, 1-2 простых предложения.
- Говори как обычный школьник.
- НЕ используй формулы (типа ΔU = Q - A, A = mgh и т.д.), пока учитель не объяснил 3 раза.
- Не решай задачу полностью.
- Просто отвечай на вопрос учителя или проси уточнить."""

    try:
        result = generate_student_response(prompt)
        result = clean_response(result)
        
        # Дополнительная защита от раннего решения
        if good_count < 2 and any(kw in result.lower() for kw in ["формула", "δu =", "q - a", "работа =", "внутренняя энергия"]):
            result = "Я понял про тепло и работу... но как правильно посчитать изменение внутренней энергии?"
            
        return result
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
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
