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
    prompt = f"""Ты — генератор задач по физике для {cls} класса.

СОЗДАЙ ЗАДАЧУ:
Тема: {topic}
Требования:
1. Задача должна требовать ВЫЧИСЛЕНИЙ (формулы + расчёты)
2. Минимум 2 числовых параметра в условии
3. Ответ НЕ должен быть очевидным без расчётов
4. Задача должна быть реалистичной и иметь однозначное решение
5. НЕ используй тривиальные задачи

ФОРМАТ ОТВЕТА (строго):
УСЛОВИЕ: [текст задачи с конкретными числами]
МОЁ РЕШЕНИЕ: [подробное решение с минимум 2 ошибками: неправильная формула, ошибка в вычислениях, неправильные единицы, перепутаны величины]
ОТВЕТ: [число с ошибкой]

Пример ошибок:
- Перепутать формулу (например, v=s*t вместо v=s/t)
- Не перевести единицы (км/ч вместо м/с)
- Арифметическая ошибка
- Перепутать массу и вес"""

    try:
        response = cerebras_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1-70b",
            max_tokens=1024,
            temperature=0.8
        )
        return response.choices[0].message.content
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
    "has_calculations": true/false,  // Есть ли вычисления?
    "has_numbers": true/false,       // Минимум 2 числовых параметра?
    "not_trivial": true/false,       // Не тривиальная?
    "has_mistakes": true/false,      // Есть ли ошибки в решении?
    "mistake_count": число,          // Количество найденных ошибок
    "is_adequate": true/false,       // Общая оценка: задача подходит?
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
        
        # Извлекаем JSON из ответа
        content = response.choices[0].message.content
        # Находим JSON в тексте
        start = content.find('{')
        end = content.rfind('}') + 1
        if start >= 0 and end > start:
            json_str = content[start:end]
            return json.loads(json_str)
        else:
            return {"is_adequate": True}  # По умолчанию пропускаем
            
    except Exception as e:
        logger.error(f"Ошибка проверки качества: {e}")
        return {"is_adequate": True}  # По умолчанию пропускаем

def check_teacher_response_quality(teacher_message, current_attempt, topic):
    """
    Контроллер релевантности ответа учителя (ИИ №3)
    Оценивает, достаточно ли подробно объяснил учитель
    """
    prompt = f"""Ты — оценщик качества объяснений учителя.

Тема: {topic}
Текущая попытка ученика: {try_attempt}

Сообщение учителя:
{teacher_message}

Оцени (ответь ТОЛЬКО JSON):
{{
    "is_relevant": true/false,       // Достаточно ли подробное объяснение?
    "has_explanation": true/false,   // Есть ли объяснение, а не просто "нет"?
    "has_formulas": true/false,      // Упоминаются ли формулы/шаги?
    "is_detailed": true/false,       // Более 2 предложений?
    "quality_score": 1-10,           // Оценка качества
    "verdict": "good/bad/short"      // Рекомендация
}}

Критерии ПЛОХОГО объяснения:
- Очень короткое (1-2 фразы)
- Нет формул или шагов решения
- Просто "подумай", "вспомни", "нет", "неправильно"
- Нет конкретики, ЧТО неправильно и ПОЧЕМУ

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
            return {"is_relevant": True, "quality_score": 5}
            
    except Exception as e:
        logger.error(f"Ошибка оценки учителя: {e}")
        return {"is_relevant": True, "quality_score": 5}

def generate_initial_message():
    """Генерирует приветственное сообщение с задачей"""
    cls, topic = get_random_class_and_topic()
    
    # Генерируем задачу
    max_attempts = 3
    for attempt in range(max_attempts):
        task = generate_task_with_mistakes(cls, topic)
        if task is None:
            continue
            
        # Проверяем качество задачи
        quality = check_task_quality(task, cls, topic)
        logger.info(f"Качество задачи (попытка {attempt+1}): {quality}")
        
        if quality.get("is_adequate", True) and quality.get("has_mistakes", True):
            # Задача подходит
            return f"""Учитель! Что-то я плохо понял тему "{topic}". Давайте я попробую решить задачу по ней:

{task}

Я правильно решил?""", cls, topic, task
    
    # Если не удалось сгенерировать хорошую задачу, используем fallback
    fallback_task = generate_fallback_task(cls, topic)
    return f"""Учитель! Что-то я плохо понял тему "{topic}". Давайте я попробую решить задачу по ней:

{fallback_task}

Я правильно решил?""", cls, topic, fallback_task

def generate_fallback_task(cls, topic):
    """Резервный генератор задач (если ИИ не справляется)"""
    # Простые шаблоны задач с ошибками
    templates = {
        7: {
            "скорость": "Автомобиль едет 2 часа со скоростью 60 км/ч. Какое расстояние он проедет?\nМОЁ РЕШЕНИЕ: v=60 км/ч, t=2 ч, s=v+t=60+2=62 км\nОТВЕТ: 62 км",
            "плотность": "Кусок железа массой 780 г имеет объём 100 см³. Найди плотность.\nМОЁ РЕШЕНИЕ: ρ=m+V=780+100=880 г/см³\nОТВЕТ: 880 г/см³"
        },
        8: {
            "работа": "Подняли груз массой 5 кг на высоту 2 м. Найди работу.\nМОЁ РЕШЕНИЕ: A=m+h=5+2=7 Дж\nОТВЕТ: 7 Дж",
            "мощность": "Двигатель развивает мощность 100 Вт за 5 с. Какая работа совершена?\nМОЁ РЕШЕНИЕ: A=P/t=100/5=20 Дж\nОТВЕТ: 20 Дж"
        },
        9: {
            "законы Ньютона": "Тело массой 2 кг движется с ускорением 3 м/с². Найди силу.\nМОЁ РЕШЕНИЕ: F=m/a=2/3=0,67 Н\nОТВЕТ: 0,67 Н",
            "импульс": "Мяч массой 0,5 кг летит со скоростью 10 м/с. Найди импульс.\nМОЁ РЕШЕНИЕ: p=m+v=0,5+10=10,5 кг·м/с\nОТВЕТ: 10,5 кг·м/с"
        },
        10: {
            "движение по окружности": "Точка движется по окружности радиусом 4 м со скоростью 2 м/с. Найди центростремительное ускорение.\nМОЁ РЕШЕНИЕ: a=v+r=2+4=6 м/с²\nОТВЕТ: 6 м/с²",
            "работа": "Сила 10 Н действует на расстоянии 5 м под углом 0°. Найди работу.\nМОЁ РЕШЕНИЕ: A=F/s=10/5=2 Дж\nОТВЕТ: 2 Дж"
        },
        11: {
            "электрическое поле": "Заряд 2 мкКл находится в поле напряжённостью 500 Н/Кл. Найди силу.\nМОЁ РЕШЕНИЕ: F=q/E=0,002/500=0,000004 Н\nОТВЕТ: 4 мкН",
            "колебания": "Маятник совершает 20 колебаний за 10 с. Найди период.\nМОЁ РЕШЕНИЕ: T=ν/t=20/10=2 с\nОТВЕТ: 2 с"
        }
    }
    
    # Выбираем шаблон по теме или случайный
    class_templates = templates.get(cls, {})
    task = class_templates.get(topic)
    if task is None:
        # Берём первый доступный
        task = list(class_templates.values())[0] if class_templates else f"Задача по теме {topic} (не удалось сгенерировать)"
    
    return task

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
    
    # Оцениваем качество объяснения учителя (только если это не первое сообщение)
    teacher_quality = None
    if attempt > 1:
        teacher_quality = check_teacher_response_quality(user_message, attempt, topic)
        logger.info(f"Оценка объяснения учителя: {teacher_quality}")
    
    # Формируем промпт для школьника
    context = f"Ты ученик {cls} класса. Тема: {topic}. Это попытка №{attempt}.\n\n"
    
    if teacher_quality and not teacher_quality.get("is_relevant", True):
        # Объяснение плохое — не улучшаемся, просим подробнее
        context += """Учитель дал короткое или непонятное объяснение.
Ты НЕ понял материал.
Ты должен:
- Сказать, что не понял
- Попросить объяснить подробнее
- Можешь запутаться ещё сильнее
- НЕ улучшай своё решение"""
    else:
        # Объяснение хорошее — постепенно улучшаемся
        if attempt == 1:
            context += """Это твоё первое решение. Учитель только начал объяснять.
Ты должен:
- Показать, что частично понял
- Но сделать новую ошибку
- Попросить пример из жизни: 'Можете, пожалуйста, объяснить это на простом примере из жизни?'"""
        elif attempt == 2:
            context += """Учитель уже объяснял один раз.
Ты должен:
- Исправить ЧАСТЬ предыдущих ошибок
- Но сделать НОВУЮ ошибку
- Показать неуверенность"""
        elif attempt == 3:
            context += """Учитель объяснял уже несколько раз.
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

Твой ответ (как неуверенный ученик, разговорный стиль, уважительно):"""

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
    """Форматирует историю сообщений для контекста"""
    if not messages:
        return "Начало диалога."
    
    result = []
    for msg in messages[-6:]:  # Последние 6 сообщений
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
            
            # Сохраняем сессию
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
            # Если нет сессии, начинаем новую
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
        
        # Генерируем ответ ученика
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
        
        # Удаляем старый
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook", timeout=10)
        
        # Устанавливаем новый
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
