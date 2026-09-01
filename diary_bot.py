import logging
import sqlite3
import sys
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from telegram.error import TimedOut, NetworkError

# --- Configuration ---
TOKEN = "API KEY HERE"  # Replace with your token

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
TITLE, BODY, REMINDER_TEXT, REMINDER_TIME = range(4)

# --- Database Setup ---
def init_db():
    """Create the database tables if they don't exist"""
    conn = sqlite3.connect('diary_bot.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS entries
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  title TEXT,
                  body TEXT,
                  date TEXT,
                  timestamp TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS reminders
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  text TEXT,
                  remind_time TEXT,
                  active INTEGER DEFAULT 1)''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message when /start is issued"""
    user = update.effective_user
    welcome_text = f"""
🌟 Hi {user.first_name}! I'm your Personal Diary & Reminder Bot!

Here's what I can do for you:

📝 /diary - Write a new diary entry
📖 /read - Read your recent diary entries
⏰ /remind - Set a reminder
📋 /myreminders - List your active reminders
❌ /deletereminder - Delete a reminder
🆘 /help - Show this message again

Your thoughts are safe and private with me! 💙
"""
    await update.message.reply_text(welcome_text)
    print(f"👋 User {user.first_name} started the bot")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a help message"""
    await start(update, context)

# --- Diary Conversation Handlers ---
async def diary_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the diary entry conversation"""
    await update.message.reply_text("📝 What's the title of your diary entry?")
    return TITLE

async def diary_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save the title and ask for body"""
    context.user_data['diary_title'] = update.message.text
    await update.message.reply_text("✍️ Now write the content of your entry:")
    return BODY

async def diary_body(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save the body and finish the diary entry"""
    title = context.user_data.get('diary_title', 'Untitled')
    body = update.message.text
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('diary_bot.db')
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date = datetime.now().strftime("%Y-%m-%d")
    
    c.execute("INSERT INTO entries (user_id, title, body, date, timestamp) VALUES (?, ?, ?, ?, ?)",
              (user_id, title, body, date, now))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ Diary entry '{title}' saved successfully!")
    return ConversationHandler.END

async def diary_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the diary entry conversation"""
    await update.message.reply_text("❌ Diary entry cancelled.")
    return ConversationHandler.END

async def read_entries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show recent diary entries"""
    user_id = update.effective_user.id
    conn = sqlite3.connect('diary_bot.db')
    c = conn.cursor()
    c.execute("SELECT title, body, date FROM entries WHERE user_id = ? ORDER BY timestamp DESC LIMIT 10",
              (user_id,))
    entries = c.fetchall()
    conn.close()
    
    if not entries:
        await update.message.reply_text("📭 You don't have any diary entries yet. Write one with /diary!")
        return
    
    response = "📖 Your Recent Diary Entries:\n\n"
    for i, (title, body, date) in enumerate(entries, 1):
        body_preview = body[:150] + "..." if len(body) > 150 else body
        response += f"*{i}. {title}*\n📅 {date}\n{body_preview}\n\n"
    
    await update.message.reply_text(response, parse_mode='Markdown')

# --- Reminder Handlers ---
async def reminder_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start the reminder conversation"""
    await update.message.reply_text("⏰ What reminder would you like to set?\n\n(Example: 'Call mom at 3pm')")
    return REMINDER_TEXT

async def reminder_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save reminder text and ask for time"""
    context.user_data['reminder_text'] = update.message.text
    await update.message.reply_text("📅 When should I remind you?\n\nFormat: YYYY-MM-DD HH:MM\nExample: 2026-09-01 15:00")
    return REMINDER_TIME

async def reminder_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Save the reminder with time"""
    try:
        reminder_text = context.user_data.get('reminder_text')
        remind_time = datetime.strptime(update.message.text, "%Y-%m-%d %H:%M")
        user_id = update.effective_user.id
        
        conn = sqlite3.connect('diary_bot.db')
        c = conn.cursor()
        c.execute("INSERT INTO reminders (user_id, text, remind_time) VALUES (?, ?, ?)",
                  (user_id, reminder_text, remind_time.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(f"✅ Reminder saved! I'll remind you at {remind_time.strftime('%Y-%m-%d %H:%M')}")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Invalid format! Please use: YYYY-MM-DD HH:MM\nExample: 2026-09-01 15:00")
        return REMINDER_TIME

async def reminder_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the reminder conversation"""
    await update.message.reply_text("❌ Reminder creation cancelled.")
    return ConversationHandler.END

async def my_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all active reminders"""
    user_id = update.effective_user.id
    conn = sqlite3.connect('diary_bot.db')
    c = conn.cursor()
    c.execute("SELECT id, text, remind_time FROM reminders WHERE user_id = ? AND active = 1", (user_id,))
    reminders = c.fetchall()
    conn.close()
    
    if not reminders:
        await update.message.reply_text("📭 You have no active reminders.")
        return
    
    response = "⏰ Your Active Reminders:\n\n"
    for reminder_id, text, remind_time in reminders:
        response += f"• {text}\n  📅 {remind_time}\n  ID: `{reminder_id}`\n\n"
    
    await update.message.reply_text(response, parse_mode='Markdown')

async def delete_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a reminder by ID"""
    try:
        command_parts = update.message.text.split()
        if len(command_parts) < 2:
            await update.message.reply_text("Usage: /deletereminder [reminder_id]\n\nGet the ID from /myreminders")
            return
        
        reminder_id = int(command_parts[1])
        
        conn = sqlite3.connect('diary_bot.db')
        c = conn.cursor()
        c.execute("UPDATE reminders SET active = 0 WHERE id = ? AND user_id = ?", 
                  (reminder_id, update.effective_user.id))
        rows_affected = conn.rowcount
        conn.commit()
        conn.close()
        
        if rows_affected > 0:
            await update.message.reply_text(f"✅ Reminder {reminder_id} deleted!")
        else:
            await update.message.reply_text(f"❌ Reminder {reminder_id} not found or already deleted.")
            
    except ValueError:
        await update.message.reply_text("❌ Please provide a valid reminder ID number.\n\nGet the ID from /myreminders")

# --- Main Function ---
def main():
    """Start the bot with retry logic"""
    print("🤖 Personal Diary Bot Starting...")
    
    # Initialize database
    init_db()
    
    # Create the Application with timeout settings
    application = Application.builder() \
        .token(TOKEN) \
        .connect_timeout(30.0) \
        .read_timeout(30.0) \
        .build()
    
    # --- Conversation Handlers ---
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
    
    # --- Add Handlers ---
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('read', read_entries))
    application.add_handler(CommandHandler('myreminders', my_reminders))
    application.add_handler(CommandHandler('deletereminder', delete_reminder))
    application.add_handler(diary_conv)
    application.add_handler(reminder_conv)
    
    # Start the Bot with retry logic
    print("✅ Bot is running!")
    print("📱 Press Ctrl+C to stop the bot")
    
    # Run with error handling
    try:
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True
        )
    except TimedOut:
        print("❌ Connection timed out. Please check your internet connection.")
        print("💡 Try these fixes:")
        print("   1. Check if you're connected to the internet")
        print("   2. Disable VPN or proxy if you're using one")
        print("   3. Try running: ping api.telegram.org")
        sys.exit(1)
    except NetworkError:
        print("❌ Network error. Please check your internet connection.")
        sys.exit(1)

if __name__ == '__main__':
    main()
