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
    m = random.choice([100, 500, 1000])
    r = random.choice([6.4e6, 6.37e6])
    g = 10
    Q = random.choice([800, 1200, 2000])
    A = random.choice([200, 300, 500])

    tasks = {
        # 10 класс — тяготение
        "тяготение": f"УСЛОВИЕ: Масса Земли 6·10²⁴ кг, радиус 6400 км. Найдите ускорение свободного падения на поверхности Земли. G = 6,67·10⁻¹¹ Н·м²/кг².\n"
                     f"МОЁ РЕШЕНИЕ:\n1) g — ускорение свободного падения.\n2) g = G * M.\n3) g = 6,67e-11 * 6e24 = очень большое число.\nОТВЕТ: очень большое число.",

        # 11 класс — термодинамика
        "термодинамика": f"УСЛОВИЕ: Газ совершил работу {A} Дж, получив от нагревателя {Q} Дж теплоты. Найдите изменение внутренней энергии газа.\n"
                         f"МОЁ РЕШЕНИЕ:\n1) ΔU — изменение внутренней энергии, A — работа, Q — теплота.\n2) ΔU = A + Q.\n3) ΔU = {A} + {Q} = {A+Q} Дж.\nОТВЕТ: {A+Q} Дж.",

        # Остальные темы (можно расширять)
        "работа и мощность": f"УСЛОВИЕ: Кран поднимает бетонную плиту массой 2 т на высоту 10 м. Какую работу совершает кран? g = 10 Н/кг.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) A — работа.\n2) F = m = 2. s = 10.\n3) A = 2 * 10 = 20 Дж.\nОТВЕТ: 20 Дж.",
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
# Проверка учителя
# ------------------------------
def check_teacher_quality(message):
    lower = message.lower()
    bad = ["надо подумать", "не знаю", "подумай сам", "не уверен"]
    if any(x in lower for x in bad):
        return False
    return len(message.split()) >= 10

# ------------------------------
# Очистка
# ------------------------------
def clean_response(text):
    text = re.sub(r'^(Ответ учителя:|Учитель:)\s*', '', text, flags=re.I)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:260] + "..." if len(text) > 260 else text

# ------------------------------
# Ответ бота
# ------------------------------
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

    prompt = f"""Ты — слабый школьник 9-10 класса. Тема: {topic}.

Задача:
{task}

{level}

Диалог:
{history_text}

Учитель только что сказал: "{user_message}"

Отвечай коротко (1-2 предложения), как обычный школьник.
НЕ пиши формулы и НЕ решай задачу полностью, если учитель объяснил меньше 3 раз.
Просто отвечай на его вопрос или проси уточнить."""

    try:
        result = generate_student_response(prompt)
        result = clean_response(result)
        return result
    except:
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
