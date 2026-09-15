import logging
import os
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)
from telegram.error import TimedOut, NetworkError

# --- Configuration ---
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
DATABASE_URL = os.environ["DATABASE_URL"]

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
TITLE, BODY, REMINDER_TEXT, REMINDER_TIME = range(4)

# --- Database Helpers ---
def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS entries (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        title TEXT,
        body TEXT,
        date TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS reminders (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        text TEXT,
        remind_time TIMESTAMP,
        active INTEGER DEFAULT 1
    )''')
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")

def save_entry(user_id, title, body):
    conn = get_conn()
    c = conn.cursor()
    date = datetime.now().strftime("%Y-%m-%d")
    c.execute("INSERT INTO entries (user_id, title, body, date) VALUES (%s, %s, %s, %s)",
              (user_id, title, body, date))
    conn.commit()
    conn.close()

def get_entries(user_id, limit=10):
    conn = get_conn()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute("SELECT title, body, date FROM entries WHERE user_id = %s ORDER BY timestamp DESC LIMIT %s",
              (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows

def save_reminder(user_id, text, remind_time):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO reminders (user_id, text, remind_time) VALUES (%s, %s, %s)",
              (user_id, text, remind_time))
    conn.commit()
    conn.close()

def get_active_reminders(user_id):
    conn = get_conn()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute("SELECT id, text, remind_time FROM reminders WHERE user_id = %s AND active = 1 ORDER BY remind_time",
              (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_due_reminders():
    conn = get_conn()
    c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute("SELECT id, user_id, text FROM reminders WHERE active = 1 AND remind_time <= %s",
              (datetime.now(),))
    rows = c.fetchall()
    conn.close()
    return rows

def mark_reminder_sent(reminder_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE reminders SET active = 0 WHERE id = %s", (reminder_id,))
    conn.commit()
    conn.close()

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"🌟 Hi {user.first_name}! I'm your Personal Diary & Reminder Bot!\n\n"
        "📝 /diary - Write a new diary entry\n"
        "📖 /read - Read your recent diary entries\n"
        "⏰ /remind - Set a reminder\n"
        "📋 /myreminders - List active reminders\n"
        "❌ /deletereminder - Delete a reminder\n"
        "🆘 /help - Show this message\n\n"
        "Your thoughts are safe and private with me! 💙"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# --- Diary Conversation ---
async def diary_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 What's the title of your diary entry?")
    return TITLE

async def diary_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['diary_title'] = update.message.text
    await update.message.reply_text("✍️ Now write the content of your entry:")
    return BODY

async def diary_body(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = context.user_data.get('diary_title', 'Untitled')
    body = update.message.text
    save_entry(update.effective_user.id, title, body)
    await update.message.reply_text(f"✅ Diary entry '{title}' saved successfully!")
    return ConversationHandler.END

async def diary_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Diary entry cancelled.")
    return ConversationHandler.END

async def read_entries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    entries = get_entries(update.effective_user.id)
    if not entries:
        await update.message.reply_text("📭 No diary entries yet. Use /diary to write one!")
        return
    response = "📖 Your Recent Diary Entries:\n\n"
    for i, entry in enumerate(entries, 1):
        body_preview = entry['body'][:150] + "..." if len(entry['body']) > 150 else entry['body']
        response += f"*{i}. {entry['title']}*\n📅 {entry['date']}\n{body_preview}\n\n"
    await update.message.reply_text(response, parse_mode='Markdown')

# --- Reminder Conversation ---
async def reminder_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏰ What reminder would you like to set?")
    return REMINDER_TEXT

async def reminder_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['reminder_text'] = update.message.text
    await update.message.reply_text(
        "📅 When should I remind you?\n\n"
        "Format: YYYY-MM-DD HH:MM (UTC time)\n"
        "Example: 2026-09-15 15:00"
    )
    return REMINDER_TIME

async def reminder_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        remind_time = datetime.strptime(update.message.text, "%Y-%m-%d %H:%M")
        if remind_time < datetime.now():
            await update.message.reply_text("❌ That time is in the past! Please pick a future time:")
            return REMINDER_TIME
        save_reminder(update.effective_user.id, context.user_data.get('reminder_text'), remind_time)
        await update.message.reply_text(f"✅ Reminder saved! I'll remind you at {remind_time.strftime('%Y-%m-%d %H:%M')} UTC")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Invalid format! Use: YYYY-MM-DD HH:MM")
        return REMINDER_TIME

async def reminder_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Reminder creation cancelled.")
    return ConversationHandler.END

async def my_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reminders = get_active_reminders(update.effective_user.id)
    if not reminders:
        await update.message.reply_text("📭 No active reminders.")
        return
    response = "⏰ Your Active Reminders:\n\n"
    for r in reminders:
        response += f"• {r['text']}\n  📅 {r['remind_time']} UTC\n  ID: `{r['id']}`\n\n"
    await update.message.reply_text(response, parse_mode='Markdown')

async def delete_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        parts = update.message.text.split()
        if len(parts) < 2:
            await update.message.reply_text("Usage: /deletereminder [id]")
            return
        reminder_id = int(parts[1])
        conn = get_conn()
        c = conn.cursor()
        c.execute("UPDATE reminders SET active = 0 WHERE id = %s AND user_id = %s",
                  (reminder_id, update.effective_user.id))
        rows = c.rowcount
        conn.commit()
        conn.close()
        if rows > 0:
            await update.message.reply_text(f"✅ Reminder {reminder_id} deleted!")
        else:
            await update.message.reply_text(f"❌ Reminder {reminder_id} not found.")
    except ValueError:
        await update.message.reply_text("❌ Please provide a valid numeric ID.")

# --- Reminder Scheduler ---
async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    try:
        due = get_due_reminders()
        for r in due:
            try:
                await context.bot.send_message(
                    chat_id=r['user_id'],
                    text=f"🔔 *Reminder:* {r['text']}",
                    parse_mode='Markdown'
                )
                mark_reminder_sent(r['id'])
                print(f"🔔 Sent reminder {r['id']} to user {r['user_id']}")
            except Exception as e:
                print(f"⚠️ Failed to send reminder {r['id']}: {e}")
    except Exception as e:
        print(f"⚠️ Scheduler error: {e}")

# --- Main ---
def main():
    print("🤖 Personal Diary Bot Starting...")
    init_db()
    
    application = Application.builder() \
        .token(TOKEN) \
        .connect_timeout(30.0) \
        .read_timeout(30.0) \
        .build()
    
    # Schedule reminder checks every 30 seconds
    job_queue = application.job_queue
    job_queue.run_repeating(check_reminders, interval=30, first=10)
    
    # Diary conversation
    diary_conv = ConversationHandler(
        entry_points=[CommandHandler('diary', diary_start)],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_title)],
            BODY: [MessageHandler(filters.TEXT & ~filters.COMMAND, diary_body)],
        },
        fallbacks=[CommandHandler('cancel', diary_cancel)],
    )
    
    # Reminder conversation
    reminder_conv = ConversationHandler(
        entry_points=[CommandHandler('remind', reminder_start)],
        states={
            REMINDER_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_text)],
            REMINDER_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_time)],
        },
        fallbacks=[CommandHandler('cancel', reminder_cancel)],
    )
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('read', read_entries))
    application.add_handler(CommandHandler('myreminders', my_reminders))
    application.add_handler(CommandHandler('deletereminder', delete_reminder))
    application.add_handler(diary_conv)
    application.add_handler(reminder_conv)
    
    print("✅ Bot is running!")
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    except TimedOut:
        print("❌ Connection timed out.")
    except NetworkError:
        print("❌ Network error.")

if __name__ == '__main__':
    main()
