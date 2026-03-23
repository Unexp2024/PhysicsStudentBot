import os
import telebot
from fastapi import FastAPI, Request
from pydantic import BaseModel
import uvicorn

# ====== Настройки ======
TOKEN = os.environ.get("TOKEN")  # Ваш Telegram Bot Token в Render
if not TOKEN:
    raise ValueError("TOKEN не задан в переменных окружения")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = FastAPI()


# ====== Для валидации входящего update =====
class TelegramUpdate(BaseModel):
    update_id: int
    message: dict | None = None
    edited_message: dict | None = None
    # можно добавить другие поля при необходимости


# ====== Здоровье сервиса =====
@app.get("/health")
def health():
    return {"status": "ok"}


# ====== Webhook =====
@app.post("/webhook")
async def webhook(update: TelegramUpdate, request: Request):
    json_update = await request.json()
    try:
        telegram_update = telebot.types.Update.de_json(json_update)
        bot.process_new_updates([telegram_update])
    except Exception as e:
        print("Ошибка обработки update:", e)
    return {"ok": True}


# ====== Пример хендлера бота =====
@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(message, "Привет! Я школьник, который плохо понял тему. Давайте начнем задачу.")


# ====== Запуск локально =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
