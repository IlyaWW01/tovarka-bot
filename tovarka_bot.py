import logging
import re
import asyncio
import nest_asyncio
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

nest_asyncio.apply()

# Настройки
TOKEN = "7937031754:AAESUJ3pq0b7BAsjo6tO2MnFjCkiN48iE14"
ORDERS_CHAT_ID = "-1002591802067"
ADMIN_CHAT_ID = "ВАШ_TELEGRAM_ID"  # Укажите свой ID (можно узнать у @userinfobot)

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("orders.log"),  # Логирование в файл
        logging.StreamHandler()  # Логирование в консоль
    ]
)

# Хранилище заказов
user_orders = {}

# FAQ ответы
faq_answers = {
    "как оплатить": "Доступные способы оплаты: СБП или перевод на карту.",
    "когда доставка": "Обычно доставка 10–18 дней.",
    "где товар": "Если вы оформили заказ, он уже обрабатывается.",
    "не работает": "Напишите подробнее, мы разберёмся и поможем."
}

# Кнопка меню
def main_menu():
    return ReplyKeyboardMarkup([[KeyboardButton("Новый заказ")]], resize_keyboard=True)

# Проверка номера телефона
def is_valid_phone(phone: str) -> bool:
    pattern = r'^(\+7|7|8)?[\s\-]?\(?[0-9]{3}\)?[\s\-]?[0-9]{3}[\s\-]?[0-9]{2}[\s\-]?[0-9]{2}$'
    return re.match(pattern, phone) is not None

# Логирование заказа в файл
def log_order(user_id: int, order_data: dict, status: str = "created"):
    log_entry = (
        f"{datetime.now()} | User: {user_id} | "
        f"Артикул: {order_data.get('article')} | "
        f"Кол-во: {order_data.get('qty')} | "
        f"Статус: {status}\n"
    )
    with open("orders.log", "a", encoding="utf-8") as f:
        f.write(log_entry)

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Просто пришли мне товар из канала или напиши артикул.",
        reply_markup=main_menu()
    )

# Оповещение админа об ошибке
async def notify_admin(context: ContextTypes.DEFAULT_TYPE, error_msg: str):
    try:
        await context.bot.send_message(
            ADMIN_CHAT_ID,
            f"⚠️ Ошибка в боте:\n{error_msg}"
        )
    except Exception as e:
        logging.error(f"Не удалось уведомить админа: {e}")

# Обработка сообщений
async def route_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.lower() if update.message.text else ""

    if text == "новый заказ":
        user_orders.pop(user_id, None)
        await update.message.reply_text("Напиши артикул или перешли товар из канала.", reply_markup=main_menu())
        return

    for q in faq_answers:
        if q in text:
            await update.message.reply_text(faq_answers[q], reply_markup=main_menu())
            return

    if user_id in user_orders:
        await handle_reply(update, context)
    else:
        await handle_article(update, context)

# Первичное сообщение: артикул или пост
async def handle_article(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = update.message
    text = msg.caption or msg.text
    photo = msg.photo[-1].file_id if msg.photo else None

    match = re.search(r'(\d{5,})', text) if text else None
    if not match:
        await msg.reply_text("Не удалось найти артикул. Уточни, пожалуйста.", reply_markup=main_menu())
        return

    article = match.group(1)
    user_orders[user_id] = {
        "article": article,
        "photo": photo,
        "step": "qty"
    }
    log_order(user_id, user_orders[user_id])  # Логируем начало заказа
    await msg.reply_text("📦 Сколько штук тебе нужно?", reply_markup=main_menu())

# Оформление заказа — шаги
async def handle_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    order = user_orders.get(user_id)

    if not order:
        return

    step = order["step"]

    if step == "qty":
        if not text.isdigit():
            await update.message.reply_text("❌ Укажи число!", reply_markup=main_menu())
            return
        order["qty"] = text
        order["step"] = "name"
        await update.message.reply_text("✍️ Введи ФИО и адрес доставки:", reply_markup=main_menu())

    elif step == "name":
        order["name"] = text
        order["step"] = "phone"
        await update.message.reply_text("📞 Укажи номер телефона для связи:", reply_markup=main_menu())

    elif step == "phone":
        if not is_valid_phone(text):
            await update.message.reply_text("❌ Неверный формат номера. Попробуй ещё раз.", reply_markup=main_menu())
            return
        order["phone"] = text
        order["step"] = "confirm"

        summary = (
            f"✅ Всё верно?\n\n"
            f"🧞 Артикул: {order['article']}\n"
            f"🔢 Кол-во: {order['qty']}\n"
            f"📍 Адрес: {order['name']}\n"
            f"📞 Телефон: {order['phone']}\n\n"
            "⚠️ Заказ оформляется с предоплатой.\n"
            "Подтвердить заказ?"
        )
        keyboard = ReplyKeyboardMarkup([[KeyboardButton("ДА")], [KeyboardButton("Нет")]], resize_keyboard=True)
        await update.message.reply_text(summary, reply_markup=keyboard)

    elif step == "confirm":
        if text.lower() == "да":
            msg = (
                f"🆕 Новый заказ!\n\n"
                f"Артикул: {order['article']}\n"
                f"Кол-во: {order['qty']}\n"
                f"Адрес: {order['name']}\n"
                f"Телефон: {order['phone']}\n"
                f"Telegram: @{update.effective_user.username or 'не указан'}"
            )
            try:
                if order.get("photo"):
                    await context.bot.send_photo(ORDERS_CHAT_ID, order["photo"], caption=msg)
                else:
                    await context.bot.send_message(ORDERS_CHAT_ID, msg)
                await update.message.reply_text("✅ Заказ оформлен! Мы скоро с вами свяжемся.", reply_markup=main_menu())
                log_order(user_id, order, "completed")  # Логируем успешный заказ
            except Exception as e:
                error_msg = f"Ошибка отправки заказа: {e}"
                logging.error(error_msg)
                await update.message.reply_text("❌ Произошла ошибка при отправке заказа. Попробуйте позже.", reply_markup=main_menu())
                await notify_admin(context, error_msg)  # Уведомляем админа
        else:
            await update.message.reply_text("❌ Заказ отменён.", reply_markup=main_menu())
            log_order(user_id, order, "cancelled")  # Логируем отмену
        user_orders.pop(user_id, None)

# Запуск
async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, route_message))
    app.add_handler(MessageHandler(filters.PHOTO, route_message))  # Обработка фото с подписями

    logging.info("Бот запущен...")
    await app.run_polling()

if __name__ == "__main__":
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.create_task(main())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logging.info("Бот остановлен.")
