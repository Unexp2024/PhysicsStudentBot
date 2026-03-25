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
# Генерация задач — по одной уникальной задаче на каждую тему
# ------------------------------
def get_random_class_and_topic():
    cls = random.choice(list(TOPICS_BY_CLASS.keys()))
    topic = random.choice(TOPICS_BY_CLASS[cls])
    return cls, topic

def get_fallback_task(cls, topic):
    # Случайные значения
    F1 = random.choice([3, 5, 7])
    F2 = random.choice([4, 6, 8])
    k = random.choice([100, 200, 300])
    x = random.choice([0.05, 0.1, 0.15])
    A_pol = random.choice([300, 500, 700])
    A_poln = random.choice([600, 1000, 1400])
    rho = 1000
    g = 10
    h = random.choice([3, 5, 8])
    m = random.choice([100, 500, 1000])
    m_t = random.choice([2, 5, 10])
    Q = random.choice([800, 1200, 1500, 2000])
    A = random.choice([200, 300, 500, 600])

    task_dict = {
        # 7 класс
        "равнодействующая сил": f"УСЛОВИЕ: На тело действуют две силы: {F1} Н и {F2} Н, направленные в противоположные стороны. Определите равнодействующую силу.\nМОЁ РЕШЕНИЕ:\n1) F — равнодействующая сила.\n2) Если силы направлены в разные стороны, их надо сложить.\n3) F = {F1} + {F2} = {F1+F2} Н.\nОТВЕТ: {F1+F2} Н.",
        "сила упругости": f"УСЛОВИЕ: Жёсткость пружины {k} Н/м, удлинение {x} м. Найдите силу упругости.\nМОЁ РЕШЕНИЕ:\n1) F — сила упругости.\n2) F = k / x.\n3) F = {k} / {x} = {round(k/x,1)} Н.\nОТВЕТ: {round(k/x,1)} Н.",
        "коэффициент полезного действия": f"УСЛОВИЕ: Полезная работа {A_pol} Дж, полная работа {A_poln} Дж. Найдите КПД механизма.\nМОЁ РЕШЕНИЕ:\n1) η — КПД.\n2) η = (Aполн / Aполез) * 100%.\n3) η = ({A_poln} / {A_pol}) * 100%.\nОТВЕТ: {round(A_poln/A_pol*100)}%.",
        "гидростатическое давление": f"УСЛОВИЕ: Вода плотностью 1000 кг/м³ на глубине {h} м. Определите гидростатическое давление. g = 10 Н/кг.\nМОЁ РЕШЕНИЕ:\n1) p — давление.\n2) p = ρ * h.\n3) p = 1000 * {h} = {1000*h} Па.\nОТВЕТ: {1000*h} Па.",
        "плотность": f"УСЛОВИЕ: Металлическая деталь имеет массу 800 г и объём 200 см³. Определите плотность металла.\nМОЁ РЕШЕНИЕ:\n1) ρ — плотность.\n2) ρ = m + V.\n3) ρ = 800 + 200 = 1000 г/см³.\nОТВЕТ: 1000 г/см³.",
        "сила тяжести": f"УСЛОВИЕ: Масса груза {m} кг. Определите силу тяжести. g = 10 Н/кг.\nМОЁ РЕШЕНИЕ:\n1) F — сила тяжести.\n2) F = m + g.\n3) F = {m} + 10 = {m+10} Н.\nОТВЕТ: {m+10} Н.",
        "давление": f"УСЛОВИЕ: Трактор массой {m_t*1000} кг, площадь гусениц {m_t*2} м². Определите давление на дорогу. g = 10 Н/кг.\nМОЁ РЕШЕНИЕ:\n1) p — давление.\n2) F = m*g, p = F/S.\n3) p = ({m_t*1000}*10) / ({m_t*2}) Па.\nОТВЕТ: большое число Па.",

        # 8 класс
        "работа и мощность": f"УСЛОВИЕ: Кран поднимает бетонную плиту массой {m_t} т на высоту {h} м. Какую работу совершает кран? g = 10 Н/кг.\nМОЁ РЕШЕНИЕ:\n1) A — работа.\n2) A = m * s.\n3) A = {m_t} * {h} = {m_t*h} Дж.\nОТВЕТ: {m_t*h} Дж.",
        "простые механизмы": f"УСЛОВИЕ: Рычаг поднимает груз 300 кг. Плечо груза 0,5 м, плечо рабочего 3 м. Какая сила нужна рабочему? g = 10 Н/кг.\nМОЁ РЕШЕНИЕ:\n1) F1 * l1 = F2 * l2.\n2) F1 = F2 * l1 / l2.\n3) F1 = 18000 Н.\nОТВЕТ: 18000 Н.",
        "энергия": f"УСЛОВИЕ: Тело массой 2 кг движется со скоростью 10 м/с. Найдите кинетическую энергию.\nМОЁ РЕШЕНИЕ:\n1) Ek — кинетическая энергия.\n2) Ek = m * v.\n3) Ek = 2 * 10 = 20 Дж.\nОТВЕТ: 20 Дж.",
        "теплопроводность": f"УСЛОВИЕ: Сколько теплоты нужно, чтобы нагреть 0,5 кг воды от 20°C до 100°C? c = 4200 Дж/(кг·°C).\nМОЁ РЕШЕНИЕ:\n1) Q — теплота.\n2) Q = c * m.\n3) Q = 4200 * 0,5 = 2100 Дж.\nОТВЕТ: 2100 Дж.",

        # 9 класс
        "законы Ньютона": f"УСЛОВИЕ: Автомобиль массой 1000 кг разгоняется с ускорением 2 м/с². Найдите равнодействующую силу.\nМОЁ РЕШЕНИЕ:\n1) F — сила.\n2) F = m + a.\n3) F = 1000 + 2 = 1002 Н.\nОТВЕТ: 1002 Н.",
        "движение": f"УСЛОВИЕ: Поезд тормозит с ускорением 0,5 м/с², начальная скорость 10 м/с. Какой путь до остановки?\nМОЁ РЕШЕНИЕ:\n1) S — путь.\n2) S = v / a.\n3) S = 10 / 0,5 = 20 м.\nОТВЕТ: 20 м.",
        "импульс": f"УСЛОВИЕ: Мяч массой 0,5 кг летит со скоростью 10 м/с. Найдите импульс мяча.\nМОЁ РЕШЕНИЕ:\n1) p — импульс.\n2) p = m + v.\n3) p = 0,5 + 10 = 10,5 кг·м/с.\nОТВЕТ: 10,5 кг·м/с.",
        "архимедова сила": f"УСЛОВИЕ: Тело объёмом 0,2 м³ полностью погружено в воду. Найдите силу Архимеда. ρ = 1000 кг/м³, g = 10 м/с².\nМОЁ РЕШЕНИЕ:\n1) Fa — сила Архимеда.\n2) Fa = ρ * V.\n3) Fa = 1000 * 0,2 = 200 Н.\nОТВЕТ: 200 Н.",
        "ток": f"УСЛОВИЕ: Лампа под напряжением 220 В, сила тока 0,5 А. Найдите сопротивление лампы.\nМОЁ РЕШЕНИЕ:\n1) R — сопротивление.\n2) R = U + I.\n3) R = 220 + 0,5 = 220,5 Ом.\nОТВЕТ: 220,5 Ом.",

        # 10 класс
        "тяготение": f"УСЛОВИЕ: Найдите силу притяжения между Землёй и человеком массой 70 кг на поверхности Земли. g = 10 Н/кг.\nМОЁ РЕШЕНИЕ:\n1) F = m * g.\n2) F = 70 * 10 = 700 Н.\nОТВЕТ: 700 Н.",
        "работа": f"УСЛОВИЕ: Груз массой 500 кг поднимают равномерно на высоту 8 м. Какую работу совершает сила тяги? g = 10 Н/кг.\nМОЁ РЕШЕНИЕ:\n1) A = F * s.\n2) A = 500 * 8 = 4000 Дж.\nОТВЕТ: 4000 Дж.",

        # 11 класс
        "термодинамика": f"УСЛОВИЕ: Газ совершил работу {A} Дж, получив от нагревателя {Q} Дж теплоты. Найдите изменение внутренней энергии газа.\nМОЁ РЕШЕНИЕ:\n1) ΔU — изменение внутренней энергии.\n2) ΔU = A + Q.\n3) ΔU = {A} + {Q} = {A+Q} Дж.\nОТВЕТ: {A+Q} Дж.",
        "электрическое поле": f"УСЛОВИЕ: Между пластинами конденсатора напряжение 100 В, расстояние 2 мм. Найдите напряжённость поля.\nМОЁ РЕШЕНИЕ:\n1) E = U / d.\n2) E = 100 / 0,002 = 50000 В/м.\nОТВЕТ: 50000 В/м.",
        "колебания": f"УСЛОВИЕ: Маятник длиной 1 м. Найдите период колебаний. g = 10 м/с².\nМОЁ РЕШЕНИЕ:\n1) T = 2π √l.\n2) T = 2 * 3,14 * 1 ≈ 6,28 с.\nОТВЕТ: 6,28 с.",
    }

    return task_dict.get(topic, f"УСЛОВИЕ: Задача по теме {topic}.\nМОЁ РЕШЕНИЕ:\n1) ...\nОТВЕТ: ...")

def generate_initial_message():
    cls, topic = get_random_class_and_topic()
    task = get_fallback_task(cls, topic)
    welcome = (f"Учитель! Что-то я плохо понял тему \"{topic}\". "
               f"Давайте я попробую решить задачу по ней:\n\n"
               f"{task}\n\n"
               f"Я правильно решил? Если нет, то объясните на примере из жизни, пожалуйста.")
    return welcome, cls, topic, task

# ------------------------------
# Проверка и ответ бота
# ------------------------------
def check_teacher_quality(message):
    lower = message.lower()
    if any(x in lower for x in ["надо подумать", "не знаю", "подумай сам", "не уверен"]):
        return False
    return len(message.split()) >= 8

def clean_response(text):
    text = re.sub(r'^(Ответ учителя:|Учитель:)\s*', '', text, flags=re.I)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:260] + "..." if len(text) > 260 else text

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

    if check_teacher_quality(user_message):
        session['good_explanations'] = good_count + 1
        good_count = session['good_explanations']

    history_text = "\n".join([f"Учитель: {m['content']}" if m['role'] == 'user' else f"Я: {m['content']}" for m in history[-6:]])

    level = {
        0: "Ты только что показал неверное решение. Ты пока совсем не понимаешь тему.",
        1: "Учитель дал первую подсказку с примером. Ты начинаешь догадываться.",
        2: "Учитель объяснил дважды. Пока не пиши готовые формулы.",
    }.get(good_count, "Теперь ты должен решить правильно.")

    prompt = f"""Ты — слабый школьник 9 класса. Тема: {topic}.

Задача:
{task}

{level}

Диалог:
{history_text}

Учитель сказал: "{user_message}"

Отвечай коротко (1-2 предложения). 
Обязательно отвечай на вопрос учителя.
НЕ пиши формулы и НЕ решай задачу полностью, если учитель объяснил меньше 3 раз."""

    try:
        result = generate_student_response(prompt)
        return clean_response(result)
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
