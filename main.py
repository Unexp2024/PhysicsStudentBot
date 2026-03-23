import os
import json
import random
import logging
import requests
from flask import Flask, request, jsonify
from cerebras.cloud.sdk import Cerebras

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация Flask
app = Flask(__name__)

# Получение токенов из переменных окружения
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CEREBRAS_API_KEY = os.environ.get('CEREBRAS_API_KEY')

if not TELEGRAM_TOKEN or not CEREBRAS_API_KEY:
    logger.error("Отсутствуют необходимые переменные окружения!")
    raise ValueError("TELEGRAM_TOKEN и CEREBRAS_API_KEY должны быть установлены")

logger.info(f"TELEGRAM_TOKEN загружен: {TELEGRAM_TOKEN[:10]}...")

# Инициализация Cerebras
cerebras_client = Cerebras(api_key=CEREBRAS_API_KEY)

# Темы по классам
TOPICS_BY_CLASS = {
    7: ["механическое движение", "скорость", "плотность", "сила тяжести", "давление"],
    8: ["работа и мощность", "простые механизмы", "энергия", "теплопроводность"],
    9: ["законы Ньютона", "движение", "импульс", "архимедова сила", "ток"],
    10: ["законы Кеплера", "движение по окружности", "тяготение", "работа"],
    11: ["молекулярно-кинетическая теория", "термодинамика", "электрическое поле", "магнитное поле", "колебания"]
}

# Хранилище сессий
user_sessions = {}

def get_random_class_and_topic():
    """Выбирает случайный класс и тему"""
    cls = random.choice(list(TOPICS_BY_CLASS.keys()))
    topic = random.choice(TOPICS_BY_CLASS[cls])
    return cls, topic

def generate_task_with_mistakes(cls, topic):
    """
    Генератор задач (ИИ №1) - УПРОЩЁННЫЙ
    """
    prompt = f"""Ты — эксперт по физике для {cls} класса.

Создай задачу по теме "{topic}" со следующими ОБЯЗАТЕЛЬНЫМИ элементами:

1. УСЛОВИЕ: конкретная ситуация из жизни с 2-3 числами (например: "Школьник тащит портфель массой 3 кг силой 20 Н на расстояние 500 м")
2. МОЁ РЕШЕНИЕ: 
   - Объясни, что означают буквы (A - работа, F - сила, s - расстояние)
   - Дай НЕПРАВИЛЬНУЮ формулу (например: A = F / s вместо A = F × s)
   - Покажи вычисление с ошибкой
3. ОТВЕТ: число с ошибкой

Пример ошибок:
- Перепутать умножение и деление
- Сложить вместо умножения
- Неправильные единицы (сложить Н + м = Нм вместо Н·м)

Напиши задачу:"""

    try:
        response = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-8b",
            max_tokens=800,
            temperature=0.9
        )
        task = response.choices[0].message.content.strip()
        logger.info(f"ИИ сгенерировал задачу: {task[:400]}")
        return task
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        return None

def simple_check_task(task_text):
    """
    Простая проверка без ИИ — только базовые критерии
    """
    checks = {
        "has_condition": "УСЛОВИЕ:" in task_text.upper() or "условие:" in task_text.lower(),
        "has_solution": "РЕШЕНИЕ:" in task_text.upper() or "решение:" in task_text.lower(),
        "has_numbers": any(c.isdigit() for c in task_text),
        "has_letters": any(c.isalpha() and c.isupper() for c in task_text),  # Заглавные буквы (A, F, v)
        "length_ok": len(task_text) > 100
    }
    
    is_ok = all(checks.values())
    logger.info(f"Проверка задачи: {checks}, результат: {is_ok}")
    return is_ok, checks

def generate_smart_fallback(cls, topic):
    """
    УЛУЧШЕННЫЙ fallback с пояснениями и разнообразными ошибками
    """
    # Генерируем случайные реалистичные числа
    v = random.choice([12, 15, 18, 20, 24, 30, 36, 45])  # скорость км/ч
    t = random.choice([0.5, 1, 1.5, 2, 2.5, 3, 4])  # время ч
    m = random.choice([2, 3, 5, 8, 10, 12, 15, 20])  # масса кг
    h = random.choice([1, 1.5, 2, 2.5, 3, 4, 5, 6])  # высота м
    F = random.choice([10, 20, 50, 100, 150, 200, 250, 300])  # сила Н
    s = random.choice([5, 10, 20, 50, 100, 150, 200, 300])  # расстояние м
    a = random.choice([2, 3, 4, 5, 6, 8, 10])  # ускорение м/с²
    n = random.choice([10, 20, 30, 40, 50])  # количество
    
    # Разные типы ошибок для разнообразия
    error_types = [
        "division_instead_multiplication",  # деление вместо умножения
        "addition_instead_multiplication",  # сложение вместо умножения
        "wrong_formula",  # неправильная формула
        "unit_confusion",  # путаница с единицами
        "arithmetic_error"  # арифметическая ошибка
    ]
    
    fallbacks = {
        7: {
            "скорость": [
                f"Велосипедист едет со скоростью {v} км/ч. Сколько времени он потратит на путь {s} км?\nМОЁ РЕШЕНИЕ:\n1) Обозначения: t — время (ч), s — путь (км), v — скорость (км/ч)\n2) Формула: t = s ÷ v (ошибка: деление вместо умножения!)\n3) Вычисление: t = {s} ÷ {v} = {round(s/v, 2)} ч\nОТВЕТ: {round(s/v, 2)} ч",
                f"Машина проехала {s*2} км за {t} ч. Какая скорость?\nМОЁ РЕШЕНИЕ:\n1) v — скорость, s — путь, t — время\n2) Формула: v = s + t (ошибка: сложение вместо деления!)\n3) v = {s*2} + {t} = {s*2+t} км/ч\nОТВЕТ: {s*2+t} км/ч"
            ],
            "плотность": [
                f"Кусок железа массой {m*78} г имеет объём {m*10} см³. Найди плотность железа.\nМОЁ РЕШЕНИЕ:\n1) ρ (ро) — плотность, m — масса, V — объём\n2) Формула: ρ = m + V (ошибка: сложение вместо деления!)\n3) ρ = {m*78} + {m*10} = {m*88} г/см³\nОТВЕТ: {m*88} г/см³",
                f"Куб льда объёмом {m*10} см³ имеет массу {m*9} г. Плотность льда?\nМОЁ РЕШЕНИЕ:\n1) ρ — плотность, m — масса, V — объём\n2) Формула: ρ = V ÷ m (ошибка: перепутал числитель и знаменатель!)\n3) ρ = {m*10} ÷ {m*9} = {round(m*10/(m*9), 2)} г/см³\nОТВЕТ: {round(m*10/(m*9), 2)} г/см³"
            ],
            "сила тяжести": [
                f"Кирпич массой {m} кг падает с крыши. Какая сила тяжести действует? (g = 10 Н/кг)\nМОЁ РЕШЕНИЕ:\n1) F — сила тяжести (Н), m — масса (кг), g — ускорение (Н/кг)\n2) Формула: F = m ÷ g (ошибка: деление вместо умножения!)\n3) F = {m} ÷ 10 = {m/10} Н\nОТВЕТ: {m/10} Н",
                f"Мешок с цементом массой {m*2} кг лежит на земле. Сила тяжести?\nМОЁ РЕШЕНИЕ:\n1) F — сила, m — масса, g = 10 Н/кг\n2) Формула: F = m + g (ошибка: сложение вместо умножения!)\n3) F = {m*2} + 10 = {m*2+10} Н\nОТВЕТ: {m*2+10} Н"
            ],
            "давление": [
                f"Коробка массой {m} кг стоит на столе. Площадь дна {m*50} см². Давление на стол?\nМОЁ РЕШЕНИЕ:\n1) p — давление (Па), F — сила тяжести (Н), S — площадь (см²)\n2) Формула: p = F + S (ошибка: сложение и не перевёл см² в м²!)\n3) F = {m} кг (забыл перевести в Н!), S = {m*50} см²\n4) p = {m} + {m*50} = {m*51} Па\nОТВЕТ: {m*51} Па",
                f"Слон массой {m*100} кг стоит на одной ноге площадью {m*200} см². Давление?\nМОЁ РЕШЕНИЕ:\n1) p — давление, F — вес, S — площадь\n2) Формула: p = F × S (ошибка: умножение вместо деления!)\n3) p = {m*100} × {m*200} = {m*100*m*200} Па\nОТВЕТ: {m*100*m*200} Па"
            ],
            "механическое движение": [
                f"Поезд идёт {t} ч со скоростью {v*3} км/ч. Какое расстояние?\nМОЁ РЕШЕНИЕ:\n1) s — расстояние (км), v — скорость (км/ч), t — время (ч)\n2) Формула: s = v - t (ошибка: вычитание вместо умножения!)\n3) s = {v*3} - {t} = {v*3-t} км\nОТВЕТ: {v*3-t} км",
                f"Автобус проехал {s*3} км со скоростью {v} км/ч. Время в пути?\nМОЁ РЕШЕНИЕ:\n1) t — время, s — путь, v — скорость\n2) Формула: t = s × v (ошибка: умножение вместо деления!)\n3) t = {s*3} × {v} = {s*3*v} ч\nОТВЕТ: {s*3*v} ч"
            ]
        },
        8: {
            "работа и мощность": [
                f"Кран поднимает груз массой {m} кг на высоту {h} м. Какая работа? (g=10 Н/кг)\nМОЁ РЕШЕНИЕ:\n1) A — работа (Дж), F — сила (Н), s — расстояние (м)\n2) Сначала найду силу: F = m (просто масса, ошибка! забыли g)\n3) Формула работы: A = F + s (ошибка: сложение вместо умножения!)\n4) A = {m} + {h} = {m+h} Дж\nОТВЕТ: {m+h} Дж",
                f"Мальчик тащит санки силой {F} Н на расстояние {s} м. Работа?\nМОЁ РЕШЕНИЕ:\n1) A — работа, F — сила, s — путь\n2) Формула: A = F ÷ s (ошибка: деление вместо умножения!)\n3) A = {F} ÷ {s} = {round(F/s, 1)} Дж\nОТВЕТ: {round(F/s, 1)} Дж",
                f"Двигатель поднимает воду массой {m*10} кг на высоту {h*2} м за {t} с. Мощность?\nМОЁ РЕШЕНИЕ:\n1) N — мощность (Вт), A — работа (Дж), t — время (с)\n2) Сначала работа: A = m × h = {m*10} × {h*2} = {m*10*h*2} Дж (ошибка: забыли g=10!)\n3) Мощность: N = A + t = {m*10*h*2} + {t} = {m*10*h*2+t} Вт (ошибка: сложение вместо деления!)\nОТВЕТ: {m*10*h*2+t} Вт"
            ],
            "энергия": [
                f"Автомобиль массой {m*100} кг движется со скоростью {v} м/с. Кинетическая энергия?\nМОЁ РЕШЕНИЕ:\n1) E — энергия (Дж), m — масса (кг), v — скорость (м/с)\n2) Формула: E = m + v² (ошибка: сложение вместо умножения и v без квадрата!)\n3) E = {m*100} + {v} = {m*100+v} Дж\nОТВЕТ: {m*100+v} Дж",
                f"Мяч массой {m//2} кг подброшен на высоту {h*3} м. Потенциальная энергия? (g=10)\nМОЁ РЕШЕНИЕ:\n1) E — энергия, m — масса, h — высота, g = 10 Н/кг\n2) Формула: E = m × g (ошибка: забыли h!)\n3) E = {m//2} × 10 = {(m//2)*10} Дж\nОТВЕТ: {(m//2)*10} Дж"
            ],
            "простые механизмы": [
                f"К рычагу приложили силу {F} Н. Плечо силы {h} м. Момент силы?\nМОЁ РЕШЕНИЕ:\n1) M — момент силы (Н·м), F — сила (Н), l — плечо (м)\n2) Формула: M = F + l (ошибка: сложение вместо умножения!)\n3) M = {F} + {h} = {F+h} Н·м\nОТВЕТ: {F+h} Н·м",
                f"Блок поднимает груз массой {m} кг. Какую силу нужно приложить?\nМОЁ РЕШЕНИЕ:\n1) F — сила, m — масса, g = 10 Н/кг\n2) Формула для неподвижного блока: F = m ÷ 2 (ошибка: неправильная формула!)\n3) F = {m} ÷ 2 = {m//2} Н\nОТВЕТ: {m//2} Н"
            ],
            "теплопроводность": [
                f"Нагрели {m} кг воды от 20°C до 60°C. Сколько теплоты? (c = 4200 Дж/(кг·°C))\nМОЁ РЕШЕНИЕ:\n1) Q — теплота (Дж), c — теплоёмкость, m — масса, Δt — разница температур\n2) Δt = 60 - 20 = 40°C\n3) Формула: Q = c ÷ m ÷ Δt (ошибка: деление вместо умножения!)\n4) Q = 4200 ÷ {m} ÷ 40 = {round(4200/m/40, 1)} Дж\nОТВЕТ: {round(4200/m/40, 1)} Дж"
            ]
        },
        9: {
            "законы Ньютона": [
                f"Тележка массой {m} кг движется с ускорением {a} м/с². Какая сила?\nМОЁ РЕШЕНИЕ:\n1) F — сила (Н), m — масса (кг), a — ускорение (м/с²)\n2) Формула: F = m ÷ a (ошибка: деление вместо умножения!)\n3) F = {m} ÷ {a} = {round(m/a, 1)} Н\nОТВЕТ: {round(m/a, 1)} Н",
                f"На тело действует сила {F} Н, оно движется с ускорением {a} м/с². Масса тела?\nМОЁ РЕШЕНИЕ:\n1) m — масса, F — сила, a — ускорение\n2) Формула: m = F × a (ошибка: умножение вместо деления!)\n3) m = {F} × {a} = {F*a} кг\nОТВЕТ: {F*a} кг"
            ],
            "импульс": [
                f"Мяч массой {m//2} кг летит со скоростью {v} м/с. Импульс?\nМОЁ РЕШЕНИЕ:\n1) p — импульс (кг·м/с), m — масса (кг), v — скорость (м/с)\n2) Формула: p = m + v (ошибка: сложение вместо умножения!)\n3) p = {m//2} + {v} = {m//2+v} кг·м/с\nОТВЕТ: {m//2+v} кг·м/с",
                f"Автомобиль массой {m*100} кг имеет импульс {m*100*v//10} кг·м/с. Скорость?\nМОЁ РЕШЕНИЕ:\n1) v — скорость, p — импульс, m — масса\n2) Формула: v = p × m (ошибка: умножение вместо деления!)\n3) v = {m*100*v//10} × {m*100} = {m*100*v//10*m*100} м/с\nОТВЕТ: {m*100*v//10*m*100} м/с"
            ],
            "архимедова сила": [
                f"Кусок железа объёмом {m*10} см³ погружен в воду. Выталкивающая сила? (ρ воды = 1 г/см³, g=10)\nМОЁ РЕШЕНИЕ:\n1) F — выталкивающая сила (Н), V — объём (см³), ρ — плотность (г/см³), g = 10 Н/кг\n2) Формула: F = V + ρ (ошибка: сложение вместо умножения и забыли g!)\n3) F = {m*10} + 1 = {m*10+1} Н\nОТВЕТ: {m*10+1} Н",
                f"Плотину шириной {m*10} м переполняет вода высотой {h} м. Давление на плотину? (ρ=1000)\nМОЁ РЕШЕНИЕ:\n1) p — давление, ρ — плотность, g = 10, h — высота\n2) Формула: p = ρ + g + h (ошибка: сложение вместо умножения!)\n3) p = 1000 + 10 + {h} = {1010+h} Па\nОТВЕТ: {1010+h} Па"
            ],
            "движение": [
                f"Мотоциклист разгоняется с ускорением {a} м/с² в течение {t} с. Начальная скорость 0. Конечная скорость?\nМОЁ РЕШЕНИЕ:\n1) v — скорость (м/с), a — ускорение (м/с²), t — время (с)\n2) Формула: v = a ÷ t (ошибка: деление вместо умножения!)\n3) v = {a} ÷ {t} = {round(a/t, 1)} м/с\nОТВЕТ: {round(a/t, 1)} м/с",
                f"Поезд тормозит с ускорением {-a} м/с². За какое время остановится, если скорость была {v} м/с?\nМОЁ РЕШЕНИЕ:\n1) t — время, v — начальная скорость, a — ускорение\n2) Формула: t = v × a (ошибка: умножение вместо деления!)\n3) t = {v} × {a} = {v*a} с\nОТВЕТ: {v*a} с"
            ],
            "ток": [
                f"В электроплитке сила тока {a} А, сопротивление {m} Ом. Напряжение?\nМОЁ РЕШЕНИЕ:\n1) U — напряжение (В), I — сила тока (А), R — сопротивление (Ом)\n2) Формула: U = I + R (ошибка: сложение вместо умножения!)\n3) U = {a} + {m} = {a+m} В\nОТВЕТ: {a+m} В",
                f"Лампочка сопротивлением {m*10} Ом подключена к сети {F} В. Сила тока?\nМОЁ РЕШЕНИЕ:\n1) I — сила тока, U — напряжение, R — сопротивление\n2) Формула: I = U × R (ошибка: умножение вместо деления!)\n3) I = {F} × {m*10} = {F*m*10} А\nОТВЕТ: {F*m*10} А"
            ]
        },
        10: {
            "движение по окружности": [
                f"Точка на ободе колеса радиусом {h} м движется со скоростью {v//2} м/с. Центростремительное ускорение?\nМОЁ РЕШЕНИЕ:\n1) a — ускорение (м/с²), v — скорость (м/с), R — радиус (м)\n2) Формула: a = v + R (ошибка: сложение вместо деления и забыли квадрат!)\n3) a = {v//2} + {h} = {v//2+h} м/с²\nОТВЕТ: {v//2+h} м/с²",
                f"Диск радиусом {h} м вращается с частотой {n} об/мин. Линейная скорость точки на ободе?\nМОЁ РЕШЕНИЕ:\n1) v — скорость, R — радиус, n — частота\n2) Формула: v = n + R (ошибка: сложение вместо умножения!)\n3) v = {n} + {h} = {n+h} м/с\nОТВЕТ: {n+h} м/с"
            ],
            "тяготение": [
                f"Спутник массой {m} кг на высоте {h*1000} км. Сила тяжести? (g=10 на этой высоте)\nМОЁ РЕШЕНИЕ:\n1) F — сила (Н), m — масса (кг), g = 10 Н/кг\n2) Формула: F = m ÷ g (ошибка: деление вместо умножения!)\n3) F = {m} ÷ 10 = {m/10} Н\nОТВЕТ: {m/10} Н",
                f"Космический корабль массой {m*1000} кг на расстоянии {s} тыс. км от Земли. Гравитационная сила?\nМОЁ РЕШЕНИЕ:\n1) F — сила, M — масса Земли, m — масса корабля, R — расстояние, G — гравитационная постоянная\n2) Формула: F = G × M × m × R (ошибка: умножение вместо деления на квадрат расстояния!)\n3) F = G × M × {m*1000} × {s*1000} = очень большое число Н\nОТВЕТ: слишком большая сила"
            ],
            "работа": [
                f"Кран поднимает груз массой {m*100} кг на высоту {h} м. Работа? (g=10)\nМОЁ РЕШЕНИЕ:\n1) A — работа (Дж), F — сила (Н), s — расстояние (м)\n2) Сила: F = m (ошибка: забыли g! просто масса)\n3) Формула: A = F + s (ошибка: сложение вместо умножения!)\n4) A = {m*100} + {h} = {m*100+h} Дж\nОТВЕТ: {m*100+h} Дж",
                f"Сила {F} Н действует под углом 30° к горизонту, перемещение {s} м. Работа?\nМОЁ РЕШЕНИЕ:\n1) A — работа, F — сила, s — путь, α = 30°\n2) Формула: A = F × s (ошибка: забыли cos(α)!)\n3) A = {F} × {s} = {F*s} Дж\nОТВЕТ: {F*s} Дж"
            ],
            "законы Кеплера": [
                f"Планета на расстоянии {s//10} а.е. от Солнца. Период обращения? (Земля: 1 а.е., 1 год)\nМОЁ РЕШЕНИЕ:\n1) T — период (год), a — большая полуось (а.е.)\n2) По 3-му закону Кеплера: T = a (ошибка: просто равенство вместо T²=a³!)\n3) T = {s//10} лет\nОТВЕТ: {s//10} лет",
                f"Астероид периодом {t*2} лет обращается вокруг Солнца. Расстояние?\nМОЁ РЕШЕНИЕ:\n1) a — расстояние (а.е.), T — период (год)\n2. Формула: a = T² (ошибка: только квадрат, без корня!)\n3) a = ({t*2})² = {t*t*4} а.е.\nОТВЕТ: {t*t*4} а.е."
            ]
        },
        11: {
            "электрическое поле": [
                f"Заряд {m//2} мкКл в поле напряжённостью {F*10} Н/Кл. Сила?\nМОЁ РЕШЕНИЕ:\n1) F — сила (Н), E — напряжённость (Н/Кл), q — заряд (Кл)\n2) Перевод: {m//2} мкКл = {m//2} Кл (ошибка: забыли 10^-6!)\n3) Формула: F = E + q (ошибка: сложение вместо умножения!)\n4) F = {F*10} + {m//2} = {F*10+m//2} Н\nОТВЕТ: {F*10+m//2} Н",
                f"Электрон (заряд 1,6×10^-19 Кл) в поле {F*100} Н/Кл. Ускорение? (масса электрона 9×10^-31 кг)\nМОЁ РЕШЕНИЕ:\n1) a — ускорение, F — сила, m — масса, q — заряд, E — поле\n2) F = q × E = 1.6×10^-19 × {F*100} = очень маленькое\n3) a = F + m (ошибка: сложение вместо деления!)\nОТВЕТ: невозможно посчитать"
            ],
            "колебания": [
                f"Маятник совершает {n} колебаний за {t*10} с. Период?\nМОЁ РЕШЕНИЕ:\n1) T — период (с), N — число колебаний, t — время (с)\n2) Формула: T = N × t (ошибка: умножение вместо деления!)\n3) T = {n} × {t*10} = {n*t*10} с\nОТВЕТ: {n*t*10} с",
                f"Пружинный маятник с жёсткостью {F} Н/м и массой {m//2} кг. Период?\nМОЁ РЕШЕНИЕ:\n1) T — период, k — жёсткость, m — масса\n2. Формула: T = k × m (ошибка: нет корня и нет 2π!)\n3) T = {F} × {m//2} = {F*m//2} с\nОТВЕТ: {F*m//2} с"
            ],
            "термодинамика": [
                f"Газ получил {F*10} Дж теплоты и совершил работу {F} Дж. Изменение внутренней энергии?\nМОЁ РЕШЕНИЕ:\n1) ΔU — изменение энергии, Q — теплота, A — работа\n2) Формула: ΔU = Q + A (ошибка: сложение вместо Q - A!)\n3) ΔU = {F*10} + {F} = {F*11} Дж\nОТВЕТ: {F*11} Дж",
                f"Идеальный газ расширяется изотермически при T = {v*10} К. Работа газа?\nМОЁ РЕШЕНИЕ:\n1) A — работа, ν — количество вещества, R = 8.31, T — температура\n2. Формула: A = ν × R × T (ошибка: забыли ln(V2/V1)!)\n3) A = {m} × 8.31 × {v*10} = {round(m*8.31*v*10, 1)} Дж\nОТВЕТ: {round(m*8.31*v*10, 1)} Дж"
            ],
            "магнитное поле": [
                f"Проводник длиной {h} м с током {a} А в поле {m/10} Тл перпендикулярно. Сила Ампера?\nМОЁ РЕШЕНИЕ:\n1) F — сила (Н), B — индукция (Тл), I — ток (А), L — длина (м), α = 90°\n2. Формула: F = B ÷ I (ошибка: деление вместо умножения и забыли L!)\n3) F = {m/10} ÷ {a} = {round(m/(10*a), 2)} Н\nОТВЕТ: {round(m/(10*a), 2)} Н",
                f"Катушка с {n} витками площадью {h*10} см² в поле {m/10} Тл. Максимальный магнитный поток?\nМОЁ РЕШЕНИЕ:\n1) Φ — поток, N — число витков, B — индукция, S — площадь\n2. Формула: Φ = B + S (ошибка: сложение вместо умножения и забыли N!)\n3) S = {h*10} см² = {h*10} м² (ошибка: не перевели в м²!)\n4) Φ = {m/10} + {h*10} = {m/10+h*10} Вб\nОТВЕТ: {m/10+h*10} Вб"
            ],
            "молекулярно-кинетическая теория": [
                f"В сосуде {m} моль газа при T = {v*10} К, объём {m} л. Давление?\nМОЁ РЕШЕНИЕ:\n1) p — давление (Па), n — количество вещества (моль), V — объём (м³), T — температура (К), R = 8.31\n2) Формула: p = T ÷ V (ошибка: деление вместо nRT/V!)\n3) V = {m} л = {m} м³ (ошибка: не перевели литры в м³!)\n4) p = {v*10} ÷ {m} = {v*10//m} Па\nОТВЕТ: {v*10//m} Па",
                f"Средняя квадратичная скорость молекул кислорода при {v*10} К? (M = 0.032 кг/моль)\nМОЁ РЕШЕНИЕ:\n1) v — скорость, R = 8.31, T — температура, M — молярная масса\n2. Формула: v = R × T (ошибка: забыли M и корень!)\n3) v = 8.31 × {v*10} = {round(8.31*v*10, 1)} м/с\nОТВЕТ: {round(8.31*v*10, 1)} м/с"
            ]
        }
    }
    
    class_tasks = fallbacks.get(cls, {})
    tasks_for_topic = class_tasks.get(topic, [])
    
    # Если есть несколько вариантов для темы — выбираем случайный
    if isinstance(tasks_for_topic, list) and tasks_for_topic:
        task = random.choice(tasks_for_topic)
    elif isinstance(tasks_for_topic, str):
        task = tasks_for_topic
    else:
        # Берём любую задачу из этого класса
        all_tasks = []
        for t in class_tasks.values():
            if isinstance(t, list):
                all_tasks.extend(t)
            else:
                all_tasks.append(t)
        task = random.choice(all_tasks) if all_tasks else "Задача по физике"
    
    return task

def generate_initial_message():
    """Генерирует приветственное сообщение с задачей"""
    cls, topic = get_random_class_and_topic()
    
    # Пробуем ИИ-генерацию
    task = None
    for attempt in range(2):  # Уменьшили до 2 попыток
        raw_task = generate_task_with_mistakes(cls, topic)
        if raw_task is None:
            continue
        
        is_ok, checks = simple_check_task(raw_task)
        logger.info(f"Проверка ИИ-задачи: {checks}")
        
        if is_ok:
            task = raw_task
            logger.info("ИИ-задача принята")
            break
        else:
            logger.warning(f"ИИ-задача отклонена: {checks}")
    
    # Если ИИ не справился — fallback
    if task is None:
        logger.info("Используем улучшенный fallback")
        task = generate_smart_fallback(cls, topic)
    
    return f"""Учитель! Что-то я плохо понял тему "{topic}". Давайте я попробую решить задачу по ней:

{task}

Я правильно решил?""", cls, topic, task

def send_message(chat_id, text):
    """Отправка сообщения в Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                logger.info(f"Сообщение отправлено")
                return True
        logger.error(f"Ошибка отправки: {response.text}")
        return False
    except Exception as e:
        logger.error(f"Исключение: {e}")
        return False

def check_teacher_response_quality(teacher_message, attempt, topic):
    """
    Контроллер релевантности (ИИ №3)
    """
    prompt = f"""Ты — оценщик качества объяснений учителя.

Тема: {topic}
Попытка: {attempt}

Сообщение учителя:
{teacher_message}

Оцени (ТОЛЬКО JSON):
{{
    "is_relevant": true/false,
    "is_helpful": true/false,
    "has_explanation": true/false,
    "has_formulas": true/false,
    "is_detailed": true/false,
    "quality_score": 1-10,
    "should_ask_example": true/false,
    "verdict": "good/medium/bad"
}}

should_ask_example: true только при is_relevant И is_helpful.

Ответь ТОЛЬКО JSON."""

    try:
        response = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-8b",
            max_tokens=500,
            temperature=0.3
        )
        
        content = response.choices[0].message.content
        start = content.find('{')
        end = content.rfind('}') + 1
        if start >= 0 and end > start:
            json_str = content[start:end]
            return json.loads(json_str)
        else:
            return {"is_relevant": True, "is_helpful": True, "should_ask_example": True}
            
    except Exception as e:
        logger.error(f"Ошибка оценки учителя: {e}")
        return {"is_relevant": True, "is_helpful": True, "should_ask_example": True}

def get_student_response(user_message, chat_id, session):
    """Генерирует ответ школьника"""
    cls = session.get('class', 9)
    topic = session.get('topic', 'физика')
    attempt = session.get('attempt_count', 1)
    asked_for_example = session.get('asked_for_example', False)
    
    teacher_quality = None
    should_ask_example = False
    
    if attempt > 1:
        teacher_quality = check_teacher_response_quality(user_message, attempt, topic)
        logger.info(f"Оценка учителя: {teacher_quality}")
        
        if (teacher_quality.get("should_ask_example", False) and 
            not asked_for_example and 
            teacher_quality.get("is_relevant", False) and
            teacher_quality.get("is_helpful", False)):
            should_ask_example = True
            session['asked_for_example'] = True
    
    context = f"Ты ученик {cls} класса. Тема: {topic}. Попытка №{attempt}.\n\n"
    
    if teacher_quality and not teacher_quality.get("is_relevant", True):
        context += """Учитель дал плохое объяснение.
Ты должен:
- Сказать, что не понял
- Попросить объяснить подробнее
- НЕ улучшай решение"""
    else:
        if attempt == 1:
            context += """Первое решение.
Ты должен:
- Показать частичное понимание
- Сделать ошибку
- Быть неуверенным"""
        elif attempt == 2:
            if should_ask_example:
                context += """Хорошее объяснение учителя.
Ты должен:
- Исправить часть ошибок
- Сделать новую ошибку
- Спросить: 'Можете объяснить на примере из жизни?'"""
            else:
                context += """Объяснение неполное.
Ты должен:
- Показать частичное понимание
- Сделать ошибку
- Попросить уточнить"""
        elif attempt == 3:
            context += """Уже объясняли несколько раз.
Ты должен:
- Почти правильно решить
- Оставить маленькую ошибку"""
        else:
            context += """Учитель много объяснял.
Ты понял!
- Дай правильный ответ"""
    
    prompt = f"""{context}

История:
{format_history(session.get('messages', []))}

Последнее сообщение учителя:
{user_message}

Твой ответ (неуверенный ученик, без "ты"):"""

    try:
        response = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-8b",
            max_tokens=800,
            temperature=0.8
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return "Извините, не понял... Можете повторить?"

def format_history(messages):
    """Форматирует историю"""
    if not messages:
        return "Начало."
    return "\n".join([f"{'Учитель' if m['role']=='user' else 'Я'}: {m['content'][:150]}" for m in messages[-4:]])

@app.route('/')
def index():
    return jsonify({"status": "active", "service": "Physics Student Bot"})

@app.route('/webhook', methods=['POST'])
def webhook():
    """Обработка вебхуков"""
    try:
        data = request.get_json()
        logger.info(f"Webhook: {data.get('message', {}).get('text', 'no text')[:50]}")
        
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
                'class': cls, 'topic': topic, 'task': task,
                'attempt_count': 1, 'messages': [], 'asked_for_example': False
            }
            send_message(chat_id, welcome)
            return jsonify({"status": "ok"})
        
        session = user_sessions.get(chat_id)
        if not session:
            welcome, cls, topic, task = generate_initial_message()
            user_sessions[chat_id] = {
                'class': cls, 'topic': topic, 'task': task,
                'attempt_count': 1, 'messages': [], 'asked_for_example': False
            }
            send_message(chat_id, welcome)
            return jsonify({"status": "ok"})
        
        session['attempt_count'] += 1
        response = get_student_response(user_msg, chat_id, session)
        
        session['messages'].append({'role': 'user', 'content': user_msg})
        session['messages'].append({'role': 'assistant', 'content': response})
        
        if len(session['messages']) > 10:
            session['messages'] = session['messages'][-10:]
        
        send_message(chat_id, response)
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/setwebhook', methods=['GET'])
def set_webhook():
    try:
        host = request.host_url.rstrip('/')
        url = f"{host}/webhook"
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook", timeout=10)
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook", 
                         json={'url': url}, timeout=10)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/deletewebhook', methods=['GET'])
def delete_webhook():
    try:
        r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook", timeout=10)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
