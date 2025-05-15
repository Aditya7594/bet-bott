import random
import logging
from datetime import datetime, timezone
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext
from pymongo import MongoClient, DESCENDING

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# MongoDB setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority')
db = client['telegram_bot']
user_collection = db['users']

def get_user_by_id(user_id):
    return user_collection.find_one({"user_id": str(user_id)})

def save_user(user_data):
    user_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

def get_ist_time():
    """Get current time in IST with proper timezone handling."""
    utc_now = datetime.now(timezone.utc)
    ist = pytz.timezone('Asia/Kolkata')
    ist_time = utc_now.astimezone(ist)
    return ist_time.strftime("%H:%M:%S IST")

async def bet(update: Update, context: CallbackContext) -> None:
    """Handle the /bet command for betting credits."""
    user = update.effective_user
    user_id = str(user.id)
    
    # Check if amount is provided
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "Usage: /bet <amount>\n"
            "Example: /bet 100"
        )
        return
    
    amount = int(context.args[0])
    if amount <= 0:
        await update.message.reply_text("Please bet a positive amount.")
        return
    
    # Get user data
    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to start the bot first using /start.")
        return
    
    # Check if user has enough credits
    if user_data.get('credits', 0) < amount:
        await update.message.reply_text(f"You don't have enough credits. Your balance: {user_data.get('credits', 0)}")
        return
    
    # Generate random number between 1 and 100
    result = random.randint(1, 100)
    
    # 50% chance to win
    if result <= 50:
        # Win
        winnings = amount * 2
        user_data['credits'] += amount
        user_data['win'] = user_data.get('win', 0) + 1
        message = f"🎉 You won {winnings} credits!"
    else:
        # Lose
        user_data['credits'] -= amount
        user_data['loss'] = user_data.get('loss', 0) + 1
        message = f"😢 You lost {amount} credits!"
    
    # Save updated user data
    save_user(user_data)
    
    # Send result
    await update.message.reply_text(
        f"{message}\n"
        f"Your new balance: {user_data['credits']} credits"
    )

async def flip(update: Update, context: CallbackContext) -> None:
    """Handle the /flip command for betting on coin flip."""
    user = update.effective_user
    user_id = str(user.id)
    
    # Check if choice and amount are provided
    if not context.args or len(context.args) != 2:
        await update.message.reply_text(
            "Usage: /flip <h/t> <amount>\n"
            "Example: /flip h 100"
        )
        return
    
    choice = context.args[0].lower()
    if choice not in ['h', 't']:
        await update.message.reply_text("Please choose 'h' for heads or 't' for tails.")
        return
    
    if not context.args[1].isdigit():
        await update.message.reply_text("Please provide a valid amount.")
        return
    
    amount = int(context.args[1])
    if amount <= 0:
        await update.message.reply_text("Please bet a positive amount.")
        return
    
    # Get user data
    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to start the bot first using /start.")
        return
    
    # Check if user has enough credits
    if user_data.get('credits', 0) < amount:
        await update.message.reply_text(f"You don't have enough credits. Your balance: {user_data.get('credits', 0)}")
        return
    
    # Get current IST time
    current_time = get_ist_time()
    
    # Flip coin
    result = random.choice(['h', 't'])
    result_text = 'Heads' if result == 'h' else 'Tails'
    
    # Check if user won
    if choice == result:
        # Win
        winnings = amount * 2
        user_data['credits'] += amount
        user_data['win'] = user_data.get('win', 0) + 1
        message = f"🎉 You won {winnings} credits!"
    else:
        # Lose
        user_data['credits'] -= amount
        user_data['loss'] = user_data.get('loss', 0) + 1
        message = f"😢 You lost {amount} credits!"
    
    # Save updated user data
    save_user(user_data)
    
    # Send result with HTML formatting
    await update.message.reply_text(
        f"🪙 <b>Coin Flip Result</b>\n\n"
        f"👤 User: {user.first_name}\n"
        f"⏰ Time: {current_time}\n"
        f"🎲 Result: {result_text}\n"
        f"💰 {message}\n"
        f"💳 New Balance: {user_data['credits']} credits",
        parse_mode='HTML'
    )

async def toss(update: Update, context: CallbackContext) -> None:
    """Handle the /toss command for simple coin flip."""
    user = update.effective_user
    
    # Get current IST time
    current_time = get_ist_time()
    
    # Flip coin
    result = random.choice(['Heads', 'Tails'])
    
    # Send result
    await update.message.reply_text(
        f"{user.first_name} flipped a coin!\n\n"
        f"It's {result}! {current_time}"
    )

async def dice(update: Update, context: CallbackContext) -> None:
    """Handle the /dice command for rolling dice."""
    user = update.effective_user
    user_id = str(user.id)
    
    # Check if amount is provided
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "Usage: /dice <amount>\n"
            "Example: /dice 100"
        )
        return
    
    amount = int(context.args[0])
    if amount <= 0:
        await update.message.reply_text("Please bet a positive amount.")
        return
    
    # Get user data
    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to start the bot first using /start.")
        return
    
    # Check if user has enough credits
    if user_data.get('credits', 0) < amount:
        await update.message.reply_text(f"You don't have enough credits. Your balance: {user_data.get('credits', 0)}")
        return
    
    # Roll dice (1-6)
    result = random.randint(1, 6)
    
    # Win if roll is 4 or higher (50% chance)
    if result >= 4:
        # Win
        winnings = amount * 2
        user_data['credits'] += amount
        user_data['win'] = user_data.get('win', 0) + 1
        message = f"🎉 You won {winnings} credits!"
    else:
        # Lose
        user_data['credits'] -= amount
        user_data['loss'] = user_data.get('loss', 0) + 1
        message = f"😢 You lost {amount} credits!"
    
    # Save updated user data
    save_user(user_data)
    
    # Send result
    await update.message.reply_text(
        f"🎲 <b>Dice Roll</b>\n\n"
        f"👤 User: {user.first_name}\n"
        f"🎯 Roll: {result}\n"
        f"💰 {message}\n"
        f"💳 New Balance: {user_data['credits']} credits",
        parse_mode='HTML'
    )

async def cleaderboard(update: Update, context: CallbackContext) -> None:
    """Show the top 25 users by credits."""
    # Get top 25 users by credits
    top_users = user_collection.find().sort("credits", DESCENDING).limit(25)
    
    # Create leaderboard message
    leaderboard = "🏆 <b>Credits Leaderboard</b>\n\n"
    
    for i, user in enumerate(top_users, 1):
        name = user.get('first_name', 'Unknown')
        credits = user.get('credits', 0)
        leaderboard += f"{i}. {name}: {credits:,} credits\n"
    
    await update.message.reply_text(leaderboard, parse_mode='HTML')

def get_gambling_handlers():
    """Return all gambling-related command handlers."""
    return [
        CommandHandler("bet", bet),
        CommandHandler("flip", flip),
        CommandHandler("toss", toss),
        CommandHandler("dice", dice),
        CommandHandler("cleaderboard", cleaderboard)
    ] 