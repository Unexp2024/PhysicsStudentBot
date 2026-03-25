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
# Декоратор повторных попыток (рекомендация 4)
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
                    logger.warning(f"Попытка {attempt+1} для {func.__name__} не удалась: {e}")
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(current_delay)
                    current_delay *= backoff
            return None
        return wrapper
    return decorator

# ------------------------------
# Генерация задач
# ------------------------------
def get_random_class_and_topic():
    cls = random.choice(list(TOPICS_BY_CLASS.keys()))
    topic = random.choice(TOPICS_BY_CLASS[cls])
    return cls, topic

def get_fallback_task(cls, topic):
    # ... (код без изменений, см. предыдущую версию) ...
    # Оставляем как в предыдущем ответе
    v_kmh = random.choice([36, 54, 72])
    v_ms = random.choice([10, 15, 20])
    t_min = random.choice([5, 10, 20])
    t_h = random.choice([0.5, 2, 3])
    m_kg = random.choice([500, 1500, 3000])
    m_g = random.choice([200, 500, 1000])
    m_t = random.choice([2, 5, 10])
    h_m = random.choice([5, 10, 20])
    s_m = random.choice([100, 500, 1000])
    s_km = random.choice([30, 60, 90])
    F_N = random.choice([100, 500, 1000])
    U_V = random.choice([220, 110])
    R_Om = random.choice([10, 20, 50])

    F1 = random.choice([3, 5, 7])
    F2 = random.choice([4, 6, 8])
    k = random.choice([100, 200, 300])
    x = random.choice([0.05, 0.1, 0.15])
    A_pol = random.choice([300, 500, 700])
    A_poln = random.choice([600, 1000, 1400])
    rho = 1000
    g = 10
    h = random.choice([3, 5, 8])

    fallbacks = {
        7: {
            "равнодействующая сил":
                f"УСЛОВИЕ: На тело действуют две силы: {F1} Н и {F2} Н, направленные в противоположные стороны. Найдите равнодействующую силу.\n"
                f"МОЁ РЕШЕНИЕ:\n1) F — равнодействующая сила.\n2) Если силы направлены в разные стороны, их надо сложить.\n3) F = {F1} + {F2} = {F1 + F2} Н.\nОТВЕТ: {F1 + F2} Н.",
            "сила упругости":
                f"УСЛОВИЕ: Жёсткость пружины {k} Н/м, её удлинение {x} м. Найдите силу упругости.\n"
                f"МОЁ РЕШЕНИЕ:\n1) F — сила упругости, k — жёсткость, x — удлинение.\n2) Формула: F = k / x.\n3) F = {k} / {x} = {round(k/x, 1)} Н.\nОТВЕТ: {round(k/x, 1)} Н.",
            "коэффициент полезного действия":
                f"УСЛОВИЕ: С помощью механизма совершена полезная работа {A_pol} Дж, полная работа {A_poln} Дж. Найдите КПД (в процентах).\n"
                f"МОЁ РЕШЕНИЕ:\n1) η — КПД, Aполез — полезная работа, Aполн — полная работа.\n2) η = (Aполн / Aполез) * 100%.\n3) η = ({A_poln} / {A_pol}) * 100 = {round(A_poln / A_pol * 100)}%.\nОТВЕТ: {round(A_poln / A_pol * 100)}%.",
            "гидростатическое давление":
                f"УСЛОВИЕ: Вода (плотность {rho} кг/м³) находится на глубине {h} м. Найдите давление воды. (g = 10 Н/кг).\n"
                f"МОЁ РЕШЕНИЕ:\n1) p — давление, ρ — плотность, h — глубина.\n2) Формула: p = ρ * h.\n3) p = {rho} * {h} = {rho * h} Па.\nОТВЕТ: {rho * h} Па.",
            "плотность":
                f"УСЛОВИЕ: Металлическая деталь имеет массу {m_g} г и объём {m_g//4} см³. Определите плотность металла.\n"
                f"МОЁ РЕШЕНИЕ:\n1) ρ — плотность, m — масса, V — объём.\n2) ρ = m + V.\n3) ρ = {m_g} + {m_g//4} = {m_g + m_g//4} г/см³.\nОТВЕТ: {m_g + m_g//4} г/см³.",
            "сила тяжести":
                f"УСЛОВИЕ: Масса груза составляет {m_kg} кг. Найдите силу тяжести, действующую на груз. (g = 10 Н/кг).\n"
                f"МОЁ РЕШЕНИЕ:\n1) F — сила тяжести.\n2) F = m + g.\n3) F = {m_kg} + 10 = {m_kg + 10} Н.\nОТВЕТ: {m_kg + 10} Н.",
            "давление":
                f"УСЛОВИЕ: Трактор массой {m_t*1000} кг стоит на дороге. Площадь опоры его гусениц равна {m_t*2} м². Вычислите давление. (g=10)\n"
                f"МОЁ РЕШЕНИЕ:\n1) p — давление, F — вес, S — площадь.\n2) F = m * g = {m_t*1000} * 10 = {m_t*10000} Н.\n3) p = F * S = {m_t*10000} * {m_t*2} = {m_t*10000 * m_t*2} Па.\nОТВЕТ: {m_t*10000 * m_t*2} Па."
        },
        8: {
            "работа и мощность":
                f"УСЛОВИЕ: Кран поднимает бетонную плиту массой {m_t} т на высоту {h_m} м. Какую работу совершает кран? (g=10 Н/кг).\n"
                f"МОЁ РЕШЕНИЕ:\n1) A — работа, F — сила, s — высота.\n2) F = m = {m_t} (просто масса). s = {h_m}.\n3) A = {m_t} * {h_m} = {m_t * h_m} Дж.\nОТВЕТ: {m_t * h_m} Дж.",
            "простые механизмы":
                f"УСЛОВИЕ: При помощи рычага рабочий поднимает камень массой 300 кг. Плечо камня 0.5 м, плечо руки 3 м. Какую силу приложить? (g=10)\n"
                f"МОЁ РЕШЕНИЕ:\n1) F1 * l1 = F2 * l2.\n2) F1 = F2 * l1 / l2.\n3) F2 = 3000 Н. F1 = 3000 * 3 / 0.5 = 18000 Н.\nОТВЕТ: 18000 Н.",
            "энергия":
                f"УСЛОВИЕ: Птица массой 2 кг летит на высоте {h_m} м со скоростью {v_ms} м/с. Определите её кинетическую энергию.\n"
                f"МОЁ РЕШЕНИЕ:\n1) Eк — кинетическая энергия.\n2) Eк = m * h.\n3) Eк = 2 * {h_m} = {2 * h_m} Дж.\nОТВЕТ: {2 * h_m} Дж.",
            "теплопроводность":
                f"УСЛОВИЕ: Сколько энергии нужно, чтобы нагреть {m_g//100} кг воды от 20°С до кипения? (c = 4200 Дж/(кг*°С)).\n"
                f"МОЁ РЕШЕНИЕ:\n1) Q — количество теплоты.\n2) Q = c * m.\n3) Q = 4200 * {m_g//100} = {4200 * (m_g//100)} Дж.\nОТВЕТ: {4200 * (m_g//100)} Дж."
        },
        9: {
            "законы Ньютона":
                f"УСЛОВИЕ: Автомобиль массой {m_kg} кг разгоняется с ускорением 2 м/с². Найдите равнодействующую силу.\n"
                f"МОЁ РЕШЕНИЕ:\n1) F — сила, m — масса, a — ускорение.\n2) F = m + a.\n3) F = {m_kg} + 2 = {m_kg + 2} Н.\nОТВЕТ: {m_kg + 2} Н.",
            "движение":
                f"УСЛОВИЕ: Поезд тормозит с ускорением 0.5 м/с². Начальная скорость 36 км/ч (10 м/с). Какой путь до остановки?\n"
                f"МОЁ РЕШЕНИЕ:\n1) S — путь, v — скорость, a — ускорение.\n2) S = v / a.\n3) S = 10 / 0.5 = 20 м.\nОТВЕТ: 20 м.",
            "импульс":
                f"УСЛОВИЕ: Мяч массой 0.5 кг летит со скоростью 10 м/с. Найдите импульс.\n"
                f"МОЁ РЕШЕНИЕ:\n1) p — импульс.\n2) p = m + v.\n3) p = 0.5 + 10 = 10.5 кг*м/с.\nОТВЕТ: 10.5 кг*м/с.",
            "архимедова сила":
                f"УСЛОВИЕ: На тело объёмом 0.2 м³, полностью погружённое в воду, действует архимедова сила. (ρ=1000 кг/м³, g=10).\n"
                f"МОЁ РЕШЕНИЕ:\n1) Fa — сила Архимеда.\n2) Fa = ρ * V.\n3) Fa = 1000 * 0.2 = 200 Н.\nОТВЕТ: 200 Н.",
            "ток":
                f"УСЛОВИЕ: Лампа включена в сеть {U_V} В. Сила тока {R_Om//10} А. Найдите сопротивление.\n"
                f"МОЁ РЕШЕНИЕ:\n1) R — сопротивление.\n2) R = U + I.\n3) R = {U_V} + {R_Om//10} = {U_V + R_Om//10} Ом.\nОТВЕТ: {U_V + R_Om//10} Ом."
        },
        10: {
            "движение по окружности":
                f"УСЛОВИЕ: Трамвай движется по закруглению радиусом {s_m} м со скоростью {v_ms} м/с. Центростремительное ускорение?\n"
                f"МОЁ РЕШЕНИЕ:\n1) a — ускорение.\n2) a = v + R.\n3) a = {v_ms} + {s_m} = {v_ms + s_m} м/с².\nОТВЕТ: {v_ms + s_m} м/с².",
            "работа":
                f"УСЛОВИЕ: Груз массой 100 кг поднимают на высоту {h_m} м за 2 секунды. Работа силы тяги? (g=10)\n"
                f"МОЁ РЕШЕНИЕ:\n1) A = F * s.\n2) F = m * g = 1000 Н.\n3) A = 1000 * {h_m} = {1000 * h_m} Дж.\nОТВЕТ: {1000 * h_m} Дж."
        },
        11: {
            "термодинамика":
                f"УСЛОВИЕ: Газ совершил работу 500 Дж, получив 800 Дж теплоты. Изменение внутренней энергии?\n"
                f"МОЁ РЕШЕНИЕ:\n1) ΔU — изменение энергии, A — работа, Q — теплота.\n2) ΔU = A + Q.\n3) ΔU = 500 + 800 = 1300 Дж.\nОТВЕТ: 1300 Дж.",
            "магнитное поле":
                f"УСЛОВИЕ: Проводник длиной 0.5 м с током 4 А в поле индукцией 0.2 Тл. Сила Ампера? (Перпендикулярно).\n"
                f"МОЁ РЕШЕНИЕ:\n1) F — сила Ампера.\n2) F = B + I + L.\n3) F = 0.2 + 4 + 0.5 = 4.7 Н.\nОТВЕТ: 4.7 Н."
        }
    }

    class_tasks = fallbacks.get(cls, {})
    task = class_tasks.get(topic)

    if not task:
        if class_tasks:
            task = list(class_tasks.values())[0]
        else:
            task = f"Задача по теме {topic}. Масса {m_kg} кг. F = m + 10 = {m_kg+10} Н."
    return task

def generate_initial_message():
    cls, topic = get_random_class_and_topic()
    task = get_fallback_task(cls, topic)
    return (f"Учитель! Что-то я плохо понял тему \"{topic}\". Давайте я попробую решить задачу по ней:\n\n{task}\n\nЯ правильно решил?"), cls, topic, task

# ------------------------------
# Улучшенная проверка качества ответа учителя (рекомендация 2)
# ------------------------------
def contains_explanation(text):
    """Проверяет, содержит ли текст явное указание на ошибку (формула, закон, число)."""
    lower = text.lower()
    # Ключевые слова, указывающие на объяснение
    explaining_phrases = [
        "формула", "закон", "правило", "ошибка", "неправильно",
        "должно быть", "надо", "следует", "потому что", "так как",
        "неверно", "проверь", "пересчитай", "вспомни", "посмотри",
        "равнодействующая", "сила упругости", "кпд", "давление", "гидростатическое"
    ]
    if any(phrase in lower for phrase in explaining_phrases):
        return True
    # Проверка на наличие чисел или формул (например, "F =", "m * g")
    if re.search(r'\d+\s*[НмДжПа]', text) or re.search(r'[a-z]\s*[=*/+-]', lower):
        return True
    return False

@retry_on_failure(max_retries=2, delay=1)
def check_teacher_quality_llm(message):
    """Использует LLM для определения, объяснил ли учитель ошибку."""
    prompt = (
        f"Ученик спросил 'Я правильно решил?'. Учитель ответил: \"{message}\"\n\n"
        "Учитель объяснил ошибку? (Указал на формулу, число или причину?).\n"
        "Если просто 'нет' или философия — false.\n"
        "JSON: {\"is_relevant\": true/false}"
    )
    resp = cerebras_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama3.1-8b", max_tokens=50, temperature=0.1
    )
    content = resp.choices[0].message.content
    if '{' in content:
        json_part = content[content.find('{'):content.rfind('}')+1]
        data = json.loads(json_part)
        return data.get("is_relevant", False)
    return False

def check_teacher_quality(message):
    """Комбинированная проверка: эвристики + LLM при необходимости."""
    # Если эвристика явно показывает, что объяснения нет, возвращаем False
    lower_msg = message.lower()
    bad_markers = ["не знаю", "подумай", "сам", "перечитай", "трудно сказать", "не уверен", "спроси", "сомневаюсь", "думаю", "непонятно", "подожди", "минуту", "сейчас", "погоди", "молодец", "умница", "нет", "вряд ли", "неверно"]
    word_count = len(message.split())

    if any(marker in lower_msg for marker in bad_markers) and word_count < 25:
        return False

    # Если эвристика говорит, что объяснение есть, возвращаем True
    if contains_explanation(message):
        return True

    # Иначе обращаемся к LLM
    try:
        return check_teacher_quality_llm(message)
    except Exception as e:
        logger.error(f"Ошибка LLM при оценке ответа учителя: {e}")
        # Если LLM недоступна, принимаем решение по эвристике (False)
        return False

# ------------------------------
# Улучшенная генерация ответа ученика (рекомендация 6)
# ------------------------------
@retry_on_failure(max_retries=3, delay=1, backoff=2)
def generate_student_response(prompt):
    """Генерация ответа ученика с повторными попытками."""
    response = cerebras_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama3.1-8b",
        max_tokens=150,
        temperature=0.6  # немного снижена для большей предсказуемости
    )
    return response.choices[0].message.content.strip()

def get_student_response(user_message, session):
    good_count = session.get('good_explanations', 0)
    is_relevant = check_teacher_quality(user_message)

    if not is_relevant:
        action = "STAY_CONFUSED"
    else:
        session['good_explanations'] = good_count + 1
        good_count = session['good_explanations']

        if good_count == 1: action = "ASK_EXAMPLE"
        elif good_count == 2: action = "PARTIAL_FIX"
        elif good_count == 3: action = "ALMOST_THERE"
        else: action = "SUCCESS"

    task = session.get('task', '')
    topic = session.get('topic', 'физика')

    # Улучшенные инструкции с примерами
    if action == "STAY_CONFUSED":
        instr = (
            "Учитель не объяснил ошибку. Ты уверен в своём решении.\n"
            "Спроси прямо: 'Так ответ правильный или нет?'.\n"
            "Не рассуждай, не пиши скобок, не объясняй физику.\n"
            "Примеры: 'Я уверен, что правильно. Так верно?', 'Ответ правильный?'"
        )
    elif action == "ASK_EXAMPLE":
        instr = (
            "Учитель объяснил ошибку. Скажи 'О, понял...' и попроси пример из жизни.\n"
            "Не исправляй своё решение.\n"
            "Примеры: 'О, понял! А в жизни где это бывает?', 'А, теперь ясно! Можно пример?'"
        )
    elif action == "PARTIAL_FIX":
        instr = (
            "Учитель привёл пример. Исправь формулу, но ошибись в счёте (намеренно).\n"
            "Спроси: 'Так правильно?'.\n"
            "Не пиши длинных объяснений.\n"
            "Пример: 'А, точно! Тогда F = m * a = 500 * 2 = 1000 Н. Так верно?'"
        )
    elif action == "ALMOST_THERE":
        instr = (
            "Реши почти правильно, но ошибись в единицах измерения.\n"
            "Спроси: 'Верно?'.\n"
            "Пример: 'Тогда v = s / t = 100 / 10 = 10 км/ч. Верно?'"
        )
    else:
        instr = (
            "Реши задачу полностью правильно, используя верные формулы.\n"
            "Поблагодари учителя.\n"
            "Пример: 'Спасибо! Теперь понял: v = s / t = 100 / 10 = 10 м/с. Всё верно!'"
        )

    prompt = (
        f"Ты — школьник-двоечник. Тема: {topic}.\n"
        f"Твоя задача (с твоим решением): {task}\n\n"
        f"Учитель написал: \"{user_message}\"\n\n"
        f"Твоя цель: {instr}\n\n"
        "СТРОГИЕ ПРАВИЛА:\n"
        "1. НЕ пиши внутренние монологи и мысли в скобках.\n"
        "2. НЕ рассуждай о физике, не объясняй свои действия.\n"
        "3. Пиши ТОЛЬКО одну короткую фразу или вопрос.\n"
        "4. Не повторяй условие задачи.\n"
        "5. Используй только простые предложения."
    )

    try:
        result = generate_student_response(prompt)
        # Пост-обработка
        if result.startswith("Учитель:") or result.startswith("Я:"):
            parts = result.split(":")
            result = parts[-1].strip()
        if result.startswith("("):
            result = re.sub(r"^\([^)]*\)\s*", "", result)
        if "\n" in result:
            result = result.split("\n")[0]
        # Ограничение длины
        if len(result) > 300:
            result = result[:300]
        return result
    except Exception as e:
        logger.error(f"Ошибка генерации ответа: {e}")
        # Запасной вариант
        return "Я не понял. Можете объяснить ещё раз?"

# ------------------------------
# Flask и Telegram обработчики
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
        logger.error(f"Ошибка отправки сообщения: {e}")

# ------------------------------
# Юнит-тесты (рекомендация 8)
# ------------------------------
def run_tests():
    """Простой набор тестов для ключевых функций."""
    print("Запуск тестов...")

    # Тест 1: Генерация задачи
    cls, topic = get_random_class_and_topic()
    task = get_fallback_task(cls, topic)
    assert task and isinstance(task, str), "Задача не сгенерирована"
    print("✓ Генерация задачи работает")

    # Тест 2: Проверка качества ответа учителя (эвристики)
    assert contains_explanation("Ты ошибся в формуле, надо F = m * a") is True
    assert contains_explanation("Нет") is False
    assert contains_explanation("Подумай сам") is False
    print("✓ Эвристика проверки ответа учителя работает")

    # Тест 3: Проверка LLM (только если доступна)
    try:
        res = check_teacher_quality_llm("Нет, неверно. Правильно: v = s/t")
        assert res is True or res is False, "LLM вернул некорректный результат"
        print("✓ LLM проверка ответа учителя доступна")
    except Exception as e:
        print(f"⚠ LLM проверка недоступна: {e}")

    # Тест 4: Генерация ответа ученика (без реального вызова LLM, только структура)
    session = {'good_explanations': 0, 'task': 'задача', 'topic': 'физика'}
    try:
        # Используем заглушку, чтобы не вызывать LLM в тестах
        original = generate_student_response
        def dummy_gen(prompt):
            return "Я не понял."
        globals()['generate_student_response'] = dummy_gen
        resp = get_student_response("Объяснение", session)
        assert isinstance(resp, str), "Ответ ученика не строка"
        print("✓ Генерация ответа ученика работает (заглушка)")
        globals()['generate_student_response'] = original
    except Exception as e:
        print(f"✗ Ошибка в генерации ответа: {e}")

    print("Тесты завершены.")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        run_tests()
    else:
        app.run(debug=True, port=5000)
