import os
import logging
import sqlite3
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    BotCommand
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    ContextTypes,
    MessageHandler,
    filters
)

# Настройки бота из переменных окружения Railway
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = [int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x]
PORT = int(os.getenv('PORT', 8443))
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация базы данных
def init_db():
    # Используем абсолютный путь для Railway
    db_path = os.path.join(os.getcwd(), 'bot.db')
    conn = sqlite3.connect(db_path, check_same_thread=False)
    cursor = conn.cursor()
    
    # Таблица каналов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT UNIQUE,
            channel_name TEXT,
            added_by INTEGER,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица постов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT,
            media_type TEXT,
            media_file_id TEXT,
            schedule_time TIMESTAMP,
            channel_id TEXT,
            status TEXT DEFAULT 'scheduled',
            created_by INTEGER,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица администраторов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            username TEXT,
            added_by INTEGER,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# Функции для работы с базой данных
def get_db_connection():
    db_path = os.path.join(os.getcwd(), 'bot.db')
    return sqlite3.connect(db_path, check_same_thread=False)

def add_channel(channel_id: str, channel_name: str, admin_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT OR REPLACE INTO channels (channel_id, channel_name, added_by) VALUES (?, ?, ?)',
            (channel_id, channel_name, admin_id)
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error adding channel: {e}")
        return False
    finally:
        conn.close()

def get_channels():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT channel_id, channel_name FROM channels')
    channels = cursor.fetchall()
    conn.close()
    return channels

def add_post(content: str, media_type: str, media_file_id: str, schedule_time: datetime, channel_id: str, user_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            '''INSERT INTO posts (content, media_type, media_file_id, schedule_time, channel_id, created_by) 
               VALUES (?, ?, ?, ?, ?, ?)''',
            (content, media_type, media_file_id, schedule_time, channel_id, user_id)
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        logger.error(f"Error adding post: {e}")
        return None
    finally:
        conn.close()

def get_scheduled_posts():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.id, p.content, p.schedule_time, p.channel_id, c.channel_name, p.status 
        FROM posts p 
        LEFT JOIN channels c ON p.channel_id = c.channel_id 
        WHERE p.status = 'scheduled' 
        ORDER BY p.schedule_time
    ''')
    posts = cursor.fetchall()
    conn.close()
    return posts

def add_admin(user_id: int, username: str, added_by: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT OR REPLACE INTO admins (user_id, username, added_by) VALUES (?, ?, ?)',
            (user_id, username, added_by)
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error adding admin: {e}")
        return False
    finally:
        conn.close()

def get_admins():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username FROM admins')
    admins = cursor.fetchall()
    conn.close()
    return admins

def is_admin(user_id: int):
    admins_list = [admin[0] for admin in get_admins()]
    return user_id in ADMIN_IDS or user_id in admins_list

# Клавиатуры
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("📋 Создать пост", callback_data="create_post")],
        [InlineKeyboardButton("📅 Запланированные посты", callback_data="scheduled_posts")],
        [InlineKeyboardButton("⚙️ Управление каналами", callback_data="manage_channels")],
        [InlineKeyboardButton("👥 Управление админами", callback_data="manage_admins")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_channels_keyboard(action: str = "select"):
    channels = get_channels()
    keyboard = []
    for channel_id, channel_name in channels:
        keyboard.append([InlineKeyboardButton(
            f"📢 {channel_name}", 
            callback_data=f"{action}_channel_{channel_id}"
        )])
    
    if action == "select":
        keyboard.append([InlineKeyboardButton("➕ Добавить канал", callback_data="add_channel")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_time_keyboard():
    keyboard = []
    times = [
        ("Через 15 мин", 15),
        ("Через 1 час", 60),
        ("Через 3 часа", 180),
        ("Завтра в это же время", 1440),
    ]
    
    for text, minutes in times:
        keyboard.append([InlineKeyboardButton(text, callback_data=f"time_{minutes}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="create_post")])
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard():
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]]
    return InlineKeyboardMarkup(keyboard)

def get_cancel_keyboard():
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="main_menu")]]
    return InlineKeyboardMarkup(keyboard)

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту. Обратитесь к администратору."
        )
        return
    
    await update.message.reply_text(
        "👋 Добро пожаловать в бота-публикатора!\n\n"
        "Выберите действие:",
        reply_markup=get_main_keyboard()
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ У вас нет доступа.")
        return
    
    data = query.data
    
    if data == "main_menu":
        await query.edit_message_text(
            "👋 Добро пожаловать в бота-публикатора!\n\nВыберите действие:",
            reply_markup=get_main_keyboard()
        )
    
    elif data == "create_post":
        channels = get_channels()
        if not channels:
            await query.edit_message_text(
                "❌ Нет добавленных каналов. Сначала добавьте канал.",
                reply_markup=get_back_keyboard()
            )
            return
            
        await query.edit_message_text(
            "📝 Выберите канал для публикации:",
            reply_markup=get_channels_keyboard("select")
        )
    
    elif data.startswith("select_channel_"):
        channel_id = data.replace("select_channel_", "")
        channel_name = next((name for cid, name in get_channels() if cid == channel_id), "Неизвестный канал")
        context.user_data['selected_channel'] = channel_id
        context.user_data['selected_channel_name'] = channel_name
        await query.edit_message_text(
            f"📝 Выбран канал: {channel_name}\n\n"
            "Отправьте текст поста или медиа-файл (фото, видео, документ):\n\n"
            "После отправки контента вы сможете выбрать время публикации.",
            reply_markup=get_cancel_keyboard()
        )
        context.user_data['waiting_for_content'] = True
    
    elif data.startswith("time_"):
        if 'post_content' not in context.user_data or 'selected_channel' not in context.user_data:
            await query.edit_message_text("❌ Ошибка: контент не найден.")
            return
        
        minutes = int(data.replace("time_", ""))
        schedule_time = datetime.now() + timedelta(minutes=minutes)
        
        post_id = add_post(
            content=context.user_data['post_content'],
            media_type=context.user_data.get('media_type', 'text'),
            media_file_id=context.user_data.get('media_file_id'),
            schedule_time=schedule_time,
            channel_id=context.user_data['selected_channel'],
            user_id=user_id
        )
        
        if post_id:
            await query.edit_message_text(
                f"✅ Пост успешно запланирован!\n\n"
                f"📅 Время публикации: {schedule_time.strftime('%d.%m.%Y %H:%M')}\n"
                f"📢 Канал: {context.user_data['selected_channel_name']}\n"
                f"📄 Тип: {context.user_data.get('media_type', 'текст')}",
                reply_markup=get_main_keyboard()
            )
            context.user_data.clear()
        else:
            await query.edit_message_text(
                "❌ Ошибка при сохранении поста.",
                reply_markup=get_main_keyboard()
            )
    
    elif data == "scheduled_posts":
        posts = get_scheduled_posts()
        if not posts:
            await query.edit_message_text(
                "📭 Нет запланированных постов.",
                reply_markup=get_main_keyboard()
            )
            return
        
        text = "📅 Запланированные посты:\n\n"
        for post in posts:
            post_id, content, schedule_time, channel_id, channel_name, status = post
            if isinstance(schedule_time, str):
                schedule_dt = datetime.strptime(schedule_time, '%Y-%m-%d %H:%M:%S')
            else:
                schedule_dt = schedule_time
            text += f"📝 ID: {post_id}\n"
            text += f"📢 Канал: {channel_name}\n"
            text += f"⏰ Время: {schedule_dt.strftime('%d.%m.%Y %H:%M')}\n"
            text += f"📄 Контент: {content[:50]}...\n"
            text += "─" * 30 + "\n"
        
        await query.edit_message_text(text, reply_markup=get_main_keyboard())
    
    elif data == "manage_channels":
        await query.edit_message_text(
            "⚙️ Управление каналами:",
            reply_markup=get_channels_keyboard("manage")
        )
    
    elif data == "add_channel":
        await query.edit_message_text(
            "📝 Чтобы добавить канал:\n\n"
            "1. Добавьте бота в канал как администратора\n"
            "2. Перешлите любое сообщение из канала в этот чат\n"
            "3. Бот автоматически добавит канал\n\n"
            "Или отправьте @username канала:",
            reply_markup=get_cancel_keyboard()
        )
        context.user_data['waiting_for_channel'] = True
    
    elif data == "manage_admins":
        admins = get_admins()
        text = "👥 Список администраторов:\n\n"
        text += f"👑 Главные администраторы (по ID): {', '.join(map(str, ADMIN_IDS))}\n\n"
        
        for admin_id, username in admins:
            if admin_id not in ADMIN_IDS:
                text += f"👤 {username or 'Без имени'} (ID: {admin_id})\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить админа", callback_data="add_admin")],
            [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data == "add_admin":
        await query.edit_message_text(
            "👤 Чтобы добавить администратора, отправьте его ID пользователя.\n\n"
            "ID можно получить с помощью бота @userinfobot\n\n"
            "Отправьте ID:",
            reply_markup=get_cancel_keyboard()
        )
        context.user_data['waiting_for_admin_id'] = True

# Обработчик сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ У вас нет доступа к этому боту.")
        return
    
    message = update.message
    
    # Обработка добавления канала через пересланное сообщение
    if message.forward_from_chat and message.forward_from_chat.type in ['channel', 'group']:
        channel_id = str(message.forward_from_chat.id)
        channel_name = message.forward_from_chat.title
        
        if add_channel(channel_id, channel_name, user_id):
            await message.reply_text(
                f"✅ Канал '{channel_name}' успешно добавлен!",
                reply_markup=get_main_keyboard()
            )
        else:
            await message.reply_text(
                "❌ Ошибка при добавлении канала.",
                reply_markup=get_main_keyboard()
            )
        context.user_data.pop('waiting_for_channel', None)
        return
    
    # Обработка добавления канала по username
    if context.user_data.get('waiting_for_channel'):
        text = message.text.strip()
        if text.startswith('@'):
            await message.reply_text(
                "❌ Добавление по username временно недоступно. "
                "Пожалуйста, перешлите сообщение из канала.",
                reply_markup=get_main_keyboard()
            )
        else:
            await message.reply_text(
                "❌ Неверный формат. Отправьте @username канала или перешлите сообщение.",
                reply_markup=get_main_keyboard()
            )
        context.user_data.pop('waiting_for_channel', None)
        return
    
    # Обработка добавления администратора по ID
    if context.user_data.get('waiting_for_admin_id'):
        try:
            new_admin_id = int(message.text)
            
            if new_admin_id in ADMIN_IDS:
                await message.reply_text(
                    "❌ Этот пользователь уже является главным администратором.",
                    reply_markup=get_main_keyboard()
                )
                return
            
            try:
                user = await context.bot.get_chat(new_admin_id)
                username = user.username or user.first_name or "Без имени"
                
                if add_admin(new_admin_id, username, user_id):
                    await message.reply_text(
                        f"✅ Администратор {username} успешно добавлен!",
                        reply_markup=get_main_keyboard()
                    )
                else:
                    await message.reply_text(
                        "❌ Ошибка при добавлении администратора.",
                        reply_markup=get_main_keyboard()
                    )
            except Exception as e:
                await message.reply_text(
                    "❌ Пользователь с таким ID не найден или бот не может с ним взаимодействовать.",
                    reply_markup=get_main_keyboard()
                )
            
            context.user_data.pop('waiting_for_admin_id', None)
        except ValueError:
            await message.reply_text(
                "❌ Пожалуйста, введите корректный ID (число).",
                reply_markup=get_main_keyboard()
            )
        return
    
    # Обработка контента для поста
    if context.user_data.get('waiting_for_content'):
        content = ""
        media_type = "text"
        media_file_id = None
        
        if message.text:
            content = message.text
        elif message.caption:
            content = message.caption
        
        if message.photo:
            media_type = "photo"
            media_file_id = message.photo[-1].file_id
        elif message.video:
            media_type = "video"
            media_file_id = message.video.file_id
        elif message.document:
            media_type = "document"
            media_file_id = message.document.file_id
        
        context.user_data['post_content'] = content
        context.user_data['media_type'] = media_type
        context.user_data['media_file_id'] = media_file_id
        
        channel_name = context.user_data.get('selected_channel_name', 'Неизвестный канал')
        
        preview_text = f"📝 Предпросмотр поста для канала {channel_name}:\n\n"
        if media_type == 'text':
            preview_text += f"{content}\n\n"
        else:
            preview_text += f"Тип: {media_type}\n"
            if content:
                preview_text += f"Подпись: {content}\n\n"
        
        preview_text += "⏰ Выберите время публикации:"
        
        if media_type == 'text':
            await message.reply_text(preview_text, reply_markup=get_time_keyboard())
        elif media_type == 'photo':
            await message.reply_photo(
                photo=media_file_id,
                caption=preview_text,
                reply_markup=get_time_keyboard()
            )
        elif media_type == 'video':
            await message.reply_video(
                video=media_file_id,
                caption=preview_text,
                reply_markup=get_time_keyboard()
            )
        elif media_type == 'document':
            await message.reply_document(
                document=media_file_id,
                caption=preview_text,
                reply_markup=get_time_keyboard()
            )
        
        context.user_data['waiting_for_content'] = False
        return
    
    await message.reply_text(
        "Выберите действие:",
        reply_markup=get_main_keyboard()
    )

# Функция для публикации запланированных постов
async def publish_scheduled_posts(context: ContextTypes.DEFAULT_TYPE):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, content, media_type, media_file_id, channel_id 
        FROM posts 
        WHERE status = 'scheduled' AND schedule_time <= datetime('now')
    ''')
    
    posts_to_publish = cursor.fetchall()
    
    for post in posts_to_publish:
        post_id, content, media_type, media_file_id, channel_id = post
        
        try:
            if media_type == 'text':
                await context.bot.send_message(
                    chat_id=channel_id,
                    text=content
                )
            elif media_type == 'photo':
                await context.bot.send_photo(
                    chat_id=channel_id,
                    photo=media_file_id,
                    caption=content
                )
            elif media_type == 'video':
                await context.bot.send_video(
                    chat_id=channel_id,
                    video=media_file_id,
                    caption=content
                )
            elif media_type == 'document':
                await context.bot.send_document(
                    chat_id=channel_id,
                    document=media_file_id,
                    caption=content
                )
            
            cursor.execute(
                'UPDATE posts SET status = "published" WHERE id = ?',
                (post_id,)
            )
            conn.commit()
            
            logger.info(f"Post {post_id} published to channel {channel_id}")
            
        except Exception as e:
            logger.error(f"Error publishing post {post_id}: {e}")
            cursor.execute(
                'UPDATE posts SET status = "error" WHERE id = ?',
                (post_id,)
            )
            conn.commit()
    
    conn.close()

async def post_init(application: Application):
    for admin_id in ADMIN_IDS:
        add_admin(admin_id, "Главный администратор", admin_id)
    
    commands = [
        BotCommand("start", "Запустить бота"),
    ]
    await application.bot.set_my_commands(commands)

# Основная функция
def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен!")
        return
    
    if not ADMIN_IDS:
        logger.error("ADMIN_IDS не установлены!")
        return
    
    init_db()
    
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.ALL, handle_message))
    
    application.job_queue.run_repeating(
        publish_scheduled_posts, 
        interval=60,
        first=10
    )
    
    if WEBHOOK_URL:
        logger.info("Starting bot in webhook mode...")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
        )
    else:
        logger.info("Starting bot in polling mode...")
        application.run_polling()

if __name__ == "__main__":
    main()
