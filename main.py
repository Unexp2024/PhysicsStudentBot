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
# Данные и генерация задач (оставлено как в последней рабочей версии)
# ------------------------------
TOPICS_BY_CLASS = {
    7: ["равнодействующая сил", "сила упругости", "коэффициент полезного действия", "гидростатическое давление", "плотность", "сила тяжести", "давление"],
    8: ["работа и мощность", "простые механизмы", "энергия", "теплопроводность"],
    9: ["законы Ньютона", "движение", "импульс", "архимедова сила", "ток"],
    10: ["законы Кеплера", "движение по окружности", "тяготение", "работа"],
    11: ["молекулярно-кинетическая теория", "термодинамика", "электрическое поле", "магнитное поле", "колебания"]
}

user_sessions = {}

def get_random_class_and_topic():
    cls = random.choice(list(TOPICS_BY_CLASS.keys()))
    topic = random.choice(TOPICS_BY_CLASS[cls])
    return cls, topic

def get_fallback_task(cls, topic):
    # Здесь можно оставить твою последнюю версию с полным task_dict
    # Для краткости использую минимальный рабочий вариант (замени на свой полный, если нужно)
    task_dict = {
        "электрическое поле": f"УСЛОВИЕ: Между пластинами конденсатора напряжение 100 В, расстояние 2 мм. Найдите напряжённость поля.\nМОЁ РЕШЕНИЕ:\n1) E = U / d.\n2) E = 100 / 0,002 = 50000 В/м.\nОТВЕТ: 50000 В/м.",
        "термодинамика": f"УСЛОВИЕ: Газ совершил работу 500 Дж, получив от нагревателя 1200 Дж теплоты. Найдите изменение внутренней энергии газа.\nМОЁ РЕШЕНИЕ:\n1) ΔU — изменение внутренней энергии.\n2) ΔU = A + Q.\n3) ΔU = 500 + 1200 = 1700 Дж.\nОТВЕТ: 1700 Дж.",
        # ... добавь остальные темы по аналогии
    }
    return task_dict.get(topic, "Задача по физике.")

def generate_initial_message():
    cls, topic = get_random_class_and_topic()
    task = get_fallback_task(cls, topic)
    welcome = (f"Учитель! Что-то я плохо понял тему \"{topic}\". "
               f"Давайте я попробую решить задачу по ней:\n\n"
               f"{task}\n\n"
               f"Я правильно решил? Если нет, то объясните на примере из жизни, пожалуйста.")
    return welcome, cls, topic, task

# ------------------------------
# Проверка и ответ бота (главное улучшение)
# ------------------------------
def check_teacher_quality(message):
    lower = message.lower()
    if any(x in lower for x in ["надо подумать", "не знаю", "подумай сам", "не уверен"]):
        return False
    return len(message.split()) >= 8

def clean_response(text):
    text = re.sub(r'^(Ответ учителя:|Учитель:)\s*', '', text, flags=re.I)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:280] + "..." if len(text) > 280 else text

@retry_on_failure(max_retries=3, delay=1, backoff=2)
def generate_student_response(prompt):
    resp = cerebras_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama3.1-8b",
        max_tokens=140,
        temperature=0.55
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

    # Уровень понимания — теперь более строгий
    if good_count == 0:
        level = "Ты только что показал своё неверное решение. Ты пока совсем не понимаешь тему и должен отвечать на вопросы учителя."
    elif good_count == 1:
        level = "Учитель дал первую подсказку с примером. Ты начинаешь понимать смысл, но ещё не знаешь точной формулы."
    elif good_count == 2:
        level = "Учитель объяснил два раза. Ты понимаешь идею, но пока отвечай общими словами, без формул."
    else:
        level = "Теперь ты можешь приближаться к правильному решению."

    prompt = f"""Ты — обычный школьник 9 класса, не очень сильный в физике. Тема: {topic}.

Задача и твоё решение:
{task}

Текущий уровень:
{level}

Предыдущий диалог:
{history_text}

Последнее сообщение учителя: "{user_message}"

Правила:
- Обязательно отвечай на вопрос учителя.
- Говори простыми словами, как школьник.
- На первых двух объяснениях учителя НЕ пиши формулы и НЕ решай задачу.
- Если учитель задал вопрос — ответь на него, даже если не уверен.
- Будь кратким (1-2 предложения)."""

    try:
        result = generate_student_response(prompt)
        return clean_response(result)
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        return "Я не совсем понял... Можете объяснить ещё раз?"

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
