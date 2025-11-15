import os
import sqlite3
import logging
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройки
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')

# Получаем ADMIN_ID из переменных окружения, если нет - используем дефолтный
try:
    ADMIN_ID = int(os.getenv('ADMIN_ID', '123456789'))
except:
    ADMIN_ID = 123456789  # Замените на ваш реальный ID

logger.info(f"Bot started with ADMIN_ID: {ADMIN_ID}")

# База данных
def init_db():
    conn = sqlite3.connect('bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            channel_id TEXT PRIMARY KEY,
            channel_name TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT,
            schedule_time TIMESTAMP,
            channel_id TEXT,
            status TEXT DEFAULT 'scheduled'
        )
    ''')
    
    conn.commit()
    conn.close()

def add_channel(channel_id, channel_name):
    conn = sqlite3.connect('bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO channels VALUES (?, ?)', (channel_id, channel_name))
    conn.commit()
    conn.close()

def get_channels():
    conn = sqlite3.connect('bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('SELECT channel_id, channel_name FROM channels')
    channels = cursor.fetchall()
    conn.close()
    return channels

def add_post(content, schedule_time, channel_id):
    conn = sqlite3.connect('bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO posts (content, schedule_time, channel_id) VALUES (?, ?, ?)',
                  (content, schedule_time, channel_id))
    conn.commit()
    conn.close()

# Клавиатуры
def main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📝 Создать пост", callback_data="create_post")],
        [InlineKeyboardButton("📅 Мои посты", callback_data="my_posts")],
        [InlineKeyboardButton("📢 Каналы", callback_data="channels")]
    ]
    return InlineKeyboardMarkup(keyboard)

def channels_keyboard():
    channels = get_channels()
    keyboard = []
    for channel_id, name in channels:
        keyboard.append([InlineKeyboardButton(f"📢 {name}", callback_data=f"channel_{channel_id}")])
    keyboard.append([InlineKeyboardButton("➕ Добавить канал", callback_data="add_channel")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])
    return InlineKeyboardMarkup(keyboard)

def time_keyboard():
    keyboard = [
        [InlineKeyboardButton("⏰ Через 15 мин", callback_data="time_15")],
        [InlineKeyboardButton("⏰ Через 1 час", callback_data="time_60")],
        [InlineKeyboardButton("⏰ Через 3 часа", callback_data="time_180")],
        [InlineKeyboardButton("⏰ Завтра", callback_data="time_1440")],
        [InlineKeyboardButton("🔙 Назад", callback_data="back")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Команды бота
async def start(update: Update, context):
    user_id = update.effective_user.id
    logger.info(f"User {user_id} tried to start bot")
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещен. Обратитесь к администратору.")
        return
    
    await update.message.reply_text(
        "👋 Привет! Я бот для публикации постов.\nВыберите действие:",
        reply_markup=main_keyboard()
    )

async def button_click(update: Update, context):
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id != ADMIN_ID:
        await query.answer("❌ Доступ запрещен")
        return
    
    data = query.data
    
    if data == "back" or data == "main_menu":
        await query.edit_message_text("Выберите действие:", reply_markup=main_keyboard())
    
    elif data == "create_post":
        channels = get_channels()
        if not channels:
            await query.edit_message_text("❌ Сначала добавьте канал", reply_markup=main_keyboard())
            return
        await query.edit_message_text("Выберите канал:", reply_markup=channels_keyboard())
    
    elif data == "channels":
        await query.edit_message_text("Управление каналами:", reply_markup=channels_keyboard())
    
    elif data == "add_channel":
        await query.edit_message_text(
            "Чтобы добавить канал:\n\n"
            "1. Добавьте бота в канал как администратора\n"
            "2. Перешлите любое сообщение из канала сюда\n\n"
            "Или отправьте @username канала",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="channels")]])
        )
    
    elif data.startswith("channel_"):
        channel_id = data.replace("channel_", "")
        context.user_data['channel'] = channel_id
        await query.edit_message_text(
            "📝 Отправьте текст поста:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="create_post")]])
        )
        context.user_data['waiting_post'] = True
    
    elif data.startswith("time_"):
        if 'post_text' not in context.user_data:
            await query.answer("❌ Сначала отправьте текст поста")
            return
        
        minutes = int(data.replace("time_", ""))
        post_time = datetime.now() + timedelta(minutes=minutes)
        
        add_post(
            context.user_data['post_text'],
            post_time,
            context.user_data['channel']
        )
        
        channel_name = next((name for cid, name in get_channels() if cid == context.user_data['channel']), "Канал")
        
        await query.edit_message_text(
            f"✅ Пост запланирован!\n\n"
            f"📢 Канал: {channel_name}\n"
            f"⏰ Время: {post_time.strftime('%d.%m.%Y %H:%M')}\n"
            f"📄 Текст: {context.user_data['post_text'][:100]}...",
            reply_markup=main_keyboard()
        )
        
        context.user_data.clear()
    
    elif data == "my_posts":
        conn = sqlite3.connect('bot.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT p.content, p.schedule_time, c.channel_name 
            FROM posts p 
            JOIN channels c ON p.channel_id = c.channel_id 
            WHERE p.status = 'scheduled'
            ORDER BY p.schedule_time
        ''')
        posts = cursor.fetchall()
        conn.close()
        
        if not posts:
            await query.edit_message_text("📭 Нет запланированных постов", reply_markup=main_keyboard())
            return
        
        text = "📅 Ваши посты:\n\n"
        for i, (content, time, channel) in enumerate(posts, 1):
            text += f"{i}. 📢 {channel}\n"
            text += f"   ⏰ {time}\n"
            text += f"   📄 {content[:50]}...\n\n"
        
        await query.edit_message_text(text, reply_markup=main_keyboard())

async def handle_message(update: Update, context):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ Доступ запрещен")
        return
    
    message = update.message
    
    # Добавление канала
    if message.forward_from_chat and message.forward_from_chat.type == 'channel':
        channel_id = str(message.forward_from_chat.id)
        channel_name = message.forward_from_chat.title
        
        add_channel(channel_id, channel_name)
        await message.reply_text(f"✅ Канал '{channel_name}' добавлен!", reply_markup=main_keyboard())
        return
    
    # Текст поста
    if context.user_data.get('waiting_post'):
        context.user_data['post_text'] = message.text
        context.user_data['waiting_post'] = False
        
        await message.reply_text(
            "⏰ Выберите время публикации:",
            reply_markup=time_keyboard()
        )
        return
    
    await message.reply_text("Выберите действие:", reply_markup=main_keyboard())

# Публикация постов
async def publish_posts(context):
    conn = sqlite3.connect('bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, content, channel_id FROM posts WHERE status = 'scheduled' AND schedule_time <= datetime('now')")
    posts = cursor.fetchall()
    
    for post_id, content, channel_id in posts:
        try:
            await context.bot.send_message(chat_id=channel_id, text=content)
            cursor.execute("UPDATE posts SET status = 'published' WHERE id = ?", (post_id,))
            conn.commit()
            logger.info(f"Пост {post_id} опубликован в канале {channel_id}")
        except Exception as e:
            logger.error(f"Ошибка публикации поста {post_id}: {e}")
    
    conn.close()

def main():
    # Инициализация базы данных
    init_db()
    
    # Создание приложения
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(MessageHandler(filters.ALL, handle_message))
    
    # Публикация постов каждую минуту
    if hasattr(app, 'job_queue') and app.job_queue is not None:
        app.job_queue.run_repeating(publish_posts, interval=60, first=10)
        logger.info("JobQueue запущен")
    else:
        logger.warning("JobQueue недоступен")
    
    logger.info("Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
