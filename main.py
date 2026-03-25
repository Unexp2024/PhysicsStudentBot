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
import math

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
# Генерация задач (с правильными ответами) - добавлены недостающие темы
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
                "condition": f"УСЛОВИЕ: Металлическая деталь имеет массу {m_g} г и объём {m_g//4} см³. Определите плотность металла (г/см³).\n"
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
                "correct_answer": (m_t * 1000 * g) / (m_t * 2),
                "correct_formula": f"p = F / S = (m * g) / S = ({m_t*1000} * 10) / ({m_t}*2) = {((m_t*1000*10)/(m_t*2))} Па"
            }
        },
        8: {
            "работа и мощность": {
                "condition": f"УСЛОВИЕ: Кран поднимает бетонную плиту массой {m_t} т ({m_t*1000} кг) на высоту {h_m} м. Какую работу совершает кран против силы тяжести? Ускорение свободного падения g = 10 Н/кг.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) A — работа, F — сила, s — высота.\n2) F = m = {m_t} (просто масса). s = {h_m}.\n3) A = {m_t} * {h_m} = {m_t * h_m} Дж.\nОТВЕТ: {m_t * h_m} Дж.",
                "correct_answer": m_t * 1000 * g * h_m,
                "correct_formula": f"A = F * h = (m * g) * h = {m_t*1000} * 10 * {h_m} = {m_t*1000*10*h_m} Дж"
            },
            "простые механизмы": {
                "condition": f"УСЛОВИЕ: При помощи рычага рабочий поднимает камень массой 300 кг. Плечо силы, действующей на камень, равно 0,5 м, плечо силы, приложенной рабочим, равно 3 м. Какую силу должен приложить рабочий, чтобы поднять камень? Ускорение свободного падения g = 10 Н/кг.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) F1 * l1 = F2 * l2.\n2) F1 = F2 * l1 / l2.\n3) F2 = 3000 Н. F1 = 3000 * 3 / 0.5 = 18000 Н.\nОТВЕТ: 18000 Н.",
                "correct_answer": (300 * 10 * 0.5) / 3,
                "correct_formula": f"F1 = (F2 * l2) / l1 = ((300*10) * 0.5) / 3 = {((300*10*0.5)/3)} Н"
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
                "correct_formula": f"S = v² / (2a) = 100 / 1 = 100 м"
            },
            "импульс": {
                "condition": f"УСЛОВИЕ: Мяч массой 0,5 кг летит со скоростью 10 м/с. Найдите импульс мяча.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) p — импульс.\n2) p = m + v.\n3) p = 0.5 + 10 = 10.5 кг·м/с.\nОТВЕТ: 10.5 кг·м/с.",
                "correct_answer": 0.5 * 10,
                "correct_formula": f"p = m * v = 0.5 * 10 = 5 кг·м/с"
            },
            "архимедова сила": {
                "condition": f"УСЛОВИЕ: Тело объёмом 0,2 м³ полностью погружено в воду. Определите модуль выталкивающей силы (силы Архимеда). Плотность воды ρ = 1000 кг/м³, g = 10 Н/кг.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) Fa — сила Архимеда.\n2) Fa = ρ * V.\n3) Fa = 1000 * 0.2 = 200 Н.\nОТВЕТ: 200 Н.",
                "correct_answer": 1000 * 0.2 * 10,
                "correct_formula": f"Fa = ρ * V * g = 1000 * 0.2 * 10 = 2000 Н"
            },
            "ток": {
                "condition": f"УСЛОВИЕ: Лампа включена в сеть напряжением {U_V} В. Сила тока в лампе {R_Om//10} А. Найдите сопротивление лампы.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) R — сопротивление.\n2) R = U + I.\n3) R = {U_V} + {R_Om//10} = {U_V + R_Om//10} Ом.\nОТВЕТ: {U_V + R_Om//10} Ом.",
                "correct_answer": U_V / (R_Om // 10),
                "correct_formula": f"R = U / I = {U_V} / {R_Om//10} = {U_V / (R_Om//10)} Ом"
            }
        },
        10: {
            "законы Кеплера": {
                "condition": f"УСЛОВИЕ: По третьему закону Кеплера T² пропорционально a³. Для Земли T=1 год, a=1 а.е. Для планеты a=8 а.е. Найдите период обращения T планеты (в годах).\n"
                             f"МОЁ РЕШЕНИЕ:\n1) T планеты.\n2) T = a.\n3) T = 8 лет.\nОТВЕТ: 8 лет.",
                "correct_answer": round(math.sqrt(8**3), 1),
                "correct_formula": f"T = sqrt(a³) = sqrt(512) ≈ {round(math.sqrt(512),1)} лет"
            },
            "движение по окружности": {
                "condition": f"УСЛОВИЕ: Трамвай движется по закруглению радиусом {s_m} м со скоростью {v_ms} м/с. Определите центростремительное ускорение.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) a — ускорение.\n2) a = v + R.\n3) a = {v_ms} + {s_m} = {v_ms + s_m} м/с².\nОТВЕТ: {v_ms + s_m} м/с².",
                "correct_answer": (v_ms ** 2) / s_m,
                "correct_formula": f"a = v² / R = {v_ms}² / {s_m} = {(v_ms**2)/s_m} м/с²"
            },
            "тяготение": {
                "condition": f"УСЛОВИЕ: Два шарика массой по {m_kg} кг расположены на расстоянии 1 м. Константа Гравитации G = 6.7e-11 Н·м²/кг². Найдите сила притяжения между ними.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) F.\n2) F = m1 * m2 / r.\n3) F = {m_kg} * {m_kg} / 1 = {m_kg**2} Н.\nОТВЕТ: {m_kg**2} Н.",
                "correct_answer": 6.7e-11 * m_kg * m_kg / 1**2,
                "correct_formula": f"F = G * m1 * m2 / r² ≈ очень маленькое число"
            },
            "работа": {
                "condition": f"УСЛОВИЕ: Груз массой 100 кг поднимают на высоту {h_m} м. Какую работу совершает сила тяги против силы тяжести? g = 10 Н/кг.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) A = F * s.\n2) F = m * g = 1000 Н.\n3) A = 1000 * {h_m} = {1000 * h_m} Дж.\nОТВЕТ: {1000 * h_m} Дж.",
                "correct_answer": 100 * 10 * h_m,
                "correct_formula": f"A = m * g * h = 100 * 10 * {h_m} = {100 * 10 * h_m} Дж"
            }
        },
        11: {
            "молекулярно-кинетическая теория": {
                "condition": f"УСЛОВИЕ: Средняя скорость молекул газа пропорциональна sqrt(T). При удвоении температуры скорость возрастёт в сколько раз?\n"
                             f"МОЁ РЕШЕНИЕ:\n1) v ~ sqrt(T).\n2) Удвоение T -> v удваивается.\n3) v2 = 2 v1.\nОТВЕТ: 2 раза.",
                "correct_answer": "sqrt(2) раза",
                "correct_formula": f"v2 / v1 = sqrt(2) ≈ 1.41 раза"
            },
            "термодинамика": {
                "condition": f"УСЛОВИЕ: Газ совершил работу 500 Дж, получив от нагревателя 800 Дж теплоты. Найдите изменение внутренней энергии газа.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) ΔU — изменение энергии, A — работа, Q — теплота.\n2) ΔU = A + Q.\n3) ΔU = 500 + 800 = 1300 Дж.\nОТВЕТ: 1300 Дж.",
                "correct_answer": 800 - 500,
                "correct_formula": f"ΔU = Q - A = 800 - 500 = 300 Дж"
            },
            "электрическое поле": {
                "condition": f"УСЛОВИЕ: Сила 2 Н действует на заряд 4 мкКл в поле. Найдите напряжённость поля.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) E = F / q.\n2) E = 2 + 4e-6 = очень мало.\nОТВЕТ: 2 / 4e-6 В/м.",
                "correct_answer": 2 / 4e-6,
                "correct_formula": f"E = F / q = 2 / 4e-6 = 5e5 В/м"
            },
            "магнитное поле": {
                "condition": f"УСЛОВИЕ: Проводник длиной 0,5 м с током 4 А в поле B=0,2 Тл перпендикулярно. Сила Ампера?\n"
                             f"МОЁ РЕШЕНИЕ:\n1) F = B + I + L.\n2) F = 0.2 + 4 + 0.5 = 4.7 Н.\nОТВЕТ: 4.7 Н.",
                "correct_answer": 0.2 * 4 * 0.5,
                "correct_formula": f"F = B * I * L = 0.2 * 4 * 0.5 = 0.4 Н"
            },
            "колебания": {
                "condition": f"УСЛОВИЕ: Маятник длиной 1 м. Период колебаний? g=10 Н/кг.\n"
                             f"МОЁ РЕШЕНИЕ:\n1) T = 2π sqrt(l / g).\n2) T = l / g = 0.1 с.\nОТВЕТ: 0.1 с.",
                "correct_answer": round(2 * 3.14 * math.sqrt(1/10), 1),
                "correct_formula": f"T = 2π sqrt(l / g) ≈ 2.0 с"
            }
        }
    }

    class_tasks = fallbacks.get(cls, {})
    task_data = class_tasks.get(topic)
    
    if not task_data:
        if class_tasks:
            task_data = list(class_tasks.values())[0]
        else:
            return f"Задача по теме {topic}. Масса {m_kg} кг. F = m + 10 = {m_kg+10} Н.", None, None
    
    return task_data["condition"], task_data["correct_answer"], task_data["correct_formula"]

def generate_initial_message():
    cls, topic = get_random_class_and_topic()
    task, correct_answer, correct_formula = get_fallback_task(cls, topic)
    welcome = (f"Учитель! Что-то я плохо понял тему \"{topic}\". Давайте я попробую решить задачу по ней:\n\n{task}\n\n"
               f"Я правильно решил? Если нет, то объясните на примере из жизни, пожалуйста.")
    return welcome, cls, topic, task, correct_answer, correct_formula

# ------------------------------
# Проверка качества ответа учителя (LLM)
# ------------------------------
@retry_on_failure(max_retries=2, delay=1)
def check_teacher_quality_llm(message, topic):
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
        "Ответь в формате JSON: {{\"is_helpful\": true/false}}"
    )
    resp = cerebras_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama3.1-8b", max_tokens=50, temperature=0.1
    )
    content = resp.choices[0].message.content.strip()
    try:
        if '{' in content:
            json_part = re.search(r'\{.*\}', content).group()
            data = json.loads(json_part)
            return data.get("is_helpful", False)
    except:
        pass
    return False

def check_teacher_quality(message, topic):
    lower_msg = message.lower()
    invalid_phrases = [
        "надо подумать", "не знаю", "не уверен", "подумай сам",
        "не могу сказать", "без понятия", "неверно", "нет"
    ]
    if any(phrase in lower_msg for phrase in invalid_phrases):
        return False
    try:
        return check_teacher_quality_llm(message, topic)
    except Exception as e:
        logger.error(f"Ошибка LLM при оценке ответа учителя: {e}")
        return len(message.split()) >= 10

# ------------------------------
# Генерация ответа ученика (динамическая, с исправленными ошибками)
# ------------------------------
@retry_on_failure(max_retries=3, delay=1, backoff=2)
def generate_student_response(prompt):
    response = cerebras_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama3.1-8b",
        max_tokens=250,
        temperature=0.7
    )
    return response.choices[0].message.content.strip()

def clean_response(text, user_message):
    """Удаляет повторения и английские слова."""
    # Удаляем префиксы
    text = re.sub(r'^(Ответ учителя:|Учитель:)\s*', '', text, flags=re.IGNORECASE)
    if re.match(r'^["\']', text):
        text = re.sub(r'^["\'].*?["\']\s*', '', text)
    if user_message and user_message in text:
        if text.strip() == user_message.strip():
            text = "Я не совсем понял. Можете ещё раз объяснить?"
        else:
            text = text.replace(user_message, "").strip()
    # Замены английских слов на русские
    eng_to_ru = {
        "force": "сила",
        "power": "мощность",
        "work": "работа",
        "mass": "масса",
        "height": "высота",
        "depends": "зависит",
        "formula": "формула"
    }
    for eng, ru in eng_to_ru.items():
        text = re.sub(rf'\b{eng}\b', ru, text, flags=re.IGNORECASE)
    # Грамматика
    text = text.replace("depends от", "зависит от")
    text = text.replace("на объём зависит", "от объёма зависит")
    return text.strip()

def get_student_response(user_message, session):
    good_count = session.get('good_explanations', 0)
    topic = session.get('topic', 'физика')
    task = session.get('task', '')
    history = session.get('messages', [])
    
    # Количество реплик учителя (предыдущих + текущая)
    num_teacher_msgs = len([m for m in history if m['role'] == 'user']) + 1
    
    is_helpful = check_teacher_quality(user_message, topic)
    if is_helpful:
        session['good_explanations'] = good_count + 1
    
    # История
    history_text = ""
    if history:
        last_few = history[-6:]
        for msg in last_few:
            role = "Учитель" if msg['role'] == 'user' else "Школьник"
            history_text += f"{role}: {msg['content']}\n"
    history_text += f"Учитель: {user_message}\n"
    
    # Уровень понимания по репликам + good_count
    if num_teacher_msgs <= 2:
        understanding = (
            f"Это {num_teacher_msgs}-я реплика учителя. "
            "Дай ОБЩИЕ РАССУЖДЕНИЯ и ПРИМЕРЫ ИЗ ЖИЗНИ. "
            "НЕ выдавай формулы, НЕ считай числа, НЕ решай задачу. "
            "Просто отвечай на вопрос учителя общими словами."
        )
    elif num_teacher_msgs == 3:
        understanding = (
            f"Это {num_teacher_msgs}-я реплика. "
            "Можешь приблизиться: вспомни части формулы, но ошибись в ней или единицах. "
            "Сначала ответь на вопрос учителя."
        )
    else:
        understanding = (
            f"Это {num_teacher_msgs}-я реплика ({good_count} полезных объяснений). "
            "Теперь исправь ошибки в решении задачи, подойди к правильному ответу."
        )
    
    prompt = (
        f"Ты — школьник-отстающий по физике, класс {session.get('class', '?')}, тема: \"{topic}\".\n"
        f"Задача с твоим ошибочным решением:\n{task}\n\n"
        f"{understanding}\n\n"
        f"История диалога:\n{history_text}\n\n"
        "ПРАВИЛА:\n"
        "- ОБЯЗАТЕЛЬНО сначала отвечай напрямую на ПОСЛЕДНИЙ вопрос/реплику учителя: \"{user_message}\".\n"
        "- Не пытайся сразу решать задачу полностью.\n"
        "- Говори естественно, как ученик 7-11 класса: 'Ой, понятно...', 'А что значит...', с ошибками в понимании на ранних этапах.\n"
        "- ТОЛЬКО РУССКИЙ ЯЗЫК, без английских слов (force=сила, work=работа и т.д.).\n"
        "- Кратко: 1-3 предложения.\n"
        "- Не повторяй слова учителя.\n"
        "Твой ответ как школьника:"
    )
    
    try:
        result = generate_student_response(prompt)
        result = clean_response(result, user_message)
        if not result:
            result = "Я запутался. Расскажите подробнее."
        return result
    except Exception as e:
        logger.error(f"Ошибка генерации ответа: {e}")
        return "Я не понял. Объясните проще, пожалуйста."

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
    print("✓ Генерация задачи работает")

    print("Тесты завершены.")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        run_tests()
    else:
        app.run(debug=True, port=5000)
