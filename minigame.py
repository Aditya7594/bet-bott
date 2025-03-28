import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, CallbackQuery
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, CallbackContext, filters
from pymongo import MongoClient
import logging
import secrets
from datetime import datetime, timedelta
from html import escape

# MongoDB setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot') 
db = client['telegram_bot']
users_collection = db['users']
minigame_collection = db['minigames']

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

    keyboard = [[InlineKeyboardButton("Flip again", callback_data="flip_again")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message.reply_to_message:
        original_msg_id = update.message.reply_to_message.message_id
        await context.bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode='HTML',
            reply_to_message_id=original_msg_id,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)

    user_id = str(user.id)
    update_user_credits(user_id, 1)

async def handle_flip_again(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    result = secrets.choice(["heads", "tails"])
    new_message = f"It's <b>{result}</b>!"

    keyboard = [[InlineKeyboardButton("Flip again", callback_data="flip_again")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.edit_message_text(text=new_message, parse_mode='HTML', reply_markup=reply_markup)

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
    """Play darts with optional betting."""
    chat_type = update.effective_chat.type
    user_id = str(update.effective_user.id)
    
    # Get bet amount if exists
    bet_amount = context.user_data.get("current_bet", 0)
    
    if chat_type in ['group', 'supergroup']:
        if update.message.reply_to_message:
            user_dice_msg_id = update.message.reply_to_message.message_id
            result = await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='🎯', reply_to_message_id=user_dice_msg_id)
        else:
            result = await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='🎯')
    else:
        result = await context.bot.send_dice(chat_id=update.effective_chat.id, emoji='🎯')

    # Handle betting rewards
    if bet_amount > 0:
        dice_value = result.dice.value
        multiplier = 1.0
        
        # Higher multipliers for better throws
        if dice_value >= 5:
            multiplier = 2.0
        elif dice_value >= 4:
            multiplier = 1.5
            
        winnings = int(bet_amount * multiplier)
        users_collection.update_one(
            {"user_id": user_id},
            {"$inc": {"credits": winnings}}
        )
        
        # Clear the bet amount
        context.user_data.pop("current_bet", None)
        
        # Send result message
        await update.message.reply_text(
            f"🎯 *Dart Result:* {dice_value}\n"
            f"💰 *Winnings:* {winnings} credits",
            parse_mode="Markdown"
        )
    else:
        # Regular credit reward for non-betting games
        users_collection.update_one(
            {"user_id": user_id},
            {"$inc": {"credits": 1}}
        )

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

async def bet(update: Update, context: CallbackContext) -> None:
    """Handle betting in minigames."""
    if not context.args:
        await update.message.reply_text(
            "🎮 *Minigame Betting*\n\n"
            "Usage: `/bet <amount> <game>`\n\n"
            "Available games:\n"
            "• dart - Throw darts\n"
            "• basketball - Play basketball\n"
            "• football - Play football\n"
            "• dice - Roll dice\n"
            "• flip - Flip a coin\n"
            "• roll - Roll custom dice\n\n"
            "Minimum bet: 10,000 credits\n"
            "Daily limit: 10 bets per game",
            parse_mode="Markdown"
        )
        return

    try:
        bet_amount = int(context.args[0])
        game_type = context.args[1].lower()
        
        if bet_amount < 10000:
            await update.message.reply_text("❌ Minimum bet amount is 10,000 credits!")
            return
            
        user_id = str(update.effective_user.id)
        user_data = get_user_by_id(user_id)
        
        if not user_data or user_data["credits"] < bet_amount:
            await update.message.reply_text("❌ You don't have enough credits!")
            return
            
        # Check daily bet limit
        today = datetime.utcnow().date()
        game_data = minigame_collection.find_one({
            "user_id": user_id,
            "game_type": game_type,
            "date": today
        })
        
        if game_data and game_data.get("bets", 0) >= 10:
            await update.message.reply_text(f"❌ You've reached the daily limit of 10 bets for {game_type}!")
            return
            
        # Update bet count
        if game_data:
            minigame_collection.update_one(
                {"user_id": user_id, "game_type": game_type, "date": today},
                {"$inc": {"bets": 1}}
            )
        else:
            minigame_collection.insert_one({
                "user_id": user_id,
                "game_type": game_type,
                "date": today,
                "bets": 1
            })
            
        # Deduct credits
        users_collection.update_one(
            {"user_id": user_id},
            {"$inc": {"credits": -bet_amount}}
        )
        
        # Store bet amount in context for the game
        context.user_data["current_bet"] = bet_amount
        
        # Call appropriate game function
        if game_type == "dart":
            await dart(update, context)
        elif game_type == "basketball":
            await basketball(update, context)
        elif game_type == "football":
            await football(update, context)
        elif game_type == "dice":
            await dice(update, context)
        elif game_type == "flip":
            await flip(update, context)
        elif game_type == "roll":
            if len(context.args) < 3:
                await update.message.reply_text("Usage: /bet <amount> roll <sides>")
                return
            try:
                sides = int(context.args[2])
                if sides < 2:
                    await update.message.reply_text("Dice must have at least 2 sides!")
                    return
                context.user_data["dice_sides"] = sides
                await roll(update, context)
            except ValueError:
                await update.message.reply_text("Please provide a valid number of sides!")
        else:
            await update.message.reply_text("❌ Invalid game type!")
            
    except (ValueError, IndexError):
        await update.message.reply_text("Usage: /bet <amount> <game>")

def get_minigame_handlers():
    """Return all minigame handlers."""
    return [
        CommandHandler("bet", bet),
        CommandHandler("dart", dart),
        CommandHandler("basketball", basketball),
        CommandHandler("football", football),
        CommandHandler("dice", dice),
        CommandHandler("flip", flip),
        CommandHandler("roll", roll),
        CommandHandler("leaderboard", credits_leaderboard),
        CommandHandler("help", help_command),
        CommandHandler("minigame", start_command),
        CallbackQueryHandler(handle_flip_again, pattern="^flip_again$")
    ]
