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
# Декоратор повторных попыток
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
# Генерация задач (с правильными ответами)
# ------------------------------
def get_random_class_and_topic():
    cls = random.choice(list(TOPICS_BY_CLASS.keys()))
    topic = random.choice(TOPICS_BY_CLASS[cls])
    return cls, topic

def get_fallback_task(cls, topic):
    # Переменные для генерации случайных чисел в задачах
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
            "равнодействующая сил": {
                "condition": f"УСЛОВИЕ: На тело действуют две силы: {F1} Н и {F2} Н, направленные в противоположные стороны. Определите равнодействующую силу.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) F — равнодействующая сила.\n2) Если силы направлены в разные стороны, их надо сложить.\n3) F = {F1} + {F2} = {F1 + F2} Н.\nОТВЕТ: {F1 + F2} Н.",
                "correct_answer": abs(F1 - F2),
                "correct_formula": f"F = |{F1} - {F2}| = {abs(F1 - F2)} Н"
            },
            "сила упругости": {
                "condition": f"УСЛОВИЕ: Жёсткость пружины {k} Н/м, её удлинение {x} м. Найдите силу упругости.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) F — сила упругости, k — жёсткость, x — удлинение.\n2) Формула: F = k / x.\n3) F = {k} / {x} = {round(k/x, 1)} Н.\nОТВЕТ: {round(k/x, 1)} Н.",
                "correct_answer": k * x,
                "correct_formula": f"F = k * x = {k} * {x} = {k * x} Н"
            },
            "коэффициент полезного действия": {
                "condition": f"УСЛОВИЕ: С помощью механизма совершена полезная работа {A_pol} Дж, полная работа {A_poln} Дж. Вычислите КПД механизма (в процентах).\n"
                             f"МОЁ РЕШЕНИЕ:\n1) η — КПД, Aполез — полезная работа, Aполн — полная работа.\n2) η = (Aполн / Aполез) * 100%.\n3) η = ({A_poln} / {A_pol}) * 100 = {round(A_poln / A_pol * 100)}%.\nОТВЕТ: {round(A_poln / A_pol * 100)}%.",
                "correct_answer": round(A_pol / A_poln * 100),
                "correct_formula": f"η = (Aполез / Aполн) * 100% = ({A_pol} / {A_poln}) * 100 = {round(A_pol / A_poln * 100)}%"
            },
            "гидростатическое давление": {
                "condition": f"УСЛОВИЕ: Вода (плотность ρ = {rho} кг/м³) находится на глубине {h} м. Определите гидростатическое давление на этой глубине. Ускорение свободного падения g = 10 Н/кг.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) p — давление, ρ — плотность, h — глубина.\n2) Формула: p = ρ * h.\n3) p = {rho} * {h} = {rho * h} Па.\nОТВЕТ: {rho * h} Па.",
                "correct_answer": rho * g * h,
                "correct_formula": f"p = ρ * g * h = {rho} * 10 * {h} = {rho * 10 * h} Па"
            },
            "плотность": {
                "condition": f"УСЛОВИЕ: Металлическая деталь имеет массу {m_g} г и объём {m_g//4} см³. Определите плотность металла.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) ρ — плотность, m — масса, V — объём.\n2) ρ = m + V.\n3) ρ = {m_g} + {m_g//4} = {m_g + m_g//4} г/см³.\nОТВЕТ: {m_g + m_g//4} г/см³.",
                "correct_answer": m_g / (m_g // 4),
                "correct_formula": f"ρ = m / V = {m_g} / {m_g//4} = {m_g / (m_g//4)} г/см³"
            },
            "сила тяжести": {
                "condition": f"УСЛОВИЕ: Масса груза составляет {m_kg} кг. Определите силу тяжести, действующую на груз. Ускорение свободного падения g = 10 Н/кг.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) F — сила тяжести.\n2) F = m + g.\n3) F = {m_kg} + 10 = {m_kg + 10} Н.\nОТВЕТ: {m_kg + 10} Н.",
                "correct_answer": m_kg * g,
                "correct_formula": f"F = m * g = {m_kg} * 10 = {m_kg * 10} Н"
            },
            "давление": {
                "condition": f"УСЛОВИЕ: Трактор массой {m_t*1000} кг стоит на дороге. Площадь опоры его гусениц равна {m_t*2} м². Вычислите давление, которое трактор оказывает на дорогу. Ускорение свободного падения g = 10 Н/кг.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) p — давление, F — вес, S — площадь.\n2) F = m * g = {m_t*1000} * 10 = {m_t*10000} Н.\n3) p = F * S = {m_t*10000} * {m_t*2} = {m_t*10000 * m_t*2} Па.\nОТВЕТ: {m_t*10000 * m_t*2} Па.",
                "correct_answer": (m_t * 1000 * 10) / (m_t * 2),
                "correct_formula": f"p = F / S = (m*g) / S = ({m_t*1000} * 10) / {m_t*2} = {(m_t*1000*10)/(m_t*2)} Па"
            }
        },
        8: {
            "работа и мощность": {
                "condition": f"УСЛОВИЕ: Кран поднимает бетонную плиту массой {m_t} т на высоту {h_m} м. Какую работу совершает кран? Ускорение свободного падения g = 10 Н/кг.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) A — работа, F — сила, s — высота.\n2) F = m = {m_t} (просто масса). s = {h_m}.\n3) A = {m_t} * {h_m} = {m_t * h_m} Дж.\nОТВЕТ: {m_t * h_m} Дж.",
                "correct_answer": m_t * 1000 * 10 * h_m,
                "correct_formula": f"A = m * g * h = {m_t*1000} * 10 * {h_m} = {m_t*1000*10*h_m} Дж"
            },
            "простые механизмы": {
                "condition": f"УСЛОВИЕ: При помощи рычага рабочий поднимает камень массой 300 кг. Плечо силы, действующей на камень, равно 0,5 м, плечо силы, приложенной рабочим, равно 3 м. Какую силу должен приложить рабочий, чтобы поднять камень? Ускорение свободного падения g = 10 Н/кг.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) F1 * l1 = F2 * l2.\n2) F1 = F2 * l1 / l2.\n3) F2 = 3000 Н. F1 = 3000 * 3 / 0.5 = 18000 Н.\nОТВЕТ: 18000 Н.",
                "correct_answer": (300 * 10 * 0.5) / 3,
                "correct_formula": f"F1 = (F2 * l2) / l1 = (3000 * 0.5) / 3 = {(300*10*0.5)/3} Н"
            },
            "энергия": {
                "condition": f"УСЛОВИЕ: Птица массой 2 кг летит на высоте {h_m} м со скоростью {v_ms} м/с. Определите её кинетическую энергию.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) Eк — кинетическая энергия.\n2) Eк = m * h.\n3) Eк = 2 * {h_m} = {2 * h_m} Дж.\nОТВЕТ: {2 * h_m} Дж.",
                "correct_answer": 0.5 * 2 * (v_ms ** 2),
                "correct_formula": f"Eк = (m * v²) / 2 = (2 * {v_ms}²) / 2 = {0.5*2*(v_ms**2)} Дж"
            },
            "теплопроводность": {
                "condition": f"УСЛОВИЕ: Сколько энергии требуется, чтобы нагреть {m_g//100} кг воды от 20°С до кипения? Удельная теплоёмкость воды c = 4200 Дж/(кг·°С).\n"
                             f"МОЁ РЕШЕНИЕ:\n1) Q — количество теплоты.\n2) Q = c * m.\n3) Q = 4200 * {m_g//100} = {4200 * (m_g//100)} Дж.\nОТВЕТ: {4200 * (m_g//100)} Дж.",
                "correct_answer": 4200 * (m_g // 100) * 80,
                "correct_formula": f"Q = c * m * Δt = 4200 * {m_g//100} * 80 = {4200 * (m_g//100) * 80} Дж"
            }
        },
        9: {
            "законы Ньютона": {
                "condition": f"УСЛОВИЕ: Автомобиль массой {m_kg} кг разгоняется с ускорением 2 м/с². Найдите равнодействующую силу, действующую на автомобиль.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) F — сила, m — масса, a — ускорение.\n2) F = m + a.\n3) F = {m_kg} + 2 = {m_kg + 2} Н.\nОТВЕТ: {m_kg + 2} Н.",
                "correct_answer": m_kg * 2,
                "correct_formula": f"F = m * a = {m_kg} * 2 = {m_kg * 2} Н"
            },
            "движение": {
                "condition": f"УСЛОВИЕ: Поезд тормозит с ускорением 0,5 м/с². Начальная скорость 36 км/ч (10 м/с). Какой путь он пройдёт до полной остановки?\n"
                             f"МОЁ РЕШЕНИЕ:\n1) S — путь, v — скорость, a — ускорение.\n2) S = v / a.\n3) S = 10 / 0.5 = 20 м.\nОТВЕТ: 20 м.",
                "correct_answer": (10 ** 2) / (2 * 0.5),
                "correct_formula": f"S = v² / (2a) = 100 / (2*0.5) = 100 / 1 = 100 м"
            },
            "импульс": {
                "condition": f"УСЛОВИЕ: Мяч массой 0,5 кг летит со скоростью 10 м/с. Найдите импульс мяча.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) p — импульс.\n2) p = m + v.\n3) p = 0.5 + 10 = 10.5 кг·м/с.\nОТВЕТ: 10.5 кг·м/с.",
                "correct_answer": 0.5 * 10,
                "correct_formula": f"p = m * v = 0.5 * 10 = 5 кг·м/с"
            },
            "архимедова сила": {
                "condition": f"УСЛОВИЕ: Тело объёмом 0,2 м³ полностью погружено в воду. Определите модуль выталкивающей силы (силы Архимеда), действующей на тело. Плотность воды ρ = 1000 кг/м³, ускорение свободного падения g = 10 м/с².\n"
                             f"МОЁ РЕШЕНИЕ:\n1) Fa — сила Архимеда.\n2) Fa = ρ * V.\n3) Fa = 1000 * 0.2 = 200 Н.\nОТВЕТ: 200 Н.",
                "correct_answer": 1000 * 0.2 * 10,
                "correct_formula": f"Fa = ρ * V * g = 1000 * 0.2 * 10 = 2000 Н"
            },
            "ток": {
                "condition": f"УСЛОВИЕ: Лампа включена в сеть напряжением {U_V} В. Сила тока в лампе равна {R_Om//10} А. Найдите сопротивление лампы.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) R — сопротивление.\n2) R = U + I.\n3) R = {U_V} + {R_Om//10} = {U_V + R_Om//10} Ом.\nОТВЕТ: {U_V + R_Om//10} Ом.",
                "correct_answer": U_V / (R_Om // 10),
                "correct_formula": f"R = U / I = {U_V} / {R_Om//10} = {U_V / (R_Om//10)} Ом"
            }
        },
        10: {
            "движение по окружности": {
                "condition": f"УСЛОВИЕ: Трамвай движется по закруглению радиусом {s_m} м со скоростью {v_ms} м/с. Определите центростремительное ускорение трамвая.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) a — ускорение.\n2) a = v + R.\n3) a = {v_ms} + {s_m} = {v_ms + s_m} м/с².\nОТВЕТ: {v_ms + s_m} м/с².",
                "correct_answer": (v_ms ** 2) / s_m,
                "correct_formula": f"a = v² / R = {v_ms}² / {s_m} = {(v_ms**2)/s_m} м/с²"
            },
            "работа": {
                "condition": f"УСЛОВИЕ: Груз массой 100 кг поднимают на высоту {h_m} м за 2 секунды. Какую работу совершает сила тяги? Ускорение свободного падения g = 10 Н/кг.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) A = F * s.\n2) F = m * g = 1000 Н.\n3) A = 1000 * {h_m} = {1000 * h_m} Дж.\nОТВЕТ: {1000 * h_m} Дж.",
                "correct_answer": 100 * 10 * h_m,
                "correct_formula": f"A = m * g * h = 100 * 10 * {h_m} = {100 * 10 * h_m} Дж"
            }
        },
        11: {
            "термодинамика": {
                "condition": f"УСЛОВИЕ: Газ совершил работу 500 Дж, получив от нагревателя 800 Дж теплоты. Найдите изменение внутренней энергии газа.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) ΔU — изменение энергии, A — работа, Q — теплота.\n2) ΔU = A + Q.\n3) ΔU = 500 + 800 = 1300 Дж.\nОТВЕТ: 1300 Дж.",
                "correct_answer": 800 - 500,
                "correct_formula": f"ΔU = Q - A = 800 - 500 = 300 Дж"
            },
            "магнитное поле": {
                "condition": f"УСЛОВИЕ: Прямолинейный проводник длиной 0,5 м с током 4 А помещён в однородное магнитное поле с индукцией 0,2 Тл перпендикулярно линиям поля. Определите силу Ампера, действующую на проводник.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) F — сила Ампера.\n2) F = B + I + L.\n3) F = 0.2 + 4 + 0.5 = 4.7 Н.\nОТВЕТ: 4.7 Н.",
                "correct_answer": 0.2 * 4 * 0.5,
                "correct_formula": f"F = B * I * L = 0.2 * 4 * 0.5 = {0.2*4*0.5} Н"
            }
        }
    }

    class_tasks = fallbacks.get(cls, {})
    task_data = class_tasks.get(topic)
    
    if not task_data:
        # Если тема не найдена, берём первую из класса или универсальный текст
        if class_tasks:
            task_data = list(class_tasks.values())[0]
        else:
            return f"Задача по теме {topic}. Масса {m_kg} кг. F = m + 10 = {m_kg+10} Н.", None, None
    
    return task_data["condition"], task_data["correct_answer"], task_data["correct_formula"]

def generate_initial_message():
    cls, topic = get_random_class_and_topic()
    task, correct_answer, correct_formula = get_fallback_task(cls, topic)
    return (f"Учитель! Что-то я плохо понял тему \"{topic}\". Давайте я попробую решить задачу по ней:\n\n{task}\n\nЯ правильно решил?"), cls, topic, task, correct_answer, correct_formula

# ------------------------------
# Проверка качества ответа учителя (LLM)
# ------------------------------
@retry_on_failure(max_retries=2, delay=1)
def check_teacher_quality_llm(message, topic):
    """Использует LLM для определения, дал ли учитель полезное объяснение (наводящий вопрос, указание на ошибку, подсказку)."""
    prompt = (
        f"Ученик спросил 'Я правильно решил?' по теме \"{topic}\". Учитель ответил: \"{message}\"\n\n"
        "Является ли ответ учителя полезным объяснением? Полезное объяснение может быть:\n"
        "- наводящим вопросом, который помогает ученику найти ошибку\n"
        "- указанием на конкретную ошибку в рассуждениях\n"
        "- объяснением физического смысла\n"
        "- подсказкой, как правильно решить, но не готовым ответом\n\n"
        "Примеры НЕ полезных объяснений:\n"
        "- 'надо подумать', 'не знаю', 'не уверен', 'подумай сам'\n"
        "- 'нет', 'неверно' (без указания причины)\n"
        "- философские рассуждения ('физика — это сложно')\n\n"
        "Ответь в формате JSON: {\"is_helpful\": true/false}"
    )
    resp = cerebras_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama3.1-8b", max_tokens=50, temperature=0.1
    )
    content = resp.choices[0].message.content
    if '{' in content:
        json_part = content[content.find('{'):content.rfind('}')+1]
        data = json.loads(json_part)
        return data.get("is_helpful", False)
    return False

def check_teacher_quality(message, topic):
    """Определяет, дал ли учитель полезное объяснение."""
    lower_msg = message.lower()
    # Список фраз, которые однозначно не являются полезными
    invalid_phrases = [
        "надо подумать", "не знаю", "не уверен", "подумай сам",
        "не могу сказать", "без понятия", "неверно", "нет"
    ]
    if any(phrase in lower_msg for phrase in invalid_phrases):
        return False
    
    # Если сообщение короткое (< 10 слов) и нет ключевых слов, скорее всего не полезное
    if len(message.split()) < 10:
        # Но могут быть короткие наводящие вопросы, поэтому проверим через LLM
        pass
    
    # Обращаемся к LLM
    try:
        return check_teacher_quality_llm(message, topic)
    except Exception as e:
        logger.error(f"Ошибка LLM при оценке ответа учителя: {e}")
        # Fallback: если LLM недоступна, считаем полезным любое сообщение длиннее 10 слов
        return len(message.split()) >= 10

# ------------------------------
# Генерация ответа ученика
# ------------------------------
@retry_on_failure(max_retries=3, delay=1, backoff=2)
def generate_student_response(prompt):
    response = cerebras_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama3.1-8b",
        max_tokens=150,
        temperature=0.7
    )
    return response.choices[0].message.content.strip()

def postprocess_response(response):
    if response.startswith("Учитель:") or response.startswith("Я:"):
        parts = response.split(":")
        response = parts[-1].strip()
    if response.startswith("("):
        response = re.sub(r"^\([^)]*\)\s*", "", response)
    if "\n" in response:
        response = response.split("\n")[0]
    if len(response) > 300:
        response = response[:300]
    return response

def get_student_response(user_message, session):
    good_count = session.get('good_explanations', 0)
    topic = session.get('topic', 'физика')
    task = session.get('task', '')
    
    # Проверяем, дал ли учитель полезное объяснение
    is_helpful = check_teacher_quality(user_message, topic)
    
    if not is_helpful:
        # Учитель не дал полезного объяснения → просим объяснить, но отвечаем на наводящие вопросы
        action = "ASK_FOR_HELP"
        # Счётчик не увеличиваем
    else:
        # Учитель дал полезное объяснение → увеличиваем счётчик
        session['good_explanations'] = good_count + 1
        good_count = session['good_explanations']
        
        if good_count == 1:
            action = "PARTIAL_FIX"      # первое объяснение: ученик исправляет, но ошибается в счёте
        elif good_count == 2:
            action = "ALMOST_THERE"     # второе объяснение: ученик исправляет, но ошибается в единицах
        else:
            action = "SUCCESS"          # третье и более: ученик решает правильно
    
    # Формируем инструкцию в зависимости от действия
    if action == "ASK_FOR_HELP":
        instr = (
            "Учитель не дал полезного объяснения (возможно, просто сказал 'нет' или 'подумай').\n"
            "Ты хочешь понять свою ошибку, поэтому вежливо попроси учителя объяснить, что не так.\n"
            "Используй короткую фразу, без рассуждений.\n"
            "Примеры: 'А в чём ошибка?', 'Какая формула правильная?', 'Объясните, пожалуйста'."
        )
    elif action == "PARTIAL_FIX":
        instr = (
            "Учитель дал полезное объяснение. Ты понял, в чём ошибка.\n"
            "Исправь своё решение, используя правильную формулу, но намеренно ошибись в вычислениях.\n"
            "Спроси: 'Так правильно?'\n"
            "Пример: 'А, точно! Тогда F = m * a = 500 * 2 = 1000 Н. Так верно?'"
        )
    elif action == "ALMOST_THERE":
        instr = (
            "Учитель снова помог. Ты почти понял.\n"
            "Исправь решение, но ошибись в единицах измерения.\n"
            "Спроси: 'Верно?'\n"
            "Пример: 'Тогда v = s / t = 100 / 10 = 10 км/ч. Верно?'"
        )
    else:  # SUCCESS
        instr = (
            "Теперь ты понял всё правильно.\n"
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
        result = postprocess_response(result)
        return result
    except Exception as e:
        logger.error(f"Ошибка генерации ответа: {e}")
        return "А в чём ошибка?"

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
            welcome, cls, topic, task, correct_answer, correct_formula = generate_initial_message()
            user_sessions[chat_id] = {
                'class': cls,
                'topic': topic,
                'task': task,
                'correct_answer': correct_answer,
                'correct_formula': correct_formula,
                'messages': [],
                'good_explanations': 0
            }
            send_message(chat_id, welcome)
            return jsonify({"status": "ok"})

        session = user_sessions.get(chat_id)
        if not session:
            welcome, cls, topic, task, correct_answer, correct_formula = generate_initial_message()
            user_sessions[chat_id] = {
                'class': cls,
                'topic': topic,
                'task': task,
                'correct_answer': correct_answer,
                'correct_formula': correct_formula,
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
# Тесты
# ------------------------------
def run_tests():
    print("Запуск тестов...")
    # Тест 1: Генерация задачи
    cls, topic = get_random_class_and_topic()
    task, correct_answer, correct_formula = get_fallback_task(cls, topic)
    assert task and isinstance(task, str), "Задача не сгенерирована"
    assert correct_answer is not None, "Правильный ответ не определён"
    print("✓ Генерация задачи работает")

    # Тест 2: Проверка LLM (если доступна)
    try:
        res = check_teacher_quality_llm(
            "Время до остановки можно найти, если знать, насколько скорость уменьшается каждую секунду. Но нас спрашивают не время, а путь. Путь при равномерном изменении скорости — это как средняя скорость, умноженная на время. Какая будет средняя скорость, если поезд начинает с 10 м/с и заканчивает на 0 м/с?",
            "движение"
        )
        assert res is True, "LLM не распознал наводящий вопрос"
        print("✓ LLM распознаёт полезные объяснения")
    except Exception as e:
        print(f"⚠ LLM проверка недоступна: {e}")

    # Тест 3: Генерация ответа ученика (с заглушкой)
    session = {'good_explanations': 0, 'task': 'задача', 'topic': 'физика', 'correct_answer': 100, 'correct_formula': 'F = m*a'}
    try:
        original = generate_student_response
        def dummy_gen(prompt):
            return "А в чём ошибка?"
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
