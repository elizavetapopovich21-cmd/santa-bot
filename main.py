import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ==========================
TOKEN = "8462613505:AAFECu2MwgW5_zQPLQEdJ-qMZJmzk86Sbhg"
# ==========================

ADMIN_ID = 7034431302

bot = Bot(TOKEN)
dp = Dispatcher()

# --- База данных ---
conn = sqlite3.connect("santa.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    age INTEGER,
    zodiac TEXT,
    photo_file_id TEXT,
    about TEXT,
    wish TEXT,
    given INTEGER DEFAULT 0,
    received INTEGER DEFAULT 0
)
""")
conn.commit()

# --- Главное меню ---
def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 Получить подарок", callback_data="get")
    kb.button(text="🎅 Подарить подарок", callback_data="give")
    kb.adjust(1)
    return kb.as_markup()

# --- Старт ---
@dp.message(Command("start"))
async def start(msg: Message):
    await msg.answer("Добро пожаловать в Тайного Санту! 😊\nВыберите действие:", reply_markup=main_menu())


# ======================
#      АНКЕТА
# ======================

user_state = {}

@dp.callback_query(F.data == "get")
async def fill_form_start(cb: CallbackQuery):
    uid = cb.from_user.id
    user_state[uid] = {}
    await cb.message.answer("Введите фамилию и имя:")
    await cb.answer()
    dp.message.register(fill_name, F.chat.id == uid)

async def fill_name(msg: Message):
    uid = msg.from_user.id
    user_state[uid]["name"] = msg.text
    await msg.answer("Введите возраст:")
    dp.message.handlers.clear()
    dp.message.register(fill_age, F.chat.id == uid)

async def fill_age(msg: Message):
    uid = msg.from_user.id
    user_state[uid]["age"] = msg.text
    await msg.answer("Введите знак зодиака:")
    dp.message.handlers.clear()
    dp.message.register(fill_zodiac, F.chat.id == uid)

async def fill_zodiac(msg: Message):
    uid = msg.from_user.id
    user_state[uid]["zodiac"] = msg.text
    await msg.answer("Пришлите одно своё фото:")
    dp.message.handlers.clear()
    dp.message.register(fill_photo, F.photo)

async def fill_photo(msg: Message):
    uid = msg.from_user.id
    user_state[uid]["photo_file_id"] = msg.photo[-1].file_id
    await msg.answer("Расскажите немного о себе:")
    dp.message.handlers.clear()
    dp.message.register(fill_about)

async def fill_about(msg: Message):
    uid = msg.from_user.id
    user_state[uid]["about"] = msg.text
    await msg.answer("Что бы вы хотели получить в подарок?")
    dp.message.handlers.clear()
    dp.message.register(fill_wish)

async def fill_wish(msg: Message):
    uid = msg.from_user.id
    user_state[uid]["wish"] = msg.text

    data = user_state[uid]

    cur.execute("""
        INSERT OR REPLACE INTO users(user_id, name, age, zodiac, photo_file_id, about, wish, given, received)
        VALUES(?,?,?,?,?,?,?,0,0)
    """, (uid, data["name"], data["age"], data["zodiac"], data["photo_file_id"], data["about"], data["wish"]))

    conn.commit()

    await msg.answer("Анкета сохранена! 🎄 Теперь вы можете нажать кнопку «Подарить подарок».",
                     reply_markup=main_menu())
    dp.message.handlers.clear()


# ======================
#   ПОДАРИТЬ ПОДАРОК
# ======================

@dp.callback_query(F.data == "give")
async def give_present(cb: CallbackQuery):
    uid = cb.from_user.id

    # Проверяем, получил ли уже
    cur.execute("SELECT received FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if row and row[0] == 1:
        await cb.message.answer("Вы уже получили анкету 🎁", reply_markup=main_menu())
        await cb.answer()
        return

    # Ищем случайную анкету
    cur.execute("""
        SELECT user_id, name, age, zodiac, photo_file_id, about, wish
        FROM users
        WHERE user_id != ? AND given = 0
        ORDER BY RANDOM()
        LIMIT 1
    """, (uid,))
    target = cur.fetchone()

    if not target:
        await cb.message.answer("Пока нет доступных анкет 😢 Попробуйте позже.")
        await cb.answer()
        return

    tid, name, age, zodiac, photo, about, wish = target

    # Отмечаем как выданную
    cur.execute("UPDATE users SET given = 1 WHERE user_id=?", (tid,))
    cur.execute("UPDATE users SET received = 1 WHERE user_id=?", (uid,))
    conn.commit()

    text = (
        f"🎁 *Анкета участника*\n\n"
        f"👤 *Имя:* {name}\n"
        f"🎂 *Возраст:* {age}\n"
        f"♒ *Знак зодиака:* {zodiac}\n\n"
        f"📝 *О себе:* {about}\n\n"
        f"✨ *Хочу получить:* {wish}"
    )

    await cb.message.answer_photo(photo, caption=text, parse_mode="Markdown")
    await cb.answer()


# ======================
#     АДМИН-ПАНЕЛЬ
# ======================

def admin_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Список участников", callback_data="admin_list")
    kb.button(text="📊 Статистика", callback_data="admin_stats")
    kb.button(text="👁 Просмотр анкеты", callback_data="admin_view")
    kb.button(text="🗑 Очистить базу", callback_data="admin_reset")
    kb.adjust(1)
    return kb.as_markup()

@dp.message(Command("admin"))
async def admin_panel(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return await msg.answer("⛔ У вас нет доступа к админ-панели")

    await msg.answer("Добро пожаловать в админ-панель 🎄", reply_markup=admin_menu())


# --- Список участников ---
@dp.callback_query(F.data == "admin_list")
async def admin_list(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return

    cur.execute("SELECT user_id, name, given, received FROM users")
    rows = cur.fetchall()

    if not rows:
        await cb.message.answer("❌ База пуста.")
        return

    text = "📋 *Список участников:*\n\n"
    for uid, name, given, received in rows:
        text += (f"🆔 {uid}\n"
                 f"👤 {name}\n"
                 f"🎁 Отправил: {'✅' if given else '❌'}\n"
                 f"📨 Получил: {'✅' if received else '❌'}\n\n")

    await cb.message.answer(text, parse_mode="Markdown")


# --- Статистика ---
@dp.callback_query(F.data == "admin_stats")
async def admin_stats(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return

    cur.execute("SELECT COUNT(*) FROM users")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM users WHERE given = 1")
    given = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM users WHERE received = 1")
    received = cur.fetchone()[0]

    text = (
        f"📊 *Статистика*\n\n"
        f"Всего участников: {total}\n"
        f"Анкет роздано: {given}\n"
        f"Анкет получили: {received}\n"
        f"Осталось раздать: {total - given}\n"
    )

    await cb.message.answer(text, parse_mode="Markdown")


# --- Просмотр анкеты ---
@dp.callback_query(F.data == "admin_view")
async def admin_view_start(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return
    await cb.message.answer("Введите ID пользователя для просмотра анкеты:")
    dp.message.register(admin_view_get)

async def admin_view_get(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return

    try:
        uid = int(msg.text)
    except:
        await msg.answer("Неверный ID.")
        return

    cur.execute("""
        SELECT name, age, zodiac, photo_file_id, about, wish
        FROM users WHERE user_id=?
    """, (uid,))
    data = cur.fetchone()

    if not data:
        await msg.answer("❌ Анкета не найдена.")
        return

    name, age, zodiac, photo, about, wish = data

    text = (
        f"👤 *{name}*\n"
        f"Возраст: {age}\n"
        f"Знак зодиака: {zodiac}\n\n"
        f"О себе: {about}\n\n"
        f"Хочу получить: {wish}"
    )

    await msg.answer_photo(photo, caption=text, parse_mode="Markdown")


# --- Очистка базы ---
@dp.callback_query(F.data == "admin_reset")
async def admin_reset(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        return

    await cb.message.answer("⚠️ Вы уверены, что хотите очистить базу? Напишите: ДА")
    dp.message.register(admin_reset_confirm)

async def admin_reset_confirm(msg: Message):
    if msg.from_user.id != ADMIN_ID:
        return

    if msg.text.strip().upper() == "ДА":
        cur.execute("DELETE FROM users")
        conn.commit()
        await msg.answer("🗑 База очищена!")
    else:
        await msg.answer("Отменено.")


# ======================
#        RUN
# ======================

async def main():
    await dp.start_polling(bot)

asyncio.run(main())
