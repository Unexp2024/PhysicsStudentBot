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
    Генератор задач (ИИ №1)
    """
    prompt = f"""Ты — эксперт по физике для {cls} класса. Создай РЕАЛИСТИЧНУЮ задачу по теме "{topic}".

ВАЖНЫЕ ТРЕБОВАНИЯ:
1. Задача из реальной жизни
2. Числа реалистичные
3. Минимум 2 числовых параметра В УСЛОВИИ
4. Требует формулы и вычисления
5. ВСЕ буквы в формулах должны быть РАСШИФРОВАНЫ
6. Решение ПОШАГОВОЕ с пояснениями

ФОРМАТ:
УСЛОВИЕ: [ситуация с числами]
МОЁ РЕШЕНИЕ: 
1) [расшифровка букв]
2) [формула с ошибкой]
3) [подстановка чисел]
ОТВЕТ: [число с ошибкой]

Примеры ошибок: неправильная формула, непереведённые единицы, арифметика

Создай задачу:"""

    try:
        response = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-8b",
            max_tokens=1000,
            temperature=0.8
        )
        task = response.choices[0].message.content.strip()
        logger.info(f"Сгенерированная задача: {task[:300]}...")
        return task
    except Exception as e:
        logger.error(f"Ошибка генерации задачи: {e}")
        return None

def check_task_quality(task_text, cls, topic):
    """
    Контроллер качества (ИИ №2)
    """
    prompt = f"""Ты — строгий контроллер качества задач по физике.

Проверь задачу для {cls} класса по теме "{topic}":

{task_text}

Проверь КРИТЕРИИ (ответь ТОЛЬКО JSON):
{{
    "has_calculations": true/false,
    "has_numbers_in_condition": true/false,
    "has_variable_explanations": true/false,
    "not_trivial": true/false,
    "has_mistakes": true/false,
    "mistake_count": число,
    "is_clear": true/false,
    "is_adequate": true/false,
    "reject_reason": "причина"
}}

Критерии ОТКЛОНЕНИЯ:
- has_variable_explanations: false — буквы не расшифрованы
- has_numbers_in_condition: false — нет чисел в условии
- is_clear: false — непонятно, что откуда взялось

Ответь ТОЛЬКО JSON."""

    try:
        response = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-8b",
            max_tokens=600,
            temperature=0.2
        )
        
        content = response.choices[0].message.content
        start = content.find('{')
        end = content.rfind('}') + 1
        if start >= 0 and end > start:
            json_str = content[start:end]
            result = json.loads(json_str)
            logger.info(f"Результат проверки: {result}")
            return result
        else:
            return {"is_adequate": True}
            
    except Exception as e:
        logger.error(f"Ошибка проверки качества: {e}")
        return {"is_adequate": True}

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

def generate_smart_fallback(cls, topic):
    """
    Улучшенный fallback — задачи с понятными обозначениями
    """
    v = random.choice([12, 15, 18, 20, 24, 30])
    t = random.choice([0.5, 1, 1.5, 2, 2.5, 3])
    m = random.choice([2, 3, 5, 8, 10, 12])
    h = random.choice([1, 1.5, 2, 2.5, 3, 4])
    F = random.choice([10, 20, 50, 100, 150, 200])
    s = random.choice([5, 10, 20, 50, 100])
    a = random.choice([2, 3, 4, 5])
    n = random.choice([10, 20, 30])
    
    fallbacks = {
        7: {
            "скорость": f"Велосипедист едет со скоростью {v} км/ч. Сколько времени он потратит на путь {s} км?\nМОЁ РЕШЕНИЕ:\n1) t — время, s — путь, v — скорость\n2) Формула: t = s × v\n3) Подставляем: t = {s} × {v} = {s*v} часов\nОТВЕТ: {s*v} ч",
            "плотность": f"Кусок железа массой {m*78} г имеет объём {m*10} см³. Найди плотность железа.\nМОЁ РЕШЕНИЕ:\n1) ρ — плотность, m — масса, V — объём\n2) Формула: ρ = m + V\n3) Подставляем: ρ = {m*78} + {m*10} = {m*88} г/см³\nОТВЕТ: {m*88} г/см³",
            "сила тяжести": f"Кирпич массой {m} кг падает с крыши. Какая сила тяжести действует на него? (g ≈ 10 Н/кг)\nМОЁ РЕШЕНИЕ:\n1) F — сила тяжести, m — масса, g — ускорение свободного падения\n2) Формула: F = m ÷ g\n3) Подставляем: F = {m} ÷ 10 = {m/10} Н\nОТВЕТ: {m/10} Н",
            "давление": f"Коробка массой {m} кг стоит на столе. Площадь дна коробки {m*50} см². Найди давление на стол.\nМОЁ РЕШЕНИЕ:\n1) p — давление, F — сила тяжести, S — площадь\n2) Формула: p = F + S\n3) F = {m} кг, S = {m*50} см²\n4) p = {m} + {m*50} = {m*51} Па\nОТВЕТ: {m*51} Па",
            "механическое движение": f"Поезд идёт {t} часов со скоростью {v*3} км/ч. Какое расстояние прошёл поезд?\nМОЁ РЕШЕНИЕ:\n1) s — расстояние, v — скорость, t — время\n2) Формула: s = v - t\n3) Подставляем: s = {v*3} - {t} = {v*3-t} км\nОТВЕТ: {v*3-t} км"
        },
        8: {
            "работа и мощность": f"Поднимают мешок с цементом массой {m} кг на высоту {h} м. Какая работа совершена?\nМОЁ РЕШЕНИЕ:\n1) A — работа, m — масса, h — высота, g ≈ 10 Н/кг\n2) Формула: A = m + h\n3) Подставляем: A = {m} + {h} = {m+h} Дж\nОТВЕТ: {m+h} Дж",
            "энергия": f"Автомобиль массой {m*100} кг движется со скоростью {v} м/с. Найди кинетическую энергию.\nМОЁ РЕШЕНИЕ:\n1) E — энергия, m — масса, v — скорость\n2) Формула: E = m + v\n3) Подставляем: E = {m*100} + {v} = {m*100+v} Дж\nОТВЕТ: {m*100+v} Дж",
            "простые механизмы": f"К рычагу приложили силу {F} Н. Плечо силы {h} м. Найди момент силы.\nМОЁ РЕШЕНИЕ:\n1) M — момент силы, F — сила, l — плечо\n2) Формула: M = F + l\n3) Подставляем: M = {F} + {h} = {F+h} Н·м\nОТВЕТ: {F+h} Н·м",
            "теплопроводность": f"Нагрели {m} кг воды от 20°C до 50°C. Сколько теплоты передано воде? (c воды = 4200 Дж/(кг·°C))\nМОЁ РЕШЕНИЕ:\n1) Q — теплота, c — удельная теплоёмкость, m — масса, Δt — разница температур\n2) Δt = 50 - 20 = 30°C\n3) Формула: Q = c ÷ m ÷ Δt\n4) Q = 4200 ÷ {m} ÷ 30 = {round(4200/m/30, 1)} Дж\nОТВЕТ: {round(4200/m/30, 1)} Дж"
        },
        9: {
            "законы Ньютона": f"Тележка массой {m} кг движется с ускорением {a} м/с². Какая сила действует на тележку?\nМОЁ РЕШЕНИЕ:\n1) F — сила, m — масса, a — ускорение\n2) Формула: F = m ÷ a\n3) Подставляем: F = {m} ÷ {a} = {round(m/a, 1)} Н\nОТВЕТ: {round(m/a, 1)} Н",
            "импульс": f"Мяч массой {m//2} кг летит со скоростью {v} м/с. Найди импульс мяча.\nМОЁ РЕШЕНИЕ:\n1) p — импульс, m — масса, v — скорость\n2) Формула: p = m + v\n3) Подставляем: p = {m//2} + {v} = {m//2+v} кг·м/с\nОТВЕТ: {m//2+v} кг·м/с",
            "архимедова сила": f"Кусок железа объёмом {m*10} см³ полностью погружен в воду. Найди выталкивающую силу. (ρ воды = 1 г/см³, g ≈ 10 Н/кг)\nМОЁ РЕШЕНИЕ:\n1) F — выталкивающая сила, V — объём, ρ — плотность, g — ускорение\n2) Формула: F = V + ρ\n3) Подставляем: F = {m*10} + 1 = {m*10+1} Н\nОТВЕТ: {m*10+1} Н",
            "движение": f"Мотоциклист разгоняется с ускорением {a} м/с² в течение {t} с. Какую скорость он приобретёт, если начальная скорость 0?\nМОЁ РЕШЕНИЕ:\n1) v — скорость, a — ускорение, t — время\n2) Формула: v = a ÷ t\n3) Подставляем: v = {a} ÷ {t} = {round(a/t, 1)} м/с\nОТВЕТ: {round(a/t, 1)} м/с",
            "ток": f"В электроплитке сила тока {a} А, сопротивление {m} Ом. Найди напряжение.\nМОЁ РЕШЕНИЕ:\n1) U — напряжение, I — сила тока, R — сопротивление\n2) Формула: U = I + R\n3) Подставляем: U = {a} + {m} = {a+m} В\nОТВЕТ: {a+m} В"
        },
        10: {
            "движение по окружности": f"Точка на ободе колеса движется по окружности радиусом {h} м со скоростью {v//2} м/с. Найди центростремительное ускорение.\nМОЁ РЕШЕНИЕ:\n1) a — ускорение, v — скорость, R — радиус\n2) Формула: a = v + R\n3) Подставляем: a = {v//2} + {h} = {v//2+h} м/с²\nОТВЕТ: {v//2+h} м/с²",
            "тяготение": f"Спутник массой {m} кг находится на высоте {h*1000} км над Землёй. Найди силу тяжести, действующую на спутник. (g ≈ 10 Н/кг на этой высоте)\nМОЁ РЕШЕНИЕ:\n1) F — сила тяжести, m — масса, g — ускорение\n2) Формула: F = m ÷ g\n3) Подставляем: F = {m} ÷ 10 = {m/10} Н\nОТВЕТ: {m/10} Н",
            "работа": f"Кран поднимает груз массой {m*100} кг на высоту {h} м. Какую работу совершает кран?\nМОЁ РЕШЕНИЕ:\n1) A — работа, m — масса, h — высота, g ≈ 10 Н/кг\n2) Формула: A = m × h\n3) Подставляем: A = {m*100} × {h} = {m*100*h} Дж\nОТВЕТ: {m*100*h} Дж",
            "законы Кеплера": f"Планета Меркурий обращается вокруг Солнца с периодом 0,24 года. На каком расстоянии от Солнца находится Меркурий? (Земля на расстоянии 150 млн км с периодом 1 год)\nМОЁ РЕШЕНИЕ:\n1) T — период обращения, a — большая полуось орбиты (расстояние)\n2) По третьему закону Кеплера: T² = a³ (в кубических а.е.)\n3) Для Меркурия: T = 0,24 года, значит a = T = 0,24 а.е.\n4) 1 а.е. = 150 млн км, значит a = 0,24 × 150 = 36 млн км\nОТВЕТ: 0,24 а.е. или 36 млн км"
        },
        11: {
            "электрическое поле": f"В однородное электрическое поле с напряжённостью {F*10} Н/Кл поместили заряд {m//2} мкКл. Найди силу, действующую на заряд.\nМОЁ РЕШЕНИЕ:\n1) F — сила, E — напряжённость поля, q — заряд\n2) Формула: F = E + q\n3) Подставляем: F = {F*10} + {m//2} = {F*10+m//2} мкН\nОТВЕТ: {F*10+m//2} мкН",
            "колебания": f"Маятник совершает {n} колебаний за {t*10} секунд. Найди период колебаний.\nМОЁ РЕШЕНИЕ:\n1) T — период, N — число колебаний, t — время\n2) Формула: T = N × t\n3) Подставляем: T = {n} × {t*10} = {n*t*10} с\nОТВЕТ: {n*t*10} с",
            "термодинамика": f"Газ получил {F*10} Дж теплоты и совершил работу {F} Дж, расширяясь. Найди изменение внутренней энергии газа.\nМОЁ РЕШЕНИЕ:\n1) ΔU — изменение внутренней энергии, Q — теплота, A — работа\n2) Формула: ΔU = Q + A\n3) Подставляем: ΔU = {F*10} + {F} = {F*11} Дж\nОТВЕТ: {F*11} Дж",
            "магнитное поле": f"Проводник длиной {h} м с током {a} А помещён в магнитное поле с индукцией {m/10} Тл перпендикулярно линиям индукции. Найди силу Ампера.\nМОЁ РЕШЕНИЕ:\n1) F — сила Ампера, B — магнитная индукция, I — сила тока, L — длина\n2) Формула: F = B ÷ I\n3) Подставляем: F = {m/10} ÷ {a} = {round(m/(10*a), 2)} Н\nОТВЕТ: {round(m/(10*a), 2)} Н",
            "молекулярно-кинетическая теория": f"В сосуде находится {m} моль идеального газа при температуре {v*10} К. Найди давление газа, если объём сосуда {m} л.\nМОЁ РЕШЕНИЕ:\n1) p — давление, T — температура, V — объём\n2) Формула: p = T ÷ V\n3) Подставляем: p = {v*10} ÷ {m} = {v*10//m} Па\nОТВЕТ: {v*10//m} Па"
        }
    }
    
    class_tasks = fallbacks.get(cls, {})
    task = class_tasks.get(topic)
    
    if task is None:
        available_tasks = list(class_tasks.values())
        if available_tasks:
            task = available_tasks[0]
        else:
            task = generate_smart_fallback(9, "законы Ньютона")[1] if cls != 9 else "Задача по физике"
    
    return task

def generate_initial_message():
    """Генерирует приветственное сообщение с задачей"""
    cls, topic = get_random_class_and_topic()
    
    task = None
    max_attempts = 3
    
    for attempt in range(max_attempts):
        raw_task = generate_task_with_mistakes(cls, topic)
        if raw_task is None:
            continue
        
        quality = check_task_quality(raw_task, cls, topic)
        logger.info(f"Попытка {attempt+1}, качество: {quality}")
        
        if (quality.get("is_adequate", False) and 
            quality.get("has_variable_explanations", False) and
            quality.get("has_numbers_in_condition", False)):
            task = raw_task
            logger.info("Задача принята ИИ-контролёром")
            break
        else:
            logger.warning(f"Задача отклонена: {quality.get('reject_reason', 'неизвестно')}")
    
    if task is None:
        logger.info("Используем fallback с пояснениями")
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
