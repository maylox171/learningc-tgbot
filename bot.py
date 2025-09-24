import re
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)

# -------------------------
# Константи / Стани
# -------------------------
ADMIN_IDS = [1000207683, 1485565692]
TOKEN = "8170304629:AAHqpnJsBboChDLnn0PPix6Vtoogof4c8Ts"
DB_NAME = "bot.db"

(LOGIN, PASSWORD, MENU_USER, MENU_ADMIN, MANAGE_LOGINS, ADD_USER_LOGIN, 
 ADD_USER_PASSWORD, DELETE_USER, THEORY_SELECT_USER, THEORY_DAY_MENU, 
 EDIT_DAY, SUPPORT, SEND_CODE_DAY, SEND_CODE, CHECK_CODE_SELECT_DAY, 
 CHECK_CODE_SELECT_USER, CHECK_CODE_VIEW, USER_SHOW_DAY_SELECTION, 
 ADMIN_REPLY_SUPPORT, ADMIN_REPLY_CODE) = range(20)

# -------------------------
# DB init & helpers
# -------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute("""CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        day TEXT,
        type TEXT,
        content TEXT,
        user_login TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        login TEXT UNIQUE,
        password TEXT,
        is_active INTEGER DEFAULT 1,
        telegram_id INTEGER
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS support_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_login TEXT,
        message TEXT,
        answered INTEGER DEFAULT 0,
        message_type TEXT DEFAULT 'support',
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS admin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER,
        action TEXT,
        target_user TEXT,
        day TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS user_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_login TEXT,
        day TEXT,
        code TEXT,
        status TEXT DEFAULT 'pending',
        admin_feedback TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS applied_days (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_login TEXT,
        type TEXT,
        day TEXT,
        admin_id INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")
    
    conn.commit()
    conn.close()

def log_admin_action(admin_id: int, action: str, target_user: str = None, day: str = None):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT INTO admin_logs (admin_id, action, target_user, day) VALUES (?, ?, ?, ?)",
                   (admin_id, action, target_user, day))
        conn.commit()

# -------------------------
# Utility: safe send/edit
# -------------------------
async def safe_edit_or_send(update: Update, message_text: str, markup: InlineKeyboardMarkup = None, parse_mode=None):
    """Безпечне редагування повідомлення при callback_query або відправка нового повідомлення."""
    if update.callback_query:
        msg = update.callback_query.message
        try:
            await msg.edit_text(message_text, reply_markup=markup, parse_mode=parse_mode)
        except Exception:
            await msg.reply_text(message_text, reply_markup=markup, parse_mode=parse_mode)
    elif update.message:
        await update.message.reply_text(message_text, reply_markup=markup, parse_mode=parse_mode)

async def send_message_to_admins(context: ContextTypes.DEFAULT_TYPE, message: str, markup: InlineKeyboardMarkup = None):
    """Надіслати повідомлення всім адмінам"""
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=message, reply_markup=markup)
        except Exception as e:
            print(f"Не вдалося надіслати повідомлення адміну {admin_id}: {e}")

# -------------------------
# Tasks / days helpers
# -------------------------
def get_tasks(task_type: str, login: str, day: str = None) -> str:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    if day:
        c.execute("SELECT content FROM tasks WHERE type=? AND user_login=? AND day=?", 
                 (task_type, login, day))
        row = c.fetchone()
        conn.close()
        if row and row[0] and row[0].strip():
            return row[0]
        else:
            return "❌ Завдання на цей день ще не додано."
    else:
        c.execute("SELECT day, content FROM tasks WHERE type=? AND user_login=?", 
                 (task_type, login))
        rows = c.fetchall()
        conn.close()
        if rows:
            return "\n\n".join([f"{d}:\n{t}" for (d, t) in rows])
        else:
            return "❌ Завдань ще немає."

def get_user_days(task_type: str, login: str):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT DISTINCT day FROM tasks WHERE type=? AND user_login=? ORDER BY day", 
             (task_type, login))
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def add_task(day: str, task_type: str, content: str, user_login: str):
    with sqlite3.connect(DB_NAME, timeout=5) as conn:
        conn.execute("INSERT INTO tasks (day, type, content, user_login) VALUES (?, ?, ?, ?)",
                   (day, task_type, content, user_login))
        conn.commit()

def update_task(day: str, task_type: str, content: str, user_login: str):
    with sqlite3.connect(DB_NAME, timeout=5) as conn:
        conn.execute("UPDATE tasks SET content=? WHERE day=? AND type=? AND user_login=?",
                   (content, day, task_type, user_login))
        conn.commit()

def get_day_content(task_type: str, login: str, day: str) -> str:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT content FROM tasks WHERE type=? AND user_login=? AND day=?", 
             (task_type, login, day))
    row = c.fetchone()
    if row and row[0] and row[0].strip():
        content = row[0]
    else:
        content = "❌ Завдання на цей день ще не додано."
    conn.close()
    return content

# -------------------------
# Codes & support
# -------------------------
def save_user_code(login: str, day: str, code_text: str):
    with sqlite3.connect(DB_NAME, timeout=5) as conn:
        cursor = conn.execute("INSERT INTO user_codes (user_login, day, code) VALUES (?, ?, ?)",
                           (login, day, code_text))
        code_id = cursor.lastrowid
        conn.commit()
        return code_id

def get_user_codes_by_day(day: str):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT DISTINCT user_login FROM user_codes WHERE day=? AND status='pending' ORDER BY user_login", 
             (day,))
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_user_code(login: str, day: str):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, code, status, timestamp FROM user_codes WHERE user_login=? AND day=? ORDER BY timestamp DESC LIMIT 1", 
             (login, day))
    row = c.fetchone()
    conn.close()
    return row

def get_pending_codes_days():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT DISTINCT day FROM user_codes WHERE status='pending' ORDER BY day")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def update_code_status(code_id: int, status: str, admin_feedback: str = None):
    with sqlite3.connect(DB_NAME) as conn:
        if admin_feedback:
            conn.execute("UPDATE user_codes SET status=?, admin_feedback=? WHERE id=?", 
                       (status, admin_feedback, code_id))
        else:
            conn.execute("UPDATE user_codes SET status=? WHERE id=?", (status, code_id))
        conn.commit()

def save_support_message(user_login: str, message: str, message_type: str = 'support'):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT INTO support_messages (user_login, message, answered, message_type) VALUES (?, ?, 0, ?)",
                   (user_login, message, message_type))
        conn.commit()

def get_unanswered_support():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("PRAGMA table_info(support_messages)")
    columns = [column[1] for column in c.fetchall()]
    if 'timestamp' in columns:
        c.execute("SELECT id, user_login, message, message_type FROM support_messages WHERE answered=0 ORDER BY timestamp")
    else:
        c.execute("SELECT id, user_login, message, message_type FROM support_messages WHERE answered=0 ORDER BY id")
    rows = c.fetchall()
    conn.close()
    return rows

def mark_support_answered(support_id: int):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("UPDATE support_messages SET answered=1 WHERE id=?", (support_id,))
        conn.commit()

# -------------------------
# Applied days
# -------------------------
def apply_day(user_login: str, task_type: str, day: str, admin_id: int):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT INTO applied_days (user_login, type, day, admin_id) VALUES (?, ?, ?, ?)",
                   (user_login, task_type, day, admin_id))
        conn.commit()

def get_applied_day(user_login: str, task_type: str):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT day FROM applied_days WHERE user_login=? AND type=? ORDER BY timestamp DESC LIMIT 1", 
             (user_login, task_type))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

# -------------------------
# Auto-create next day
# -------------------------
def _extract_numbers_from_string(s: str):
    return [int(x) for x in re.findall(r'\d+', s)]

def create_new_day_for_user(user_login: str, task_type: str) -> str:
    days = get_user_days(task_type, user_login)
    nums = []
    for d in days:
        found = _extract_numbers_from_string(d)
        if found:
            nums.extend(found)
    
    if nums:
        next_num = max(nums) + 1
    else:
        next_num = len(days) + 1
    
    new_day = f"День {next_num}"
    placeholder = ""
    add_task(new_day, task_type, placeholder, user_login)
    return new_day

# -------------------------
# Меню — адмін / юзер
# -------------------------
async def admin_main_menu(update: Update):
    keyboard = [
        [InlineKeyboardButton("Теорія", callback_data="admin_theory"),
         InlineKeyboardButton("Практика", callback_data="admin_practice")],
        [InlineKeyboardButton("Підтримка", callback_data="admin_support"),
         InlineKeyboardButton("Керувати логінами", callback_data="admin_manage")],
        [InlineKeyboardButton("Перевірити коди", callback_data="admin_check_codes")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await safe_edit_or_send(update, "✅ Меню адміністратора:", markup)
    return MENU_ADMIN

async def user_main_menu(update: Update, login: str):
    keyboard = [
        [InlineKeyboardButton("Теорія", callback_data="user_theory"),
         InlineKeyboardButton("Практика", callback_data="user_practice")],
        [InlineKeyboardButton("Надіслати код", callback_data="user_send_code"),
         InlineKeyboardButton("Зв'язатися з адміністратором", callback_data="user_support")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await safe_edit_or_send(update, f"✅ Головне меню для {login}:", markup)
    return MENU_USER

# -------------------------
# Старт / авторизація
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user_id = update.effective_user.id
    
    if user_id in ADMIN_IDS:
        return await admin_main_menu(update)
    
    await update.message.reply_text("Введіть свій логін:")
    return LOGIN

async def ask_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    login = update.message.text.strip()
    context.user_data["login"] = login
    await update.message.reply_text("Введіть пароль:")
    return PASSWORD

async def check_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    login = context.user_data.get("login")
    password = update.message.text.strip()
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, is_active FROM users WHERE login=? AND password=?", (login, password))
    row = c.fetchone()
    
    if row and row[1] == 1:
        c.execute("UPDATE users SET telegram_id=? WHERE id=?", (update.effective_user.id, row[0]))
        conn.commit()
        conn.close()
        return await user_main_menu(update, login)
    
    conn.close()
    await update.message.reply_text("⛔️ Невірний логін або заблокований користувач.")
    return LOGIN

# -------------------------
# Керування користувачами
# -------------------------
async def add_user_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_login"] = update.message.text.strip()
    await update.message.reply_text("Введіть пароль для нового користувача:")
    return ADD_USER_PASSWORD

async def add_user_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    login_new = context.user_data.get("new_login")
    admin_id = update.effective_user.id
    
    try:
        with sqlite3.connect(DB_NAME, timeout=5) as conn:
            conn.execute("INSERT INTO users (login, password, is_active) VALUES (?, ?, 1)", 
                       (login_new, password))
            conn.commit()
        log_admin_action(admin_id, "add_user", target_user=login_new)
        await update.message.reply_text(f"✅ Користувач {login_new} успішно доданий!")
    except sqlite3.IntegrityError:
        await update.message.reply_text("⛔️ Користувач з таким логіном вже існує!")
    
    return await manage_logins_menu(update)

async def manage_logins_menu(update: Update):
    keyboard = [
        [InlineKeyboardButton("Додати користувача", callback_data="add_user")],
        [InlineKeyboardButton("Видалити користувача", callback_data="delete_user")],
        [InlineKeyboardButton("Показати активних користувачів", callback_data="show_users")],
        [InlineKeyboardButton("Назад", callback_data="back_admin_main")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await safe_edit_or_send(update, "👤 Керування користувачами:", markup)
    return MANAGE_LOGINS

async def delete_user_menu(update: Update):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT login FROM users WHERE is_active=1")
    rows = c.fetchall()
    conn.close()
    
    users = [u[0] for u in rows if u[0]]
    keyboard = [[InlineKeyboardButton(u, callback_data=f"del_{u}")] for u in users]
    
    if users:
        keyboard.append([InlineKeyboardButton("Назад", callback_data="back_manage")])
        markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_or_send(update, "👤 Виберіть користувача для видалення:", markup)
    else:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_manage")]])
        await safe_edit_or_send(update, "❌ Активних користувачів немає.", markup)
    
    return DELETE_USER

async def show_active_users(update: Update):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT login FROM users WHERE is_active=1")
    rows = c.fetchall()
    conn.close()
    
    users = [u[0] for u in rows if u[0]]
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_manage")]])
    
    if not users:
        await safe_edit_or_send(update, "❌ Активних користувачів немає.", markup)
    else:
        text = "👤 Активні користувачі:\n" + "\n".join(users)
        await safe_edit_or_send(update, text, markup)
    
    return MANAGE_LOGINS

# -------------------------
# Вибір користувача і днів (адмін)
# -------------------------
async def select_user_for_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT login FROM users WHERE is_active=1")
    rows = c.fetchall()
    conn.close()
    
    users = [u[0] for u in rows if u[0]]
    keyboard = [[InlineKeyboardButton(u, callback_data=f"select_user_{u}")] for u in users]
    
    if users:
        keyboard.append([InlineKeyboardButton("Назад", callback_data="back_admin_main")])
        markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_or_send(update, "👤 Виберіть користувача:", markup)
    else:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_admin_main")]])
        await safe_edit_or_send(update, "❌ Активних користувачів немає.", markup)
    
    return THEORY_SELECT_USER

async def show_user_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_login = context.user_data.get("selected_user")
    task_type = context.user_data.get("task_type")
    
    if not user_login or not task_type:
        return await admin_main_menu(update)
    
    days = get_user_days(task_type, user_login)
    applied = get_applied_day(user_login, task_type)
    
    keyboard = [[InlineKeyboardButton(("✅ " if d == applied else "") + d, callback_data=f"select_day_{d}")] for d in days]
    keyboard.append([InlineKeyboardButton("➕ Додати новий день", callback_data="add_new_day")])
    keyboard.append([InlineKeyboardButton("Назад до користувачів", callback_data="back_to_users")])
    
    markup = InlineKeyboardMarkup(keyboard)
    
    if not days:
        await safe_edit_or_send(update, f"❌ Днів поки що немає для {user_login}. Можете додати новий день:", markup)
    else:
        await safe_edit_or_send(update, f"📖 Дні користувача {user_login}:", markup)
    
    return THEORY_DAY_MENU

# -------------------------
# Редагування/додавання дня (адмін)
# -------------------------
async def edit_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_login = context.user_data.get("selected_user")
    
    if not user_login:
        await update.message.reply_text("⛔️ Щось пішло не так (не знайдено користувача). Виконайте /start та повторіть.")
        return MENU_ADMIN
    
    task_type = context.user_data.get("task_type")
    day = context.user_data.get("current_day")
    
    if not (user_login and task_type and day):
        await update.message.reply_text("⛔️ Щось пішло не так. /start")
        return MENU_ADMIN
    
    days = get_user_days(task_type, user_login)
    
    if day in days:
        update_task(day, task_type, text, user_login)
        log_admin_action(update.effective_user.id, "edit_day", target_user=user_login, day=day)
        notice = f"✅ {day} оновлено для {user_login}."
    else:
        add_task(day, task_type, text, user_login)
        log_admin_action(update.effective_user.id, "add_day", target_user=user_login, day=day)
        notice = f"✅ {day} додано для {user_login}."
    
    content = get_day_content(task_type, user_login, day)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("Назад до днів", callback_data="back_to_days")]])
    await safe_edit_or_send(update, notice + "\n\n" + content, markup)
    return THEORY_DAY_MENU

# =========================
# Перевірка кодів (адмін)
# =========================
async def admin_check_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    days = get_pending_codes_days()
    days = [str(day) for day in days if day]
    
    if not days:
        await safe_edit_or_send(update, "✅ Немає кодів для перевірки.")
        return MENU_ADMIN
    
    keyboard = [[InlineKeyboardButton(day, callback_data=f"check_day_{day}")] for day in days]
    keyboard.append([InlineKeyboardButton("Назад", callback_data="back_admin_main")])
    markup = InlineKeyboardMarkup(keyboard)
    await safe_edit_or_send(update, "📅 Оберіть день для перевірки кодів:", markup)
    return CHECK_CODE_SELECT_DAY

async def select_check_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    day = query.data.replace("check_day_", "")
    context.user_data["check_day"] = day
    
    users = get_user_codes_by_day(day)
    users = [str(user) for user in users if user]
    
    if not users:
        await query.edit_message_text(f"❌ Коди за {day} відсутні.")
        return await admin_check_codes(update, context)
    
    keyboard = [[InlineKeyboardButton(user, callback_data=f"check_user_{user}")] for user in users]
    keyboard.append([InlineKeyboardButton("Назад", callback_data="admin_check_codes")])
    markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"👤 Оберіть користувача для перевірки кодів за {day}:", reply_markup=markup)
    return CHECK_CODE_SELECT_USER

async def view_user_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_login = query.data.replace("check_user_", "")
    day = context.user_data.get("check_day")
    context.user_data["current_user"] = user_login
    
    code_data = get_user_code(user_login, day)
    if not code_data:
        await query.edit_message_text("❌ Код не знайдено.")
        return await select_check_day(update, context)
    
    code_id, code_text, status, timestamp = code_data
    context.user_data["current_code_id"] = code_id
    
    message = f"📄 Код від {user_login} за {day} ({timestamp}):\n\n{code_text}"
    keyboard = [
        [InlineKeyboardButton("✅ Позначити як прочитане", callback_data=f"mark_code_ok_{code_id}")],
        [InlineKeyboardButton("💬 Відповісти користувачеві", callback_data=f"reply_code_{code_id}")],
        [InlineKeyboardButton("Назад", callback_data=f"back_to_check_users_{day}")]
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message, reply_markup=markup)
    return CHECK_CODE_VIEW

async def mark_code_as_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    code_id = int(query.data.replace("mark_code_ok_", ""))
    update_code_status(code_id, "approved")
    log_admin_action(update.effective_user.id, "mark_code_approved")
    
    await query.edit_message_text("✅ Код позначено як прочитаний та правильний.")
    return await admin_check_codes(update, context)

async def start_reply_to_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    code_id = int(query.data.replace("reply_code_", ""))
    context.user_data["reply_code_id"] = code_id
    await query.edit_message_text("Введіть відповідь користувачеві:")
    return ADMIN_REPLY_CODE

async def admin_send_code_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code_id = context.user_data.get("reply_code_id")
    reply_text = update.message.text.strip()
    
    if not code_id:
        await update.message.reply_text("⛔️ Немає коду для відповіді.")
        return MENU_ADMIN
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT user_login FROM user_codes WHERE id=?", (code_id,))
    row = c.fetchone()
    
    if not row:
        conn.close()
        await update.message.reply_text("⛔️ Код не знайдено.")
        return MENU_ADMIN
    
    user_login = row[0]
    c.execute("SELECT telegram_id FROM users WHERE login=?", (user_login,))
    r2 = c.fetchone()
    
    if r2 and r2[0]:
        user_tid = r2[0]
        try:
            await context.bot.send_message(chat_id=user_tid, text=f"💬 Відповідь адміністратора на ваш код:\n\n{reply_text}")
            update_code_status(code_id, "replied", reply_text)
            log_admin_action(update.effective_user.id, "reply_to_code", target_user=user_login)
            await update.message.reply_text("✅ Відповідь надіслано користувачу.")
        except Exception:
            await update.message.reply_text("⛔️ Не вдалося надіслати повідомлення користувачу.")
    else:
        await update.message.reply_text("⛔️ Не знайдено telegram_id користувача.")
    
    conn.close()
    return await admin_check_codes(update, context)

# -------------------------
# Надіслати код (юзер)
# -------------------------
async def user_send_code_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    login = context.user_data.get("login")
    if not login:
        await safe_edit_or_send(update, "⛔️ Будь ласка, авторизуйтесь /start")
        return LOGIN
    
    days = get_user_days("practice", login)
    if not days:
        await safe_edit_or_send(update, "❌ У вас немає днів для надсилання коду.")
        return await user_main_menu(update, login)
    
    keyboard = [[InlineKeyboardButton(day, callback_data=f"code_day_{day}")] for day in days]
    keyboard.append([InlineKeyboardButton("Назад", callback_data="back_user_menu")])
    markup = InlineKeyboardMarkup(keyboard)
    await safe_edit_or_send(update, "📅 Оберіть день для надсилання коду:", markup)
    return SEND_CODE_DAY

async def select_code_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    day = query.data.replace("code_day_", "")
    context.user_data["code_day"] = day
    await query.edit_message_text(f"📝 Введіть код для {day}:")
    return SEND_CODE

async def send_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    login = context.user_data.get("login")
    day = context.user_data.get("code_day")
    
    if not login or not day:
        await update.message.reply_text("⛔️ Помилка: не знайдено логін або день")
        return await user_main_menu(update, login)
    
    code_text = update.message.text.strip()
    code_id = save_user_code(login, day, code_text)
    
    admin_message = f"📨 Новий код від {login} за {day}:\n\n{code_text}"
    admin_keyboard = [[InlineKeyboardButton("Перевірити код", callback_data=f"check_day_{day}")]]
    admin_markup = InlineKeyboardMarkup(admin_keyboard)
    await send_message_to_admins(context, admin_message, admin_markup)
    
    await update.message.reply_text("✅ Ваш код надіслано адміністраторам для перевірки.")
    return await user_main_menu(update, login)

# -------------------------
# Підтримка (юзер/адмін)
# -------------------------
async def user_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    login = context.user_data.get("login")
    message = update.message.text.strip()
    
    if login:
        save_support_message(login, message)
        admin_message = f"📩 Нове повідомлення підтримки від {login}:\n\n{message}"
        admin_keyboard = [[InlineKeyboardButton("Переглянути", callback_data="admin_support")]]
        admin_markup = InlineKeyboardMarkup(admin_keyboard)
        await send_message_to_admins(context, admin_message, admin_markup)
        await update.message.reply_text("✅ Ваше питання надіслано адміністраторам.")
        return await user_main_menu(update, login)
    else:
        await update.message.reply_text("⛔️ Не знайдено логін. /start")
        return LOGIN

async def admin_show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_unanswered_support()
    keyboard = []
    
    for r in rows:
        sid, ulogin, msg, msg_type = r
        preview = msg if len(msg) <= 40 else msg[:37] + "..."
        type_emoji = "📨" if msg_type == 'support' else "📄"
        keyboard.append([InlineKeyboardButton(f"{type_emoji} {ulogin}: {preview}", callback_data=f"view_support_{sid}")])
    
    keyboard.append([InlineKeyboardButton("Назад", callback_data="back_admin_main")])
    markup = InlineKeyboardMarkup(keyboard)
    
    if not rows:
        await safe_edit_or_send(update, "✅ Немає нових повідомлень.", markup)
    else:
        await safe_edit_or_send(update, "📩 Нові повідомлення:", markup)
    
    return MENU_ADMIN

async def view_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    sid = int(data.replace("view_support_", ""))
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT user_login, message, message_type FROM support_messages WHERE id=?", (sid,))
    row = c.fetchone()
    conn.close()
    
    if row:
        ulogin, msg, msg_type = row
        type_text = "підтримки" if msg_type == 'support' else "коду"
        keyboard = [
            [InlineKeyboardButton("Відповісти", callback_data=f"reply_support_{sid}")],
            [InlineKeyboardButton("Позначити як відповіли", callback_data=f"mark_support_{sid}")],
            [InlineKeyboardButton("Назад", callback_data="admin_support")]
        ]
        markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_or_send(update, f"📨 Повідомлення {type_text} від {ulogin}:\n\n{msg}", markup)
    else:
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="admin_support")]])
        await safe_edit_or_send(update, "❌ Повідомлення не знайдено.", markup)
    
    return MENU_ADMIN

async def start_reply_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    sid = int(data.replace("reply_support_", ""))
    context.user_data["reply_support_id"] = sid
    await safe_edit_or_send(update, "Введіть відповідь, яку хочете надіслати користувачу:")
    return ADMIN_REPLY_SUPPORT

async def admin_send_support_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sid = context.user_data.get("reply_support_id")
    reply_text = update.message.text.strip()
    
    if not sid:
        await update.message.reply_text("⛔️ Немає повідомлення для відповіді.")
        return MENU_ADMIN
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT user_login FROM support_messages WHERE id=?", (sid,))
    row = c.fetchone()
    
    if not row:
        conn.close()
        await update.message.reply_text("⛔️ Оригінальне повідомлення не знайдено.")
        return MENU_ADMIN
    
    user_login = row[0]
    c.execute("SELECT telegram_id FROM users WHERE login=?", (user_login,))
    r2 = c.fetchone()
    
    if r2 and r2[0]:
        user_tid = r2[0]
        try:
            await context.bot.send_message(chat_id=user_tid, text=f"💬 Відповідь адміністратора:\n\n{reply_text}")
            mark_support_answered(sid)
            log_admin_action(update.effective_user.id, "reply_support", target_user=user_login)
            await update.message.reply_text("✅ Відповідь надіслано користувачу.")
        except Exception:
            await update.message.reply_text("⛔️ Не вдалось надіслати повідомлення користувачу.")
    else:
        await update.message.reply_text("⛔️ Не знайдено telegram_id користувача.")
    
    conn.close()
    return await admin_show_support(update, context)

async def mark_support_as_answered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    sid = int(data.replace("mark_support_", ""))
    mark_support_answered(sid)
    
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="admin_support")]])
    await safe_edit_or_send(update, "✅ Повідомлення позначено як відповілене.", markup)
    return MENU_ADMIN

# -------------------------
# Центральний callback handler
# -------------------------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    
    data = update.callback_query.data if update.callback_query else None
    login = context.user_data.get("login")
    
    # ---------------- Admin navigation ----------------
    if data == "back_admin_main":
        return await admin_main_menu(update)
    
    elif data == "back_manage":
        return await manage_logins_menu(update)
    
    elif data == "back_to_users":
        return await select_user_for_task(update, context)
    
    elif data == "back_to_days":
        return await show_user_days(update, context)
    
    elif data.startswith("back_to_check_users_"):
        day = data.replace("back_to_check_users_", "")
        context.user_data["check_day"] = day
        return await select_check_day(update, context)
    
    elif data == "admin_manage":
        return await manage_logins_menu(update)
    
    elif data == "admin_theory":
        context.user_data["task_type"] = "theory"
        return await select_user_for_task(update, context)
    
    elif data == "admin_practice":
        context.user_data["task_type"] = "practice"
        return await select_user_for_task(update, context)
    
    elif data == "admin_check_codes":
        return await admin_check_codes(update, context)
    
    elif data == "admin_support":
        return await admin_show_support(update, context)
    
    elif data == "add_user":
        await safe_edit_or_send(update, "Введіть логін нового користувача:")
        return ADD_USER_LOGIN
    
    elif data == "delete_user":
        return await delete_user_menu(update)
    
    elif data == "show_users":
        return await show_active_users(update)
    
    elif data.startswith("del_"):
        login_to_delete = data.replace("del_", "")
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("UPDATE users SET is_active=0 WHERE login=?", (login_to_delete,))
            conn.commit()
        log_admin_action(update.effective_user.id, "deactivate_user", target_user=login_to_delete)
        return await delete_user_menu(update)
    
    elif data.startswith("select_user_"):
        sel = data.replace("select_user_", "")
        context.user_data["selected_user"] = sel
        return await show_user_days(update, context)
    
    elif data.startswith("select_day_"):
        day_sel = data.replace("select_day_", "")
        context.user_data["current_day"] = day_sel
        user_login = context.user_data.get("selected_user")
        task_type = context.user_data.get("task_type")
        content = get_day_content(task_type, user_login, day_sel)
        
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("Назад до днів", callback_data="back_to_days")]])
        await safe_edit_or_send(update, content + "\n\nВведіть новий текст для редагування цього дня:", markup)
        return EDIT_DAY
    
    elif data == "add_new_day":
        user_login = context.user_data.get("selected_user")
        task_type = context.user_data.get("task_type")
        
        if not user_login or not task_type:
            await safe_edit_or_send(update, "⛔️ Не вдалося створити день.")
            return await admin_main_menu(update)
        
        new_day = create_new_day_for_user(user_login, task_type)
        log_admin_action(update.effective_user.id, "create_new_day", target_user=user_login, day=new_day)
        context.user_data["current_day"] = new_day
        
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("Назад до днів", callback_data="back_to_days")]])
        await safe_edit_or_send(update, f"✅ Створено: {new_day} для {user_login}.\n\nВведіть текст:", markup)
        return EDIT_DAY
    
    # ---------------- Code checking ----------------
    elif data.startswith("check_day_"):
        return await select_check_day(update, context)
    
    elif data.startswith("check_user_"):
        return await view_user_code(update, context)
    
    elif data.startswith("mark_code_ok_"):
        return await mark_code_as_ok(update, context)
    
    elif data.startswith("reply_code_"):
        return await start_reply_to_code(update, context)
    
    # ---------------- User code sending ----------------
    elif data == "user_send_code":
        return await user_send_code_start(update, context)
    
    elif data.startswith("code_day_"):
        return await select_code_day(update, context)
    
    # ---------------- Support ----------------
    elif data.startswith("view_support_"):
        return await view_support_message(update, context)
    
    elif data.startswith("reply_support_"):
        return await start_reply_support(update, context)
    
    elif data.startswith("mark_support_"):
        return await mark_support_as_answered(update, context)
    
    # ---------------- User area ----------------
    elif data == "back_user_menu":
        return await user_main_menu(update, login)
    
    elif data == "user_theory":
        if not login:
            await safe_edit_or_send(update, "⛔️ Будь ласка, авторизуйтесь /start")
            return LOGIN
        
        applied = get_applied_day(login, "theory")
        if applied:
            content = get_tasks("theory", login, applied)
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("Головне меню", callback_data="back_user_menu")]])
            await safe_edit_or_send(update, f"📖 Ваш день (ТЕОРІЯ): {applied}\n\n{content}", markup)
            return MENU_USER
        
        days = get_user_days("theory", login)
        if not days:
            await safe_edit_or_send(update, get_tasks("theory", login))
            return MENU_USER
        
        keyboard = [[InlineKeyboardButton(day, callback_data=f"user_day_theory_{day}")] for day in days]
        keyboard.append([InlineKeyboardButton("Назад", callback_data="back_user_menu")])
        markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_or_send(update, "📖 Оберіть день теорії для перегляду:", markup)
        return USER_SHOW_DAY_SELECTION
    
    elif data == "user_practice":
        if not login:
            await safe_edit_or_send(update, "⛔️ Будь ласка, авторизуйтесь /start")
            return LOGIN
        
        applied = get_applied_day(login, "practice")
        if applied:
            content = get_tasks("practice", login, applied)
            markup = InlineKeyboardMarkup([[InlineKeyboardButton("Головне меню", callback_data="back_user_menu")]])
            await safe_edit_or_send(update, f"📖 Ваш день (ПРАКТИКА): {applied}\n\n{content}", markup)
            return MENU_USER
        
        days = get_user_days("practice", login)
        if not days:
            await safe_edit_or_send(update, get_tasks("practice", login))
            return MENU_USER
        
        keyboard = [[InlineKeyboardButton(day, callback_data=f"user_day_practice_{day}")] for day in days]
        keyboard.append([InlineKeyboardButton("Назад", callback_data="back_user_menu")])
        markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_or_send(update, "📖 Оберіть день практики для перегляду:", markup)
        return USER_SHOW_DAY_SELECTION
    
    elif data.startswith("user_day_theory_"):
        day_sel = data.replace("user_day_theory_", "")
        content = get_tasks("theory", login, day_sel)
        keyboard = [
            [InlineKeyboardButton("Назад", callback_data="user_theory")],
            [InlineKeyboardButton("Головне меню", callback_data="back_user_menu")]
        ]
        markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_or_send(update, content, markup)
        return MENU_USER
    
    elif data.startswith("user_day_practice_"):
        day_sel = data.replace("user_day_practice_", "")
        content = get_tasks("practice", login, day_sel)
        keyboard = [
            [InlineKeyboardButton("Назад", callback_data="user_practice")],
            [InlineKeyboardButton("Головне меню", callback_data="back_user_menu")]
        ]
        markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_or_send(update, content, markup)
        return MENU_USER
    
    elif data == "user_support":
        await safe_edit_or_send(update, "Введіть ваше питання для адміністратора:")
        return SUPPORT
    
    # ---------------- Default fallback ----------------
    if update.effective_user.id in ADMIN_IDS:
        return await admin_main_menu(update)
    else:
        if login:
            return await user_main_menu(update, login)
        else:
            await safe_edit_or_send(update, "⛔️ Будь ласка, авторизуйтесь /start")
            return LOGIN

# -------------------------
# Запуск
# -------------------------
def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_password)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_password)],
            MENU_ADMIN: [CallbackQueryHandler(callback_handler)],
            MENU_USER: [CallbackQueryHandler(callback_handler)],
            MANAGE_LOGINS: [CallbackQueryHandler(callback_handler)],
            ADD_USER_LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user_login)],
            ADD_USER_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user_password)],
            DELETE_USER: [CallbackQueryHandler(callback_handler)],
            THEORY_SELECT_USER: [CallbackQueryHandler(callback_handler)],
            THEORY_DAY_MENU: [CallbackQueryHandler(callback_handler)],
            EDIT_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_day)],
            SUPPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, user_support)],
            SEND_CODE_DAY: [CallbackQueryHandler(callback_handler)],
            SEND_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_code)],
            CHECK_CODE_SELECT_DAY: [CallbackQueryHandler(callback_handler)],
            CHECK_CODE_SELECT_USER: [CallbackQueryHandler(callback_handler)],
            CHECK_CODE_VIEW: [CallbackQueryHandler(callback_handler)],
            USER_SHOW_DAY_SELECTION: [CallbackQueryHandler(callback_handler)],
            ADMIN_REPLY_SUPPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_send_support_reply)],
            ADMIN_REPLY_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_send_code_reply)]
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True
    )
    
    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()