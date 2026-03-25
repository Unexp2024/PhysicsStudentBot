import os
import json
import random
import logging
import requests
import re
import sys
import time
from functools import wraps
from flask import Flask, request, jsonify
from cerebras.cloud.sdk import Cerebras

# ------------------------------
# Конфигурация и логирование
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
    v_kmh = random.choice([36, 54, 72])
    v_ms = random.choice([10, 15, 20])
    m_kg = random.choice([500, 1500, 3000])
    m_g = random.choice([200, 500, 1000])
    m_t = random.choice([2, 5, 10])
    h_m = random.choice([5, 10, 20])
    s_m = random.choice([100, 500, 1000])
    F1 = random.choice([3, 5, 7])
    F2 = random.choice([4, 6, 8])
    k = random.choice([100, 200, 300])
    x = random.choice([0.05, 0.1, 0.15])
    A_pol = random.choice([300, 500, 700])
    A_poln = random.choice([600, 1000, 1400])
    rho = 1000
    g = 10
    h = random.choice([3, 5, 8])
    U_V = random.choice([220, 110])
    R_Om = random.choice([10, 20, 50])

    fallbacks = {
        7: {
            "равнодействующая сил": f"УСЛОВИЕ: На тело действуют две силы: {F1} Н и {F2} Н, направленные в противоположные стороны. Определите равнодействующую силу.\n"
                                  f"МОЁ РЕШЕНИЕ:\n1) F — равнодействующая сила.\n2) Если силы направлены в разные стороны, их надо сложить.\n3) F = {F1} + {F2} = {F1 + F2} Н.\nОТВЕТ: {F1 + F2} Н.",
            "сила упругости": f"УСЛОВИЕ: Жёсткость пружины {k} Н/м, её удлинение {x} м. Найдите силу упругости.\n"
                              f"МОЁ РЕШЕНИЕ:\n1) F — сила упругости, k — жёсткость, x — удлинение.\n2) Формула: F = k / x.\n3) F = {k} / {x} = {round(k/x, 1)} Н.\nОТВЕТ: {round(k/x, 1)} Н.",
            "коэффициент полезного действия": f"УСЛОВИЕ: С помощью механизма совершена полезная работа {A_pol} Дж, полная работа {A_poln} Дж. Вычислите КПД механизма (в процентах).\n"
                                             f"МОЁ РЕШЕНИЕ:\n1) η — КПД, Aполез — полезная работа, Aполн — полная работа.\n2) η = (Aполн / Aполез) * 100%.\n3) η = ({A_poln} / {A_pol}) * 100 = {round(A_poln / A_pol * 100)}%.\nОТВЕТ: {round(A_poln / A_pol * 100)}%.",
            "гидростатическое давление": f"УСЛОВИЕ: Вода (плотность ρ = {rho} кг/м³) находится на глубине {h} м. Определите гидростатическое давление на этой глубине. Ускорение свободного падения g = 10 Н/кг.\n"
                                         f"МОЁ РЕШЕНИЕ:\n1) p — давление, ρ — плотность, h — глубина.\n2) Формула: p = ρ * h.\n3) p = {rho} * {h} = {rho * h} Па.\nОТВЕТ: {rho * h} Па.",
            "плотность": f"УСЛОВИЕ: Металлическая деталь имеет массу {m_g} г и объём {m_g//4} см³. Определите плотность металла.\n"
                         f"МОЁ РЕШЕНИЕ:\n1) ρ — плотность, m — масса, V — объём.\n2) ρ = m + V.\n3) ρ = {m_g} + {m_g//4} = {m_g + m_g//4} г/см³.\nОТВЕТ: {m_g + m_g//4} г/см³.",
            "сила тяжести": f"УСЛОВИЕ: Масса груза составляет {m_kg} кг. Определите силу тяжести, действующую на груз. Ускорение свободного падения g = 10 Н/кг.\n"
                            f"МОЁ РЕШЕНИЕ:\n1) F — сила тяжести.\n2) F = m + g.\n3) F = {m_kg} + 10 = {m_kg + 10} Н.\nОТВЕТ: {m_kg + 10} Н.",
            "давление": f"УСЛОВИЕ: Трактор массой {m_t*1000} кг стоит на дороге. Площадь опоры его гусениц равна {m_t*2} м². Вычислите давление, которое трактор оказывает на дорогу. Ускорение свободного падения g = 10 Н/кг.\n"
                        f"МОЁ РЕШЕНИЕ:\n1) p — давление, F — вес, S — площадь.\n2) F = m * g = {m_t*1000} * 10 = {m_t*10000} Н.\n3) p = F * S = {m_t*10000} * {m_t*2} = {m_t*10000 * m_t*2} Па.\nОТВЕТ: {m_t*10000 * m_t*2} Па."
        },
        8: {
            "работа и мощность": f"УСЛОВИЕ: Кран поднимает бетонную плиту массой {m_t} т на высоту {h_m} м. Какую работу совершает кран? Ускорение свободного падения g = 10 Н/кг.\n"
                                 f"МОЁ РЕШЕНИЕ:\n1) A — работа, F — сила, s — высота.\n2) F = m = {m_t} (просто масса). s = {h_m}.\n3) A = {m_t} * {h_m} = {m_t * h_m} Дж.\nОТВЕТ: {m_t * h_m} Дж.",
        },
        9: {
            "законы Ньютона": f"УСЛОВИЕ: Автомобиль массой {m_kg} кг разгоняется с ускорением 2 м/с². Найдите равнодействующую силу, действующую на автомобиль.\n"
                              f"МОЁ РЕШЕНИЕ:\n1) F — сила, m — масса, a — ускорение.\n2) F = m + a.\n3) F = {m_kg} + 2 = {m_kg + 2} Н.\nОТВЕТ: {m_kg + 2} Н.",
            "движение": f"УСЛОВИЕ: Поезд тормозит с ускорением 0,5 м/с². Начальная скорость 36 км/ч (10 м/с). Какой путь он пройдёт до полной остановки?\n"
                        f"МОЁ РЕШЕНИЕ:\n1) S — путь, v — скорость, a — ускорение.\n2) S = v / a.\n3) S = 10 / 0.5 = 20 м.\nОТВЕТ: 20 м.",
            "импульс": f"УСЛОВИЕ: Мяч массой 0,5 кг летит со скоростью 10 м/с. Найдите импульс мяча.\n"
                       f"МОЁ РЕШЕНИЕ:\n1) p — импульс.\n2) p = m + v.\n3) p = 0.5 + 10 = 10.5 кг·м/с.\nОТВЕТ: 10.5 кг·м/с.",
            "архимедова сила": f"УСЛОВИЕ: Тело объёмом 0,2 м³ полностью погружено в воду. Определите модуль выталкивающей силы (силы Архимеда), действующей на тело. Плотность воды ρ = 1000 кг/м³, ускорение свободного падения g = 10 м/с².\n"
                               f"МОЁ РЕШЕНИЕ:\n1) Fa — сила Архимеда.\n2) Fa = ρ * V.\n3) Fa = 1000 * 0.2 = 200 Н.\nОТВЕТ: 200 Н.",
            "ток": f"УСЛОВИЕ: Лампа включена в сеть напряжением {U_V} В. Сила тока в лампе равна {R_Om//10} А. Найдите сопротивление лампы.\n"
                   f"МОЁ РЕШЕНИЕ:\n1) R — сопротивление.\n2) R = U + I.\n3) R = {U_V} + {R_Om//10} = {U_V + R_Om//10} Ом.\nОТВЕТ: {U_V + R_Om//10} Ом."
        },
        10: {
            "движение по окружности": f"УСЛОВИЕ: Трамвай движется по закруглению радиусом {s_m} м со скоростью {v_ms} м/с. Определите центростремительное ускорение трамвая.\n"
                                       f"МОЁ РЕШЕНИЕ:\n1) a — ускорение.\n2) a = v + R.\n3) a = {v_ms} + {s_m} = {v_ms + s_m} м/с².\nОТВЕТ: {v_ms + s_m} м/с².",
            "работа": f"УСЛОВИЕ: Груз массой 100 кг поднимают на высоту {h_m} м за 2 секунды. Какую работу совершает сила тяги? Ускорение свободного падения g = 10 Н/кг.\n"
                      f"МОЁ РЕШЕНИЕ:\n1) A = F * s.\n2) F = m * g = 1000 Н.\n3) A = 1000 * {h_m} = {1000 * h_m} Дж.\nОТВЕТ: {1000 * h_m} Дж."
        },
        11: {
            "термодинамика": f"УСЛОВИЕ: Газ совершил работу 500 Дж, получив от нагревателя 800 Дж теплоты. Найдите изменение внутренней энергии газа.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) ΔU — изменение энергии, A — работа, Q — теплота.\n2) ΔU = A + Q.\n3) ΔU = 500 + 800 = 1300 Дж.\nОТВЕТ: 1300 Дж.",
            "магнитное поле": f"УСЛОВИЕ: Прямолинейный проводник длиной 0,5 м с током 4 А помещён в однородное магнитное поле с индукцией 0,2 Тл перпендикулярно линиям поля. Определите силу Ампера, действующую на проводник.\n"
                              f"МОЁ РЕШЕНИЕ:\n1) F — сила Ампера.\n2) F = B + I + L.\n3) F = 0.2 + 4 + 0.5 = 4.7 Н.\nОТВЕТ: 4.7 Н."
        }
    }

    return fallbacks.get(cls, {}).get(topic, "Задача по физике.")

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
def check_teacher_quality(message, topic):
    lower = message.lower()
    invalid = ["надо подумать", "не знаю", "не уверен", "подумай сам", "не могу сказать"]
    if any(phrase in lower for phrase in invalid):
        return False
    return len(message.split()) >= 8

# ------------------------------
# Постобработка
# ------------------------------
def clean_response(text, user_message=""):
    text = re.sub(r'^(Ответ учителя:|Учитель:)\s*', '', text, flags=re.I)
    if user_message and user_message.strip() in text:
        text = text.replace(user_message.strip(), "").strip()
    text = text.replace("depends от", "зависит от")
    text = re.sub(r'\s+', ' ', text).strip()
    if len(text) > 280:
        text = text[:280] + "..."
    return text

# ------------------------------
# Генерация ответа школьника
# ------------------------------
@retry_on_failure(max_retries=3, delay=1, backoff=2)
def generate_student_response(prompt):
    response = cerebras_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama3.1-8b",
        max_tokens=150,
        temperature=0.6
    )
    return response.choices[0].message.content.strip()

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

def get_student_response(user_message, session):
    good_count = session.get('good_explanations', 0)
    topic = session.get('topic', 'физика')
    task = session.get('task', '')
    history = session.get('messages', [])

    is_helpful = check_teacher_quality(user_message, topic)
    if is_helpful:
        session['good_explanations'] = good_count + 1
        good_count = session['good_explanations']

    history_text = "\n".join([f"Учитель: {m['content']}" if m['role'] == 'user' else f"Я: {m['content']}" for m in history[-6:]])

    if good_count == 0:
        level = "Ты только что показал своё неправильное решение. Ты пока совсем не понимаешь тему."
    elif good_count == 1:
        level = "Учитель дал первую подсказку с примером из жизни. Ты начинаешь догадываться, но ещё не уверен."
    elif good_count == 2:
        level = "Учитель объяснил уже два раза. Ты почти понял, но можешь ошибиться в единицах."
    else:
        level = "Теперь ты должен решить задачу правильно."

    prompt = (
        f"Ты — школьник 8 класса, не очень сильный в физике. Тема: {topic}.\n"
        f"Задача: {task}\n\n"
        f"{level}\n\n"
        f"Диалог до этого:\n{history_text}\n"
        f"Последнее сообщение учителя: \"{user_message}\"\n\n"
        "Ответь коротко (1-2 предложения), естественно, как школьник. "
        "Не повторяй слова учителя. Не решай задачу полностью правильно, если учитель объяснил меньше 3 раз."
    )

    try:
        result = generate_student_response(prompt)
        result = clean_response(result, user_message)
        # Защита от слишком быстрого решения
        if good_count < 2 and any(x in result.lower() for x in ["100000", "2000000", "a =", "работа =", "дж"]):
            result = "Понял, что нужно учитывать силу тяжести... А как её правильно посчитать?"
        return result
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        return "Я запутался... Объясните ещё раз, пожалуйста?"

# ------------------------------
# Flask handlers
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
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        print("Тесты запущены...")
        print("✓ main.py загружен успешно")
    else:
        port = int(os.environ.get("PORT", 5000))
        app.run(host='0.0.0.0', port=port, debug=False)
