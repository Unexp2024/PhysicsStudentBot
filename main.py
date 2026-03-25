import os
import json
import random
import logging
import requests
import re
import sys
import time
import warnings
from functools import wraps
from flask import Flask, request, jsonify

# Подавляем предупреждение Pydantic V1 / Python 3.14
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CEREBRAS_API_KEY = os.environ.get('CEREBRAS_API_KEY')

if not TELEGRAM_TOKEN or not CEREBRAS_API_KEY:
    logger.warning("Один или оба токена не установлены — проверьте переменные окружения.")

# Ленивая инициализация клиента Cerebras
_cerebras_client = None

def get_cerebras_client():
    global _cerebras_client
    if _cerebras_client is None:
        from cerebras.cloud.sdk import Cerebras
        _cerebras_client = Cerebras(api_key=CEREBRAS_API_KEY)
    return _cerebras_client

# ------------------------------
# Данные
# ------------------------------
TOPICS_BY_CLASS = {
    7: ["равнодействующая сил", "сила упругости", "коэффициент полезного действия",
        "гидростатическое давление", "плотность", "сила тяжести", "давление"],
    8: ["работа и мощность", "простые механизмы", "энергия", "теплопроводность"],
    9: ["законы Ньютона", "движение", "импульс", "архимедова сила", "ток"],
    10: ["законы Кеплера", "движение по окружности", "тяготение", "работа"],
    11: ["молекулярно-кинетическая теория", "термодинамика",
         "электрическое поле", "магнитное поле", "колебания"]
}

user_sessions = {}

# ------------------------------
# Персистентность сессий
# ------------------------------
SESSIONS_FILE = 'sessions.json'

def load_sessions():
    """Загружает сессии из файла при старте."""
    global user_sessions
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, 'r', encoding='utf-8') as f:
                raw = json.load(f)
                # JSON хранит ключи как строки, конвертируем обратно в int
                user_sessions = {int(k): v for k, v in raw.items()}
            logger.info(f"Загружено {len(user_sessions)} сессий из файла.")
        except Exception as e:
            logger.error(f"Ошибка загрузки сессий: {e}")
            user_sessions = {}

def save_sessions():
    """Сохраняет сессии в файл."""
    try:
        with open(SESSIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_sessions, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения сессий: {e}")

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
# Генерация задач
# ------------------------------
def get_random_class_and_topic():
    cls = random.choice(list(TOPICS_BY_CLASS.keys()))
    topic = random.choice(TOPICS_BY_CLASS[cls])
    return cls, topic

def get_fallback_task(cls, topic):
    v_ms   = random.choice([10, 15, 20])
    m_kg   = random.choice([500, 1500, 3000])
    m_g    = random.choice([200, 500, 1000])
    m_t    = random.choice([2, 5, 10])
    h_m    = random.choice([5, 10, 20])
    s_m    = random.choice([100, 500, 1000])
    U_V    = random.choice([220, 110])
    R_Om   = random.choice([10, 20, 50])
    F1     = random.choice([3, 5, 7])
    F2     = random.choice([4, 6, 8])
    k      = random.choice([100, 200, 300])
    x      = random.choice([0.05, 0.1, 0.15])
    A_pol  = random.choice([300, 500, 700])
    A_poln = random.choice([600, 1000, 1400])
    rho    = 1000
    g      = 10
    h      = random.choice([3, 5, 8])

    fallbacks = {
        7: {
            "равнодействующая сил": {
                "condition": (
                    f"УСЛОВИЕ: На тело действуют две силы: {F1} Н и {F2} Н, "
                    f"направленные в противоположные стороны. "
                    f"Определите равнодействующую силу (в Н).\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) F — равнодействующая сила.\n"
                    f"2) Если силы направлены в разные стороны, их надо сложить.\n"
                    f"3) F = {F1} + {F2} = {F1 + F2} Н.\n"
                    f"ОТВЕТ: {F1 + F2} Н."
                ),
                "correct_answer": abs(F1 - F2),
                "correct_formula": f"F = |{F1} - {F2}| = {abs(F1 - F2)} Н"
            },
            "сила упругости": {
                "condition": (
                    f"УСЛОВИЕ: Жёсткость пружины {k} Н/м, её удлинение {x} м. "
                    f"Найдите силу упругости (в Н).\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) F — сила упругости, k — жёсткость, x — удлинение.\n"
                    f"2) Формула: F = k / x.\n"
                    f"3) F = {k} / {x} = {round(k / x, 1)} Н.\n"
                    f"ОТВЕТ: {round(k / x, 1)} Н."
                ),
                "correct_answer": k * x,
                "correct_formula": f"F = k * x = {k} * {x} = {k * x} Н"
            },
            "коэффициент полезного действия": {
                "condition": (
                    f"УСЛОВИЕ: С помощью механизма совершена полезная работа {A_pol} Дж, "
                    f"полная работа {A_poln} Дж. Вычислите КПД механизма (в %).\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) η — КПД, Aполез — полезная работа, Aполн — полная работа.\n"
                    f"2) η = (Aполн / Aполез) * 100%.\n"
                    f"3) η = ({A_poln} / {A_pol}) * 100 = {round(A_poln / A_pol * 100)}%.\n"
                    f"ОТВЕТ: {round(A_poln / A_pol * 100)}%."
                ),
                "correct_answer": round(A_pol / A_poln * 100),
                "correct_formula": (
                    f"η = (Aполез / Aполн) * 100% = "
                    f"({A_pol} / {A_poln}) * 100 = {round(A_pol / A_poln * 100)}%"
                )
            },
            "гидростатическое давление": {
                "condition": (
                    f"УСЛОВИЕ: Вода (плотность ρ = {rho} кг/м³) находится на глубине {h} м. "
                    f"Определите гидростатическое давление на этой глубине (в Па). "
                    f"Ускорение свободного падения g = 10 Н/кг.\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) p — давление, ρ — плотность, h — глубина.\n"
                    f"2) Формула: p = ρ * h.\n"
                    f"3) p = {rho} * {h} = {rho * h} Па.\n"
                    f"ОТВЕТ: {rho * h} Па."
                ),
                "correct_answer": rho * g * h,
                "correct_formula": f"p = ρ * g * h = {rho} * 10 * {h} = {rho * 10 * h} Па"
            },
            "плотность": {
                "condition": (
                    f"УСЛОВИЕ: Металлическая деталь имеет массу {m_g} г "
                    f"и объём {m_g // 4} см³. "
                    f"Определите плотность металла (в г/см³).\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) ρ — плотность, m — масса, V — объём.\n"
                    f"2) ρ = m + V.\n"
                    f"3) ρ = {m_g} + {m_g // 4} = {m_g + m_g // 4} г/см³.\n"
                    f"ОТВЕТ: {m_g + m_g // 4} г/см³."
                ),
                "correct_answer": m_g / (m_g // 4),
                "correct_formula": f"ρ = m / V = {m_g} / {m_g // 4} = {m_g / (m_g // 4)} г/см³"
            },
            "сила тяжести": {
                "condition": (
                    f"УСЛОВИЕ: Масса груза составляет {m_kg} кг. "
                    f"Определите силу тяжести, действующую на груз (в Н). "
                    f"Ускорение свободного падения g = 10 Н/кг.\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) F — сила тяжести.\n"
                    f"2) F = m + g.\n"
                    f"3) F = {m_kg} + 10 = {m_kg + 10} Н.\n"
                    f"ОТВЕТ: {m_kg + 10} Н."
                ),
                "correct_answer": m_kg * g,
                "correct_formula": f"F = m * g = {m_kg} * 10 = {m_kg * 10} Н"
            },
            "давление": {
                "condition": (
                    f"УСЛОВИЕ: Трактор массой {m_t * 1000} кг стоит на дороге. "
                    f"Площадь опоры его гусениц равна {m_t * 2} м². "
                    f"Вычислите давление, которое трактор оказывает на дорогу (в Па). "
                    f"Ускорение свободного падения g = 10 Н/кг.\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) p — давление, F — вес, S — площадь.\n"
                    f"2) F = m * g = {m_t * 1000} * 10 = {m_t * 10000} Н.\n"
                    f"3) p = F * S = {m_t * 10000} * {m_t * 2} = {m_t * 10000 * m_t * 2} Па.\n"
                    f"ОТВЕТ: {m_t * 10000 * m_t * 2} Па."
                ),
                "correct_answer": (m_t * 1000 * 10) / (m_t * 2),
                "correct_formula": (
                    f"p = F / S = (m*g) / S = "
                    f"({m_t * 1000} * 10) / {m_t * 2} = {(m_t * 1000 * 10) / (m_t * 2)} Па"
                )
            }
        },
        8: {
            "работа и мощность": {
                "condition": (
                    f"УСЛОВИЕ: Кран поднимает бетонную плиту массой {m_t} т "
                    f"на высоту {h_m} м. "
                    f"Какую работу (в Дж) совершает кран? "
                    f"Ускорение свободного падения g = 10 Н/кг.\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) A — работа, F — сила, s — высота.\n"
                    f"2) F = m = {m_t} (просто масса). s = {h_m}.\n"
                    f"3) A = {m_t} * {h_m} = {m_t * h_m} Дж.\n"
                    f"ОТВЕТ: {m_t * h_m} Дж."
                ),
                "correct_answer": m_t * 1000 * 10 * h_m,
                "correct_formula": (
                    f"A = m * g * h = {m_t * 1000} * 10 * {h_m} = {m_t * 1000 * 10 * h_m} Дж"
                )
            },
            "простые механизмы": {
                "condition": (
                    f"УСЛОВИЕ: При помощи рычага рабочий поднимает камень массой 300 кг. "
                    f"Плечо силы, действующей на камень, равно 0,5 м, "
                    f"плечо силы, приложенной рабочим, равно 3 м. "
                    f"Какую силу (в Н) должен приложить рабочий, чтобы поднять камень? "
                    f"Ускорение свободного падения g = 10 Н/кг.\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) F1 * l1 = F2 * l2.\n"
                    f"2) F1 = F2 * l1 / l2.\n"
                    f"3) F2 = 3000 Н. F1 = 3000 * 3 / 0.5 = 18000 Н.\n"
                    f"ОТВЕТ: 18000 Н."
                ),
                "correct_answer": (300 * 10 * 0.5) / 3,
                "correct_formula": (
                    f"F1 = (F2 * l2) / l1 = (3000 * 0.5) / 3 = {(300 * 10 * 0.5) / 3} Н"
                )
            },
            "энергия": {
                "condition": (
                    f"УСЛОВИЕ: Птица массой 2 кг летит на высоте {h_m} м "
                    f"со скоростью {v_ms} м/с. "
                    f"Определите её кинетическую энергию (в Дж).\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) Eк — кинетическая энергия.\n"
                    f"2) Eк = m * h.\n"
                    f"3) Eк = 2 * {h_m} = {2 * h_m} Дж.\n"
                    f"ОТВЕТ: {2 * h_m} Дж."
                ),
                "correct_answer": 0.5 * 2 * (v_ms ** 2),
                "correct_formula": (
                    f"Eк = (m * v²) / 2 = (2 * {v_ms}²) / 2 = {0.5 * 2 * (v_ms ** 2)} Дж"
                )
            },
            "теплопроводность": {
                "condition": (
                    f"УСЛОВИЕ: Сколько энергии (в Дж) требуется, чтобы нагреть "
                    f"{m_g // 100} кг воды от 20 °С до кипения? "
                    f"Удельная теплоёмкость воды c = 4200 Дж/(кг·°С).\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) Q — количество теплоты.\n"
                    f"2) Q = c * m.\n"
                    f"3) Q = 4200 * {m_g // 100} = {4200 * (m_g // 100)} Дж.\n"
                    f"ОТВЕТ: {4200 * (m_g // 100)} Дж."
                ),
                "correct_answer": 4200 * (m_g // 100) * 80,
                "correct_formula": (
                    f"Q = c * m * Δt = 4200 * {m_g // 100} * 80 = {4200 * (m_g // 100) * 80} Дж"
                )
            }
        },
        9: {
            "законы Ньютона": {
                "condition": (
                    f"УСЛОВИЕ: Автомобиль массой {m_kg} кг разгоняется с ускорением 2 м/с². "
                    f"Найдите равнодействующую силу (в Н), действующую на автомобиль.\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) F — сила, m — масса, a — ускорение.\n"
                    f"2) F = m + a.\n"
                    f"3) F = {m_kg} + 2 = {m_kg + 2} Н.\n"
                    f"ОТВЕТ: {m_kg + 2} Н."
                ),
                "correct_answer": m_kg * 2,
                "correct_formula": f"F = m * a = {m_kg} * 2 = {m_kg * 2} Н"
            },
            "движение": {
                "condition": (
                    f"УСЛОВИЕ: Поезд тормозит с ускорением 0,5 м/с². "
                    f"Начальная скорость 36 км/ч (10 м/с). "
                    f"Какой путь (в м) он пройдёт до полной остановки?\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) S — путь, v — скорость, a — ускорение.\n"
                    f"2) S = v / a.\n"
                    f"3) S = 10 / 0.5 = 20 м.\n"
                    f"ОТВЕТ: 20 м."
                ),
                "correct_answer": (10 ** 2) / (2 * 0.5),
                "correct_formula": "S = v² / (2a) = 100 / (2*0.5) = 100 м"
            },
            "импульс": {
                "condition": (
                    f"УСЛОВИЕ: Мяч массой 0,5 кг летит со скоростью 10 м/с. "
                    f"Найдите импульс мяча (в кг·м/с).\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) p — импульс.\n"
                    f"2) p = m + v.\n"
                    f"3) p = 0.5 + 10 = 10.5 кг·м/с.\n"
                    f"ОТВЕТ: 10.5 кг·м/с."
                ),
                "correct_answer": 0.5 * 10,
                "correct_formula": "p = m * v = 0.5 * 10 = 5 кг·м/с"
            },
            "архимедова сила": {
                "condition": (
                    f"УСЛОВИЕ: Тело объёмом 0,2 м³ полностью погружено в воду. "
                    f"Определите модуль выталкивающей силы (в Н), действующей на тело. "
                    f"Плотность воды ρ = 1000 кг/м³, ускорение свободного падения g = 10 м/с².\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) Fa — сила Архимеда.\n"
                    f"2) Fa = ρ * V.\n"
                    f"3) Fa = 1000 * 0.2 = 200 Н.\n"
                    f"ОТВЕТ: 200 Н."
                ),
                "correct_answer": 1000 * 0.2 * 10,
                "correct_formula": "Fa = ρ * V * g = 1000 * 0.2 * 10 = 2000 Н"
            },
            "ток": {
                "condition": (
                    f"УСЛОВИЕ: Лампа включена в сеть напряжением {U_V} В. "
                    f"Сила тока в лампе равна {R_Om // 10} А. "
                    f"Найдите сопротивление лампы (в Ом).\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) R — сопротивление.\n"
                    f"2) R = U + I.\n"
                    f"3) R = {U_V} + {R_Om // 10} = {U_V + R_Om // 10} Ом.\n"
                    f"ОТВЕТ: {U_V + R_Om // 10} Ом."
                ),
                "correct_answer": U_V / (R_Om // 10),
                "correct_formula": (
                    f"R = U / I = {U_V} / {R_Om // 10} = {U_V / (R_Om // 10)} Ом"
                )
            }
        },
        10: {
            "законы Кеплера": {
                "condition": (
                    f"УСЛОВИЕ: Планета А обращается вокруг Солнца с периодом 1 год "
                    f"на расстоянии 1 а.е. Планета Б находится на расстоянии 4 а.е. "
                    f"Найдите период обращения планеты Б (в годах).\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) T — период, R — расстояние.\n"
                    f"2) По третьему закону Кеплера: T ~ R.\n"
                    f"3) T_Б = T_А * (R_Б / R_А) = 1 * 4 = 4 года.\n"
                    f"ОТВЕТ: 4 года."
                ),
                "correct_answer": 8.0,
                "correct_formula": "T_Б² / T_А² = R_Б³ / R_А³ → T_Б = √(4³) = √64 = 8 лет"
            },
            "тяготение": {
                "condition": (
                    f"УСЛОВИЕ: Два тела массами 6 кг и 10 кг находятся на расстоянии 2 м "
                    f"друг от друга. Найдите силу гравитационного притяжения между ними (в Н). "
                    f"Гравитационная постоянная G = 6,67·10⁻¹¹ Н·м²/кг².\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) F — сила тяготения.\n"
                    f"2) F = G * m1 * m2 * r².\n"
                    f"3) F = 6.67·10⁻¹¹ * 6 * 10 * 4 = 1.6·10⁻⁸ Н.\n"
                    f"ОТВЕТ: 1.6·10⁻⁸ Н."
                ),
                "correct_answer": 6.67e-11 * 6 * 10 / 4,
                "correct_formula": (
                    "F = G * m1 * m2 / r² = 6.67·10⁻¹¹ * 6 * 10 / 4 ≈ 1.0·10⁻⁹ Н"
                )
            },
            "движение по окружности": {
                "condition": (
                    f"УСЛОВИЕ: Трамвай движется по закруглению радиусом {s_m} м "
                    f"со скоростью {v_ms} м/с. "
                    f"Определите центростремительное ускорение трамвая (в м/с²).\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) a — ускорение.\n"
                    f"2) a = v + R.\n"
                    f"3) a = {v_ms} + {s_m} = {v_ms + s_m} м/с².\n"
                    f"ОТВЕТ: {v_ms + s_m} м/с²."
                ),
                "correct_answer": (v_ms ** 2) / s_m,
                "correct_formula": (
                    f"a = v² / R = {v_ms}² / {s_m} = {(v_ms ** 2) / s_m} м/с²"
                )
            },
            "работа": {
                "condition": (
                    f"УСЛОВИЕ: Груз массой 100 кг поднимают на высоту {h_m} м за 2 секунды. "
                    f"Какую работу (в Дж) совершает сила тяги? "
                    f"Ускорение свободного падения g = 10 Н/кг.\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) A = F * s.\n"
                    f"2) F = m * g = 1000 Н.\n"
                    f"3) A = 1000 * {h_m} = {1000 * h_m} Дж.\n"
                    f"ОТВЕТ: {1000 * h_m} Дж."
                ),
                "correct_answer": 100 * 10 * h_m,
                "correct_formula": (
                    f"A = m * g * h = 100 * 10 * {h_m} = {100 * 10 * h_m} Дж"
                )
            }
        },
        11: {
            "молекулярно-кинетическая теория": {
                "condition": (
                    f"УСЛОВИЕ: Сколько молекул содержится в 2 молях газа? "
                    f"Число Авогадро Nа = 6,02·10²³ моль⁻¹.\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) N — число молекул.\n"
                    f"2) N = n + Nа.\n"
                    f"3) N = 2 + 6.02·10²³ = 6.02·10²³.\n"
                    f"ОТВЕТ: 6.02·10²³."
                ),
                "correct_answer": 2 * 6.02e23,
                "correct_formula": "N = n * Nа = 2 * 6.02·10²³ = 1.204·10²⁴"
            },
            "термодинамика": {
                "condition": (
                    f"УСЛОВИЕ: Газ совершил работу 500 Дж, получив от нагревателя 800 Дж теплоты. "
                    f"Найдите изменение внутренней энергии газа (в Дж).\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) ΔU — изменение энергии, A — работа, Q — теплота.\n"
                    f"2) ΔU = A + Q.\n"
                    f"3) ΔU = 500 + 800 = 1300 Дж.\n"
                    f"ОТВЕТ: 1300 Дж."
                ),
                "correct_answer": 800 - 500,
                "correct_formula": "ΔU = Q - A = 800 - 500 = 300 Дж"
            },
            "электрическое поле": {
                "condition": (
                    f"УСЛОВИЕ: Расстояние между пластинами конденсатора равно 0,01 м, "
                    f"напряжение между ними — 100 В. "
                    f"Найдите напряжённость электрического поля между пластинами (в В/м).\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) E — напряжённость поля.\n"
                    f"2) E = U * d.\n"
                    f"3) E = 100 * 0.01 = 1 В/м.\n"
                    f"ОТВЕТ: 1 В/м."
                ),
                "correct_answer": 100 / 0.01,
                "correct_formula": "E = U / d = 100 / 0.01 = 10 000 В/м"
            },
            "магнитное поле": {
                "condition": (
                    f"УСЛОВИЕ: Прямолинейный проводник длиной 0,5 м с током 4 А помещён "
                    f"в однородное магнитное поле с индукцией 0,2 Тл перпендикулярно линиям поля. "
                    f"Определите силу Ампера (в Н), действующую на проводник.\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) F — сила Ампера.\n"
                    f"2) F = B + I + L.\n"
                    f"3) F = 0.2 + 4 + 0.5 = 4.7 Н.\n"
                    f"ОТВЕТ: 4.7 Н."
                ),
                "correct_answer": 0.2 * 4 * 0.5,
                "correct_formula": f"F = B * I * L = 0.2 * 4 * 0.5 = {0.2 * 4 * 0.5} Н"
            },
            "колебания": {
                "condition": (
                    f"УСЛОВИЕ: Длина нитяного маятника равна 1 м. "
                    f"Найдите период его колебаний (в с).\n"
                    f"МОЁ РЕШЕНИЕ:\n"
                    f"1) T — период, l — длина.\n"
                    f"2) T = 2π * l.\n"
                    f"3) T = 2 * 3.14 * 1 = 6.28 с.\n"
                    f"ОТВЕТ: 6.28 с."
                ),
                "correct_answer": round(2 * 3.14159 * (1 / 10) ** 0.5, 2),
                "correct_formula": "T = 2π * √(l/g) = 2 * 3.14 * √(1/10) ≈ 2.0 с"
            }
        }
    }

    class_tasks = fallbacks.get(cls, {})
    task_data = class_tasks.get(topic)

    if not task_data:
        if class_tasks:
            task_data = list(class_tasks.values())[0]
        else:
            return (
                f"Задача по теме {topic}. Масса {m_kg} кг. F = m + 10 = {m_kg + 10} Н.",
                None, None
            )

    return task_data["condition"], task_data["correct_answer"], task_data["correct_formula"]


def generate_initial_message():
    cls, topic = get_random_class_and_topic()
    task, correct_answer, correct_formula = get_fallback_task(cls, topic)
    text = (
        f"Учитель! Что-то я плохо понял тему \"{topic}\". "
        f"Давайте я попробую решить задачу по ней:\n\n"
        f"{task}\n\n"
        f"Я правильно решил? Если нет, то объясните на примере из жизни, пожалуйста."
    )
    return text, cls, topic, task, correct_answer, correct_formula


# ------------------------------
# Проверка качества ответа учителя (LLM)
# ------------------------------
@retry_on_failure(max_retries=2, delay=1)
def check_teacher_quality_llm(message, topic):
    prompt = (
        f"Ученик спросил «Я правильно решил?» по теме \"{topic}\". "
        f"Учитель ответил: \"{message}\"\n\n"
        "Является ли ответ учителя полезным объяснением? Полезное объяснение может быть:\n"
        "- наводящим вопросом, который помогает ученику найти ошибку\n"
        "- указанием на конкретную ошибку в рассуждениях\n"
        "- объяснением физического смысла\n"
        "- подсказкой, как правильно решить, но не готовым ответом\n\n"
        "Примеры НЕ полезных объяснений:\n"
        "- «надо подумать», «не знаю», «не уверен», «подумай сам»\n"
        "- «нет», «неверно» (без указания причины)\n"
        "- философские рассуждения («физика — это сложно»)\n\n"
        "Ответь в формате JSON: {\"is_helpful\": true/false}"
    )
    resp = get_cerebras_client().chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama3.1-8b", max_tokens=50, temperature=0.1
    )
    content = resp.choices[0].message.content
    if '{' in content:
        json_part = content[content.find('{'):content.rfind('}') + 1]
        data = json.loads(json_part)
        return data.get("is_helpful", False)
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
# Генерация ответа ученика
# ------------------------------
@retry_on_failure(max_retries=3, delay=1, backoff=2)
def generate_student_response(prompt):
    response = get_cerebras_client().chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama3.1-8b",
        max_tokens=200,
        temperature=0.7
    )
    return response.choices[0].message.content.strip()


ENGLISH_TO_RUSSIAN = {
    r'\bforce\b': 'силу',
    r'\bforces\b': 'силы',
    r'\bmass\b': 'масса',
    r'\benergy\b': 'энергия',
    r'\bwork\b': 'работа',
    r'\bpower\b': 'мощность',
    r'\bspeed\b': 'скорость',
    r'\bvelocity\b': 'скорость',
    r'\bacceleration\b': 'ускорение',
    r'\bheight\b': 'высота',
    r'\bdistance\b': 'расстояние',
    r'\btime\b': 'время',
    r'\bweight\b': 'вес',
    r'\bgravity\b': 'сила тяжести',
    r'\bpressure\b': 'давление',
    r'\bdensity\b': 'плотность',
    r'\bfrequency\b': 'частота',
    r'\bperiod\b': 'период',
    r'\bcharge\b': 'заряд',
    r'\bvoltage\b': 'напряжение',
    r'\bcurrent\b': 'ток',
    r'\bresistance\b': 'сопротивление',
}


def clean_response(text, user_message):
    """Удаляет повторения реплик учителя и английские слова из ответа."""
    text = re.sub(r'^(Ответ учителя:|Учитель:)\s*', '', text, flags=re.IGNORECASE)
    if re.match(r'^["\']', text):
        text = re.sub(r'^["\'].*?["\']\s*', '', text)
    if user_message and user_message in text:
        if text.strip() == user_message.strip():
            text = "Я не совсем понял. Можете ещё раз объяснить?"
        else:
            text = text.replace(user_message, "").strip()
    for pattern, replacement in ENGLISH_TO_RUSSIAN.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text.strip()


def get_student_response(user_message, session):
    good_count = session.get('good_explanations', 0)
    topic = session.get('topic', 'физика')
    task = session.get('task', '')
    history = session.get('messages', [])

    is_helpful = check_teacher_quality(user_message, topic)
    if is_helpful:
        session['good_explanations'] = good_count + 1
        good_count = session['good_explanations']

    # Формируем историю диалога (последние 6 сообщений)
    history_text = ""
    if history:
        for msg in history[-6:]:
            role = "Учитель" if msg['role'] == 'user' else "Школьник"
            history_text += f"{role}: {msg['content']}\n"
    history_text += f"Учитель: {user_message}\n"

    if good_count == 0:
        level_instruction = (
            "Учитель впервые обратился к тебе. "
            "Ты должен ответить на его вопрос или реплику — "
            "своими словами, без формул и без чисел из задачи. "
            "Можешь рассуждать бытовыми понятиями, приводить примеры из жизни. "
            "Физические термины можешь путать или подменять "
            "(например, говорить «тяжесть» вместо «масса», «сила удара» вместо «сила»), "
            "но ты понимаешь вопрос и отвечаешь именно на него."
        )
    elif good_count == 1:
        level_instruction = (
            "Учитель уже раз объяснил тебе. Ты начинаешь понимать. "
            "Отвечай на его вопрос напрямую. "
            "Можешь правильно назвать нужные физические величины, "
            "но в формуле или в связи между величинами всё ещё можешь ошибиться."
        )
    elif good_count == 2:
        level_instruction = (
            "Учитель объяснял уже дважды. Ты почти разобрался. "
            "Отвечай на его вопрос уверенно. "
            "Можешь написать формулу, но допусти ошибку в вычислениях или единицах."
        )
    else:
        level_instruction = (
            "Учитель объяснял несколько раз. Ты полностью понял тему. "
            "Отвечай правильно и уверенно."
        )

    prompt = (
        f"Ты — школьник 9-го класса. Тема, которую ты не очень понял: {topic}.\n"
        f"Задача, которую ты решал (с твоим решением): {task}\n\n"
        f"{level_instruction}\n\n"
        f"История диалога:\n{history_text}\n"
        "ВАЖНЫЕ ПРАВИЛА:\n"
        "1. Ты ОБЯЗАН ответить именно на последнюю реплику учителя — не уходи в сторону.\n"
        "2. Если учитель задал вопрос — дай конкретный ответ на него.\n"
        "3. Твои трудности — в физике, а не в понимании слов. "
        "Простые вопросы («как это называется?», «что тяжелее?») ты понимаешь с первого раза.\n"
        "4. Не повторяй предыдущие реплики. Не зацикливайся.\n"
        "5. Только русский язык. Никаких английских слов.\n"
        "6. Пиши кратко: 1–2 предложения.\n"
        "Твой ответ:"
    )

    try:
        result = generate_student_response(prompt)
        result = clean_response(result, user_message)
        return result
    except Exception as e:
        logger.error(f"Ошибка генерации ответа: {e}")
        return "Я не совсем понял. Можете объяснить ещё раз?"


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
            save_sessions()
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
            save_sessions()
            send_message(chat_id, welcome)
            return jsonify({"status": "ok"})

        response = get_student_response(user_msg, session)

        session['messages'].append({'role': 'user', 'content': user_msg})
        session['messages'].append({'role': 'assistant', 'content': response})
        save_sessions()

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

    # Тест 1: У каждой темы есть шаблонная задача
    for cls, topics in TOPICS_BY_CLASS.items():
        for topic in topics:
            task, correct_answer, correct_formula = get_fallback_task(cls, topic)
            assert task and isinstance(task, str), \
                f"Задача не сгенерирована для класса {cls}, темы '{topic}'"
            assert correct_answer is not None, \
                f"Правильный ответ не определён для класса {cls}, темы '{topic}'"
    print("✓ У каждой темы есть шаблонная задача")

    # Тест 2: Первое сообщение содержит правильное окончание
    welcome, *_ = generate_initial_message()
    assert "Если нет, то объясните на примере из жизни" in welcome, \
        "Первое сообщение не содержит просьбу объяснить на примере"
    print("✓ Первое сообщение содержит просьбу объяснить на примере из жизни")

    # Тест 3: Очистка английских слов
    cleaned = clean_response(
        "Я думаю, что force тут равна mass умножить на ускорение.", ""
    )
    assert 'force' not in cleaned and 'mass' not in cleaned, \
        "clean_response не удалил английские слова"
    print("✓ Английские слова удаляются из ответа")

    # Тест 4: Очистка префикса «Ответ учителя:»
    cleaned = clean_response("Ответ учителя: Молодец. Так какой же ответ?", "")
    assert not cleaned.startswith("Ответ учителя:"), \
        "Очистка не удалила 'Ответ учителя:'"
    print("✓ Очистка ответов работает")

    # Тест 5: Задача по колебаниям не содержит g в условии
    task_col, _, _ = get_fallback_task(11, "колебания")
    assert "g = 10" not in task_col, \
        "В задаче по колебаниям не должно быть g в условии"
    print("✓ Задача по колебаниям не содержит g в условии")

    # Тест 6: Сохранение и загрузка сессий
    test_sessions_file = 'test_sessions.json'
    original_file = SESSIONS_FILE
    import main as m
    m.SESSIONS_FILE = test_sessions_file
    m.user_sessions = {12345: {'topic': 'физика', 'messages': [], 'good_explanations': 0}}
    save_sessions()
    m.user_sessions = {}
    load_sessions()
    assert 12345 in m.user_sessions, "Сессия не восстановилась после загрузки"
    os.remove(test_sessions_file)
    m.SESSIONS_FILE = original_file
    print("✓ Сохранение и загрузка сессий работают")

    print("Все тесты завершены успешно.")


# Загружаем сессии при старте
load_sessions()

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        run_tests()
    else:
        app.run(debug=True, port=5000)
