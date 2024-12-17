import random
from telegram import Update, MessageEntity
from pymongo import MongoClient
import logging
import secrets
from datetime import datetime, timedelta
from telegram.ext import CallbackContext
from html import escape

# MongoDB setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
users_collection = db['users']

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# MongoDB utility functions
def get_user_by_id(user_id):
    return users_collection.find_one({"user_id": user_id})

def update_user_credits(user_id, amount):
    users_collection.update_one(
        {"user_id": user_id},
        {"$inc": {"credits": amount}}
    )
def escape_markdown_v2(text):
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)

def get_ist_time() -> str:
    """Return the current time in IST (Indian Standard Time) as a formatted string."""
    # Add 5 hours and 30 minutes to UTC
    ist_time = datetime.utcnow() + timedelta(hours=5, minutes=30)
    return ist_time.strftime('%Y-%m-%d %I:%M:%S %p')  # Example: 2024-06-15 04:30 PM

def escape_html(text: str) -> str:
    """Escape special characters for safe use in HTML."""
    return escape(text)

async def flip(update: Update, context: CallbackContext) -> None:
    """Handle the /flip command to simulate a coin flip with IST timestamp."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    result = secrets.choice(["heads", "tails"])

    # Create a safe HTML link for the user
    user_link = f"<a href='tg://user?id={user.id}'>{escape(user.first_name)}</a>"

    # Get current IST time
    ist_timestamp = get_ist_time()

    # Construct the message
    message = f"『 {user_link} 』flipped a coin! 🪙\n\n" if update.message.reply_to_message else f"Flipped a coin! 🪙\n\n"
    message += f"It's <b>{result}</b>!\n🕰️ Timestamp (IST): {ist_timestamp}"

    # Reply to a specific message if applicable
    if update.message.reply_to_message:
        original_msg_id = update.message.reply_to_message.message_id
        await context.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode='HTML',
            reply_to_message_id=original_msg_id
        )
    else:
        # Send the message normally without tagging any user
        await update.message.reply_text(message, parse_mode='HTML')

async def dice(update: Update, context: CallbackContext) -> None:
    """Handle the /dice command to roll a dice."""
    chat_type = update.effective_chat.type
    if chat_type in ['group', 'supergroup']:
        if update.message.reply_to_message:
            user_dice_msg_id = update.message.reply_to_message.message_id
            await context.bot.send_dice(chat_id=update.effective_chat.id, reply_to_message_id=user_dice_msg_id)
        else:
            # If no reply to a message, send dice without tagging anyone
            await update.message.reply_dice()
    else:
        # Send dice normally without reply
        await context.bot.send_dice(chat_id=update.effective_chat.id)

async def football(update: Update, context: CallbackContext) -> None:
    """Handle the /football command to simulate a football action."""
    chat_type = update.effective_chat.type
    if chat_type in ['group', 'supergroup']:
        if update.message.reply_to_message:
            user_msg_id = update.message.reply_to_message.message_id
            await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='⚽', reply_to_message_id=user_msg_id)
        else:
            # If no reply to a message, send football emoji without tagging anyone
            await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='⚽')
    else:
        # Send dice with football emoji normally without reply
        await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='⚽')

async def basketball(update: Update, context: CallbackContext) -> None:
    """Handle the /basketball command to simulate a basketball action."""
    chat_type = update.effective_chat.type
    if chat_type in ['group', 'supergroup']:
        if update.message.reply_to_message:
            user_msg_id = update.message.reply_to_message.message_id
            await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='🏀', reply_to_message_id=user_msg_id)
        else:
            # If no reply to a message, send basketball emoji without tagging anyone
            await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='🏀')
    else:
        # Send dice with basketball emoji normally without reply
        await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='🏀')

async def dart(update: Update, context: CallbackContext) -> None:
    chat_type = update.effective_chat.type
    if chat_type in ['group', 'supergroup']:
        if update.message.reply_to_message:
            user_msg_id = update.message.reply_to_message.message_id
            await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='🎯', reply_to_message_id=user_msg_id)
        else:
            await update.message.reply_text("Please reply to a user's message to play darts for them.")
    else:
        await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='🎯')

        
async def credits_leaderboard(update: Update, context: CallbackContext) -> None:
    try:
        # Fetch top 20 users sorted by credits in descending order
        top_users = list(users_collection.find().sort("credits", -1).limit(20))

        if not top_users:
            await update.message.reply_text("No data available for the leaderboard.")
            return

        # Build the leaderboard message
        leaderboard_message = "⚔️ *Top 20 Credits Leaderboard* ⚔️\n\n"
        for idx, user in enumerate(top_users, start=1):
            name = user.get("first_name", "Unknown User")
            credits = user.get("credits", 0)
            leaderboard_message += f"{idx}. {name} ► {credits} 👾\n"

        # Send the leaderboard message
        await update.message.reply_text(leaderboard_message)
    except Exception as e:
        logger.error(f"Error generating credits leaderboard: {e}")
        await update.message.reply_text("An error occurred while generating the leaderboard.")

