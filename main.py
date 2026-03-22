import telebot
import random
import os

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

# Состояние пользователя
user_state = {}

# Темы по классам
topics_by_grade = {
    7: ["сила тяжести", "механическое движение", "скорость", "плотность", "давление"],
    8: ["теплопроводность", "работа и мощность", "простые механизмы", "энергия"],
    9: ["законы Ньютона", "движение", "импульс", "архимедова сила", "ток"],
    10: ["законы Кеплера", "движение по окружности", "тяготение", "работа"],
    11: ["термодинамика", "молекулярно-кинетическая теория", "электрическое поле", "магнитное поле", "колебания"]
}

def generate_task():
    # Выбираем случайный класс
    grade = random.randint(7, 11)
    topic = random.choice(topics_by_grade[grade])
    
    # Придумываем задачу: минимум 2 числовых параметра
    a = random.randint(2, 20)
    b = random.randint(10, 200)
    if topic in ["скорость", "механическое движение", "движение", "движение по окружности"]:
        task = f"Машина проезжает {b} км за {a} часов. Какова её скорость?"
        solution = f"Я думаю, скорость равна {b*a} км/ч"  # ошибочное решение
    elif topic in ["сила тяжести", "энергия", "работа и мощность", "ток"]:
        task = f"Объект массой {a} кг поднимают на высоту {b} м. Какова потенциальная энергия?"
        solution = f"Я думаю, энергия равна {a+b} Дж"  # ошибочное решение
    else:
        task = f"На плоскости находится объект. {a} N силы действуют на него в течение {b} секунд. Что произойдет?"
        solution = f"Я думаю, объект будет двигаться со скоростью {a+b} м/с"  # ошибочное решение
    return task, solution, topic, grade

# Начало диалога
@bot.message_handler(commands=['start'])
def handle_start(message):
    task, solution, topic, grade = generate_task()
    user_state[message.chat.id] = {
        "task": task,
        "solution": solution,
        "topic": topic,
        "grade": grade,
        "step": 1
    }
    bot.send_message(
        message.chat.id,
        f"Учитель! Что-то я плохо понял тему {topic}. Я попытался решить задачу: {task} "
        f"Вот моё решение: {solution} Я правильно решил?"
    )

# Ответы пользователя
@bot.message_handler(func=lambda m: True)
def handle_message(message):
    state = user_state.get(message.chat.id)
    if not state:
        bot.send_message(message.chat.id, "Напишите /start чтобы начать.")
        return
    
    step = state["step"]
    
    # Алгоритм исправлений ошибок по шагам
    if step == 1:
        bot.send_message(message.chat.id, "А можете объяснить это на простом примере из жизни?")
        state["step"] += 1
    elif step == 2:
        bot.send_message(message.chat.id,
                         "Я попробовал исправить часть ошибки, но, кажется, я снова что-то напутал...")
        state["step"] += 1
    elif step == 3:
        bot.send_message(message.chat.id,
                         "Теперь почти правильно, но я всё ещё не уверен в одном моменте...")
        state["step"] += 1
    else:
        bot.send_message(message.chat.id,
                         "Похоже, я наконец понял! Спасибо за помощь, учитель.")
        del user_state[message.chat.id]

# Запуск
if __name__ == "__main__":
    print("Бот запущен (polling)")
    bot.infinity_polling()
