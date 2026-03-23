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
    Создаёт задачу с вычислениями и неправильным решением (минимум 2 ошибки)
    """
    prompt = f"""Ты — эксперт по физике для {cls} класса. Создай РЕАЛИСТИЧНУЮ задачу по теме "{topic}".

ВАЖНО:
- Задача должна быть из реальной жизни (спорт, транспорт, быт, природа)
- Числа должны быть реалистичными (не 1 м, не 1000 км)
- Минимум 2 числовых параметра В УСЛОВИИ
- Должна требовать формулы и вычисления
- Ответ неочевиден без расчёта

ФОРМАТ (строго соблюдай):
УСЛОВИЕ: [конкретная ситуация с числами, например: "Велосипедист едет со скоростью 12 км/ч 3 часа"]
МОЁ РЕШЕНИЕ: [решение с 2-3 ошибками: неправильная формула, перепутаны единицы, арифметика]
ОТВЕТ: [число с ошибкой]

Примеры ошибок:
- v=s+t вместо v=s/t
- км/ч не перевёл в м/с
- перепутал массу и вес
- ошибка в степени (r² как r)

Создай задачу:"""

    try:
        response = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-70b",
            max_tokens=800,
            temperature=0.9
        )
        task = response.choices[0].message.content.strip()
        logger.info(f"Сгенерированная задача: {task[:200]}...")
        return task
    except Exception as e:
        logger.error(f"Ошибка генерации задачи: {e}")
        return None

def check_task_quality(task_text, cls, topic):
    """
    Контроллер качества (ИИ №2)
    Проверяет, соответствует ли задача требованиям
    """
    prompt = f"""Ты — контроллер качества задач по физике.

Проверь задачу для {cls} класса по теме "{topic}":

{task_text}

Проверь КРИТЕРИИ (ответь ТОЛЬКО JSON):
{{
    "has_calculations": true/false,
    "has_numbers": true/false,
    "not_trivial": true/false,
    "has_mistakes": true/false,
    "mistake_count": число,
    "is_adequate": true/false,
    "reason": "причина, если не подходит"
}}

Ответь ТОЛЬКО JSON, без пояснений."""

    try:
        response = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-70b",
            max_tokens=512,
            temperature=0.3
        )
        
        content = response.choices[0].message.content
        start = content.find('{')
        end = content.rfind('}') + 1
        if start >= 0 and end > start:
            json_str = content[start:end]
            return json.loads(json_str)
        else:
            return {"is_adequate": True}
            
    except Exception as e:
        logger.error(f"Ошибка проверки качества: {e}")
        return {"is_adequate": True}

def check_teacher_response_quality(teacher_message, attempt, topic):
    """
    Контроллер релевантности ответа учителя (ИИ №3)
    Оценивает, достаточно ли подробно и релевантно объяснил учитель
    Возвращает оценку и флаг, стоит ли запрашивать пример из жизни
    """
    prompt = f"""Ты — оценщик качества объяснений учителя.

Тема: {topic}
Текущая попытка ученика: {attempt}

Сообщение учителя:
{teacher_message}

Оцени (ответь ТОЛЬКО JSON):
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

Критерии:
- is_relevant: объяснение действительно направлено на помощь в понимании темы (не просто "нет", "неправильно", "подумай")
- is_helpful: содержит конкретные подсказки, формулы, шаги решения
- should_ask_example: true ТОЛЬКО если is_relevant И is_helpful (после действительно полезного объяснения)

Плохое объяснение (should_ask_example: false):
- "Неправильно", "Подумай ещё", "Нет", "Учебник открой"
- Очень короткое без конкретики

Хорошее объяснение (should_ask_example: true):
- Объясняет, что именно не так
- Даёт формулы или подсказки
- Показывает шаги решения

Ответь ТОЛЬКО JSON."""

    try:
        response = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-70b",
            max_tokens=512,
            temperature=0.3
        )
        
        content = response.choices[0].message.content
        start = content.find('{')
        end = content.rfind('}') + 1
        if start >= 0 and end > start:
            json_str = content[start:end]
            return json.loads(json_str)
        else:
            return {"is_relevant": True, "is_helpful": True, "should_ask_example": True, "quality_score": 5}
            
    except Exception as e:
        logger.error(f"Ошибка оценки учителя: {e}")
        return {"is_relevant": True, "is_helpful": True, "should_ask_example": True, "quality_score": 5}

def generate_smart_fallback(cls, topic):
    """
    Умный fallback — конкретные задачи с реалистичными числами и ошибками
    """
    # Случайные реалистичные числа
    v = random.choice([12, 15, 18, 20, 24, 30])  # скорость км/ч
    t = random.choice([0.5, 1, 1.5, 2, 2.5, 3])  # время ч
    m = random.choice([2, 3, 5, 8, 10, 12])  # масса кг
    h = random.choice([1, 1.5, 2, 2.5, 3, 4])  # высота м
    F = random.choice([10, 20, 50, 100, 150, 200])  # сила Н
    s = random.choice([5, 10, 20, 50, 100])  # расстояние м
    a = random.choice([2, 3, 4, 5])  # ускорение м/с²
    n = random.choice([10, 20, 30])  # количество
    
    fallbacks = {
        7: {
            "скорость": f"Велосипедист едет со скоростью {v} км/ч. За {t} ч он проедет?\nМОЁ РЕШЕНИЕ: s=v/t={v}/{t}={round(v/t, 1)} км\nОТВЕТ: {round(v/t, 1)} км",
            "плотность": f"Кусок алюминия массой {m*270} г имеет объём {m} см³. Найди плотность.\nМОЁ РЕШЕНИЕ: ρ=m+V={m*270}+{m}={m*270+m} г/см³\nОТВЕТ: {m*270+m} г/см³",
            "сила тяжести": f"Тело массой {m} кг падает. Сила тяжести?\nМОЁ РЕШЕНИЕ: F=m/m={m}/{m}=1 Н\nОТВЕТ: 1 Н",
            "давление": f"Кирпич массой {m} кг лежит на площади {m*2} см². Давление?\nМОЁ РЕШЕНИЕ: p=m+S={m}+{m*2}={m*3} Па\nОТВЕТ: {m*3} Па",
            "механическое движение": f"Поезд идёт {t} ч со скоростью {v*2} км/ч. Расстояние?\nМОЁ РЕШЕНИЕ: s=v-t={v*2}-{t}={v*2-t} км\nОТВЕТ: {v*2-t} км"
        },
        8: {
            "работа и мощность": f"Поднимают груз массой {m} кг на высоту {h} м. Работа?\nМОЁ РЕШЕНИЕ: A=m+h={m}+{h}={m+h} Дж\nОТВЕТ: {m+h} Дж",
            "энергия": f"Тело массой {m} кг движется со скоростью {v} м/с. Кинетическая энергия?\nМОЁ РЕШЕНИЕ: E=m+v={m}+{v}={m+v} Дж\nОТВЕТ: {m+v} Дж",
            "простые механизмы": f"Сила {F} Н действует на рычаг, плечо {h} м. Момент силы?\nМОЁ РЕШЕНИЕ: M=F+h={F}+{h}={F+h} Н·м\nОТВЕТ: {F+h} Н·м",
            "теплопроводность": f"Нагрели {m} кг воды от 20°C до 50°C. Теплота (c=4200)?\nМОЁ РЕШЕНИЕ: Q=c/t=4200/30=140 Дж\nОТВЕТ: 140 Дж"
        },
        9: {
            "законы Ньютона": f"Тело массой {m} кг движется с ускорением {a} м/с². Сила?\nМОЁ РЕШЕНИЕ: F=m/a={m}/{a}={round(m/a, 1)} Н\nОТВЕТ: {round(m/a, 1)} Н",
            "импульс": f"Мяч массой {m//2} кг летит со скоростью {v} м/с. Импульс?\nМОЁ РЕШЕНИЕ: p=m+v={m//2}+{v}={m//2+v} кг·м/с\nОТВЕТ: {m//2+v} кг·м/с",
            "архимедова сила": f"Тело объёмом {m*10} см³ погружено в воду. Выталкивающая сила?\nМОЁ РЕШЕНИЕ: F=V+m={m*10}+{m}={m*11} Н\nОТВЕТ: {m*11} Н",
            "движение": f"Мотоциклист едет {t} ч с ускорением {a} м/с². Ускорение?\nМОЁ РЕШЕНИЕ: a=v/t={v}/{t}={round(v/t, 1)} м/с²\nОТВЕТ: {round(v/t, 1)} м/с²",
            "ток": f"Сила тока {a} А, сопротивление {m} Ом. Напряжение?\nМОЁ РЕШЕНИЕ: U=I+R={a}+{m}={a+m} В\nОТВЕТ: {a+m} В"
        },
        10: {
            "движение по окружности": f"Точка движется по окружности R={h} м со скоростью {v//2} м/с. Центростремительное ускорение?\nМОЁ РЕШЕНИЕ: a=v+R={v//2}+{h}={v//2+h} м/с²\nОТВЕТ: {v//2+h} м/с²",
            "тяготение": f"Тело массой {m} кг на высоте {h} м над Землёй. Сила тяжести (g=10)?\nМОЁ РЕШЕНИЕ: F=m/h={m}/{h}={round(m/h, 1)} Н\nОТВЕТ: {round(m/h, 1)} Н",
            "работа": f"Сила {F} Н действует на расстоянии {s} м. Работа?\nМОЁ РЕШЕНИЕ: A=F/s={F}/{s}={round(F/s, 1)} Дж\nОТВЕТ: {round(F/s, 1)} Дж",
            "законы Кеплера": f"Планета на расстоянии {s} млн км от Солнца. Период обращения?\nМОЁ РЕШЕНИЕ: T=R/v={s}/{v}={round(s/v, 1)} лет\nОТВЕТ: {round(s/v, 1)} лет"
        },
        11: {
            "электрическое поле": f"Заряд {m//2} мкКл в поле E={F*10} Н/Кл. Сила?\nМОЁ РЕШЕНИЕ: F=q+E={m//2}+{F*10}={m//2+F*10} мкН\nОТВЕТ: {m//2+F*10} мкН",
            "колебания": f"Маятник совершает {n} колебаний за {t*10} с. Период?\nМОЁ РЕШЕНИЕ: T=ν×t={n}×{t*10}={n*t*10} с\nОТВЕТ: {n*t*10} с",
            "термодинамика": f"Газ получил {F*10} Дж теплоты и совершил работу {F} Дж. Изменение внутренней энергии?\nМОЁ РЕШЕНИЕ: ΔU=Q+W={F*10}+{F}={F*11} Дж\nОТВЕТ: {F*11} Дж",
            "магнитное поле": f"Проводник длиной {h} м с током {a} А в поле B={m/10} Тл. Сила Ампера?\nМОЁ РЕШЕНИЕ: F=B/I={m/10}/{a}={round(m/(10*a), 2)} Н\nОТВЕТ: {round(m/(10*a), 2)} Н",
            "молекулярно-кинетическая теория": f"В сосуде {m} моль газа при температуре {v*10} К. Давление (V={m} л)?\nМОЁ РЕШЕНИЕ: p=T/V={v*10}/{m}={v*10//m} Па\nОТВЕТ: {v*10//m} Па"
        }
    }
    
    class_tasks = fallbacks.get(cls, {})
    task = class_tasks.get(topic)
    
    if task is None:
        # Берём любую задачу из этого класса
        task = list(class_tasks.values())[0] if class_tasks else f"Задача по теме {topic}"
    
    return task

def generate_initial_message():
    """Генерирует приветственное сообщение с задачей"""
    cls, topic = get_random_class_and_topic()
    
    # Пытаемся сгенерировать задачу ИИ
    task = None
    max_attempts = 3
    
    for attempt in range(max_attempts):
        raw_task = generate_task_with_mistakes(cls, topic)
        if raw_task is None:
            continue
        
        # Проверяем, что задача содержит числа в условии
        if "УСЛОВИЕ:" in raw_task and any(char.isdigit() for char in raw_task.split("УСЛОВИЕ:")[1].split("МОЁ")[0]):
            # Проверяем качество
            quality = check_task_quality(raw_task, cls, topic)
            logger.info(f"Попытка {attempt+1}, качество: {quality}")
            
            if quality.get("is_adequate", True):
                task = raw_task
                break
    
    # Если ИИ не справился — используем умный fallback
    if task is None:
        logger.warning("ИИ не справился, используем fallback")
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
        logger.info(f"Ответ Telegram API: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                logger.info(f"Сообщение отправлено в чат {chat_id}")
                return True
            else:
                logger.error(f"Telegram API ошибка: {result}")
                return False
        else:
            logger.error(f"HTTP ошибка {response.status_code}: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Исключение при отправке: {e}")
        return False

def get_student_response(user_message, chat_id, session):
    """
    Генерирует ответ школьника с учётом качества объяснения учителя
    """
    cls = session.get('class', 9)
    topic = session.get('topic', 'физика')
    attempt = session.get('attempt_count', 1)
    asked_for_example = session.get('asked_for_example', False)
    
    # Оцениваем качество объяснения учителя
    teacher_quality = None
    should_ask_example = False
    
    if attempt > 1:
        teacher_quality = check_teacher_response_quality(user_message, attempt, topic)
        logger.info(f"Оценка учителя: {teacher_quality}")
        
        # Запрашиваем пример из жизни ТОЛЬКО если:
        # 1. Это первое релевантное объяснение
        # 2. Объяснение действительно полезное
        # 3. Мы ещё не просили пример
        if (teacher_quality.get("should_ask_example", False) and 
            not asked_for_example and 
            teacher_quality.get("is_relevant", False) and
            teacher_quality.get("is_helpful", False)):
            should_ask_example = True
            session['asked_for_example'] = True
    
    # Формируем промпт для школьника
    context = f"Ты ученик {cls} класса. Тема: {topic}. Это попытка №{attempt}.\n\n"
    
    if teacher_quality and not teacher_quality.get("is_relevant", True):
        # Объяснение нерелевантное — не улучшаемся
        context += """Учитель дал непонятное или слишком короткое объяснение.
Ты НЕ понял материал.
Ты должен:
- Сказать, что не понял
- Попросить объяснить подробнее, что именно не так
- Можешь запутаться ещё сильнее
- НЕ улучшай своё решение"""
    else:
        # Объяснение релевантное — постепенно улучшаемся
        if attempt == 1:
            context += """Это твоё первое решение. Учитель только начал объяснять.
Ты должен:
- Показать, что частично понял
- Но сделать новую ошибку
- Быть неуверенным"""
        elif attempt == 2:
            if should_ask_example:
                context += """Учитель дал хорошее объяснение. Ты начинаешь понимать.
Ты должен:
- Исправить ЧАСТЬ предыдущих ошибок
- Но сделать НОВУЮ ошибку
- ОБЯЗАТЕЛЬНО спросить: 'Можете, пожалуйста, объяснить это на простом примере из жизни?'"""
            else:
                context += """Учитель объяснил, но не очень подробно.
Ты должен:
- Показать частичное понимание
- Сделать ошибку в вычислениях
- Попросить уточнить или объяснить подробнее"""
        elif attempt == 3:
            context += """Учитель уже объяснял несколько раз.
Ты должен:
- Почти правильно решить
- Но оставить маленькую ошибку или сомнение
- Задать уточняющий вопрос"""
        else:
            context += """Учитель много раз объяснял.
Ты наконец понял!
- Дай правильное решение
- Покажи облегчение
- Поблагодари учителя"""
    
    prompt = f"""{context}

ИСТОРИЯ ДИАЛОГА:
{format_history(session.get('messages', []))}

ПОСЛЕДНЕЕ СООБЩЕНИЕ УЧИТЕЛЯ:
{user_message}

Твой ответ (как неуверенный ученик, разговорный стиль, уважительно, без "ты"):"""

    try:
        response = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-70b",
            max_tokens=1024,
            temperature=0.8
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка генерации ответа: {e}")
        return "Извините, я запутался... Можете повторить объяснение?"

def format_history(messages):
    """Форматирует историю сообщений"""
    if not messages:
        return "Начало диалога."
    
    result = []
    for msg in messages[-6:]:
        role = "Учитель" if msg['role'] == 'user' else "Я"
        result.append(f"{role}: {msg['content'][:200]}...")
    
    return "\n".join(result)

@app.route('/')
def index():
    """Проверка работоспособности"""
    return jsonify({
        "status": "active",
        "service": "Physics Student Bot",
        "message": "Бот работает! Отправьте /start в Telegram"
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """Обработка вебхуков от Telegram"""
    try:
        data = request.get_json()
        logger.info(f"Incoming webhook: {json.dumps(data, ensure_ascii=False)}")
        
        if not data or 'message' not in data:
            return jsonify({"status": "ok"})
        
        message_data = data['message']
        
        if 'text' not in message_data:
            return jsonify({"status": "ok"})
        
        user_msg = message_data['text'].strip()
        chat_id = message_data['chat']['id']
        
        # Обработка /start
        if user_msg == '/start':
            welcome_text, cls, topic, task = generate_initial_message()
            
            user_sessions[chat_id] = {
                'class': cls,
                'topic': topic,
                'task': task,
                'attempt_count': 1,
                'messages': [],
                'asked_for_example': False
            }
            
            send_message(chat_id, welcome_text)
            return jsonify({"status": "ok"})
        
        # Обработка обычных сообщений
        session = user_sessions.get(chat_id)
        if not session:
            welcome_text, cls, topic, task = generate_initial_message()
            user_sessions[chat_id] = {
                'class': cls,
                'topic': topic,
                'task': task,
                'attempt_count': 1,
                'messages': [],
                'asked_for_example': False
            }
            send_message(chat_id, welcome_text)
            return jsonify({"status": "ok"})
        
        # Увеличиваем счётчик попыток
        session['attempt_count'] += 1
        
        # Генерируем ответ
        response_text = get_student_response(user_msg, chat_id, session)
        
        # Сохраняем в историю
        session['messages'].append({'role': 'user', 'content': user_msg})
        session['messages'].append({'role': 'assistant', 'content': response_text})
        
        # Ограничиваем историю
        if len(session['messages']) > 10:
            session['messages'] = session['messages'][-10:]
        
        send_message(chat_id, response_text)
        return jsonify({"status": "ok"})
        
    except Exception as e:
        logger.error(f"Ошибка в webhook: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/setwebhook', methods=['GET'])
def set_webhook():
    """Установка вебхука"""
    try:
        host_url = request.host_url.rstrip('/')
        webhook_url = f"{host_url}/webhook"
        
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook", timeout=10)
        
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/setWebhook",
            json={'url': webhook_url},
            timeout=10
        )
        
        result = response.json()
        if result.get('ok'):
            return jsonify({"status": "success", "webhook_url": webhook_url})
        else:
            return jsonify({"status": "error", "message": result}), 500
            
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/deletewebhook', methods=['GET'])
def delete_webhook():
    """Удаление вебхука"""
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook",
            timeout=10
        )
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
