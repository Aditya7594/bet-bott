import random
from telegram import Update, MessageEntity
from pymongo import MongoClient
import logging
import secrets
from datetime import datetime, timedelta
from html import escape

# MongoDB setup
client = MongoClient('mongo+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
users_collection = db['users']

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Utility functions
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
    ist_time = datetime.utcnow() + timedelta(hours=5, minutes=30)
    return ist_time.strftime('%Y-%m-%d %I:%M:%S %p')

def escape_html(text: str) -> str:
    return escape(text)

# Existing game functions with credit awarding
async def flip(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    chat_id = update.effective_chat.id
    result = secrets.choice(["heads", "tails"])

    user_link = f"<a href='tg://user?id={user.id}'>{escape(user.first_name)}</a>"
    ist_timestamp = get_ist_time()
    message = f"『 {user_link} 』flipped a coin! 🪙\n\n" if update.message.reply_to_message else f"Flipped a coin! 🪙\n\n"
    message += f"It's <b>{result}</b>!\n🕰️ Timestamp (IST): {ist_timestamp}"

    if update.message.reply_to_message:
        original_msg_id = update.message.reply_to_message.message_id
        await context.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode='HTML',
            reply_to_message_id=original_msg_id
        )
    else:
        await update.message.reply_text(message, parse_mode='HTML')

    user_id = str(user.id)
    update_user_credits(user_id, 1)

async def dice(update: Update, context: CallbackContext) -> None:
    chat_type = update.effective_chat.type
    if chat_type in ['group', 'supergroup']:
        if update.message.reply_to_message:
            user_dice_msg_id = update.message.reply_to_message.message_id
            await context.bot.send_dice(chat_id=update.effective_chat.id, reply_to_message_id=user_dice_msg_id)
        else:
            await update.message.reply_dice()
    else:
        await context.bot.send_dice(chat_id=update.effective_chat.id)

    user_id = str(update.effective_user.id)
    update_user_credits(user_id, 1)

async def football(update: Update, context: CallbackContext) -> None:
    chat_type = update.effective_chat.type
    if chat_type in ['group', 'supergroup']:
        if update.message.reply_to_message:
            user_msg_id = update.message.reply_to_message.message_id
            await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='⚽', reply_to_message_id=user_msg_id)
        else:
            await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='⚽')
    else:
        await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='⚽')

    user_id = str(update.effective_user.id)
    update_user_credits(user_id, 1)

async def basketball(update: Update, context: CallbackContext) -> None:
    chat_type = update.effective_chat.type
    if chat_type in ['group', 'supergroup']:
        if update.message.reply_to_message:
            user_msg_id = update.message.reply_to_message.message_id
            await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='🏀', reply_to_message_id=user_msg_id)
        else:
            await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='🏀')
    else:
        await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='🏀')

    user_id = str(update.effective_user.id)
    update_user_credits(user_id, 1)

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

    user_id = str(update.effective_user.id)
    update_user_credits(user_id, 1)

async def credits_leaderboard(update: Update, context: CallbackContext) -> None:
    try:
        top_users = list(users_collection.find().sort("credits", -1).limit(20))
        if not top_users:
            await update.message.reply_text("No data available for the leaderboard.")
            return

        leaderboard_message = "⚔️ *Top 20 Credits Leaderboard* ⚔️\n\n"
        for idx, user in enumerate(top_users, start=1):
            name = user.get("first_name", "Unknown User")
            credits = user.get("credits", 0)
            leaderboard_message += f"{idx}. {name} ► {credits} 👾\n"

        await update.message.reply_text(leaderboard_message)
    except Exception as e:
        logger.error(f"Error generating credits leaderboard: {e}")
        await update.message.reply_text("An error occurred while generating the leaderboard.")

# New functions
async def help_command(update: Update, context: CallbackContext):
    help_message = """
    Available commands:
    /flip: Flip a coin.
    /dice: Roll a die.
    /football: Simulate a football action.
    /basketball: Simulate a basketball action.
    /dart: Simulate a dart throw.
    /credits_leaderboard: Top 20 users by credits.
    /help: Show this help.
    /start: Welcome message.
    /roll <number>: Roll a die with number sides.
    """
    await update.message.reply_text(help_message)

async def start_command(update: Update, context: CallbackContext):
    welcome_message = "Welcome to the Joybot! Use /help to see available commands."
    await update.message.reply_text(welcome_message)

async def roll(update: Update, context: CallbackContext):
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /roll <number of sides>")
        return
    sides = int(context.args[0])
    if sides < 1:
        await update.message.reply_text("Number of sides must be at least 1.")
        return
    result = random.randint(1, sides)
    await update.message.reply_text(f"Rolled a {sides}-sided die. Result: {result}")
    user_id = str(update.effective_user.id)
    update_user_credits(user_id, 1)
