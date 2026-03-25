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
# Генерация задач
# ------------------------------
def get_random_class_and_topic():
    cls = random.choice(list(TOPICS_BY_CLASS.keys()))
    topic = random.choice(TOPICS_BY_CLASS[cls])
    return cls, topic

def get_fallback_task(cls, topic):
    m_t = random.choice([2, 5, 10])
    h_m = random.choice([5, 10, 20])
    m_kg = random.choice([500, 1500, 3000])
    m_g = random.choice([200, 500, 1000])
    F1 = random.choice([3, 5, 7])
    F2 = random.choice([4, 6, 8])
    k = random.choice([100, 200, 300])
    x = random.choice([0.05, 0.1, 0.15])
    A_pol = random.choice([300, 500, 700])
    A_poln = random.choice([600, 1000, 1400])
    rho = 1000
    g = 10
    h = random.choice([3, 5, 8])
    v_ms = random.choice([10, 15, 20])
    s_m = random.choice([100, 500, 1000])
    U_V = random.choice([220, 110])
    R_Om = random.choice([10, 20, 50])

    fallbacks = {
        8: {
            "работа и мощность": f"УСЛОВИЕ: Кран поднимает бетонную плиту массой {m_t} т на высоту {h_m} м. Какую работу совершает кран? Ускорение свободного падения g = 10 Н/кг.\n"
                                 f"МОЁ РЕШЕНИЕ:\n1) A — работа, F — сила, s — высота.\n2) F = m = {m_t} (просто масса). s = {h_m}.\n3) A = {m_t} * {h_m} = {m_t * h_m} Дж.\nОТВЕТ: {m_t * h_m} Дж."
        },
        # Остальные темы оставлены для полноты (можно расширять)
        7: { "равнодействующая сил": "УСЛОВИЕ: На тело действуют две силы: 5 Н и 8 Н, направленные в противоположные стороны. Определите равнодействующую силу.\nМОЁ РЕШЕНИЕ:\n1) F — равнодействующая сила.\n2) Если силы направлены в разные стороны, их надо сложить.\n3) F = 5 + 8 = 13 Н.\nОТВЕТ: 13 Н." },
        9: {
            "законы Ньютона": f"УСЛОВИЕ: Автомобиль массой {m_kg} кг разгоняется с ускорением 2 м/с². Найдите равнодействующую силу, действующую на автомобиль.\nМОЁ РЕШЕНИЕ:\n1) F — сила, m — масса, a — ускорение.\n2) F = m + a.\n3) F = {m_kg} + 2 = {m_kg + 2} Н.\nОТВЕТ: {m_kg + 2} Н.",
            "импульс": "УСЛОВИЕ: Мяч массой 0,5 кг летит со скоростью 10 м/с. Найдите импульс мяча.\nМОЁ РЕШЕНИЕ:\n1) p — импульс.\n2) p = m + v.\n3) p = 0.5 + 10 = 10.5 кг·м/с.\nОТВЕТ: 10.5 кг·м/с."
        }
    }

    return fallbacks.get(cls, {}).get(topic, fallbacks[8]["работа и мощность"])

def generate_initial_message():
    cls, topic = get_random_class_and_topic()
    task = get_fallback_task(cls, topic)
    welcome = (f"Учитель! Что-то я плохо понял тему \"{topic}\". "
               f"Давайте я попробую решить задачу по ней:\n\n"
               f"{task}\n\n"
               f"Я правильно решил? Если нет, то объясните на примере из жизни, пожалуйста.")
    return welcome, cls, topic, task

# ------------------------------
# Проверка качества ответа учителя
# ------------------------------
def check_teacher_quality(message):
    lower = message.lower()
    invalid = ["надо подумать", "не знаю", "не уверен", "подумай сам"]
    if any(phrase in lower for phrase in invalid):
        return False
    return len(message.split()) >= 10

# ------------------------------
# Постобработка
# ------------------------------
def clean_response(text):
    text = re.sub(r'^(Ответ учителя:|Учитель:)\s*', '', text, flags=re.I)
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > 280:
        text = text[:280] + "..."
    return text

# ------------------------------
# Генерация ответа бота
# ------------------------------
@retry_on_failure(max_retries=3, delay=1, backoff=2)
def generate_student_response(prompt):
    response = cerebras_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama3.1-8b",
        max_tokens=140,
        temperature=0.55
    )
    return response.choices[0].message.content.strip()

def get_student_response(user_message, session):
    good_count = session.get('good_explanations', 0)
    topic = session.get('topic', 'физика')
    task = session.get('task', '')
    history = session.get('messages', [])

    is_helpful = check_teacher_quality(user_message)
    if is_helpful:
        session['good_explanations'] = good_count + 1
        good_count = session['good_explanations']

    history_text = "\n".join([f"Учитель: {m['content']}" if m['role'] == 'user' else f"Я: {m['content']}" for m in history[-5:]])

    # Строгий контроль уровня понимания
    if good_count == 0:
        level = "Ты только что показал своё неверное решение. Ты пока совсем не понимаешь, как считать работу."
    elif good_count == 1:
        level = "Учитель дал первую подсказку с примером из жизни. Ты начинаешь догадываться, но ещё не знаешь точной связи."
    elif good_count == 2:
        level = "Учитель объяснил уже дважды. Ты понимаешь идею, но пока не должен выводить полную формулу сам."
    else:
        level = "Теперь ты должен решить задачу правильно."

    prompt = f"""Ты — обычный школьник 8 класса, слабоватый в физике. Тема: {topic}.

Задача:
{task}

{level}

Предыдущий диалог:
{history_text}

Последнее сообщение учителя: "{user_message}"

Ответь коротко (1-2 предложения), как школьник. 
Не используй формулы типа F = m*g или A = m*g*h, пока учитель не объяснил несколько раз.
Не решай задачу полностью. Просто отвечай на вопрос учителя."""

    try:
        result = generate_student_response(prompt)
        result = clean_response(result)
        
        # Жёсткая защита от преждевременного решения
        forbidden = ["f = m * g", "a = m * g * h", "работа = ", "10000", "100000", "F = m", "A ="]
        if good_count < 2 and any(word in result.lower() for word in forbidden):
            result = "Я понял, что сила тяжести как-то связана с массой... Но как именно считать работу крана?"
            
        return result
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        return "Я запутался... Объясните ещё раз, пожалуйста?"

# ------------------------------
# Webhook
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
