from pymongo import MongoClient
import asyncio
import os
import secrets
import logging
from telegram import Update, ChatPermissions
from telegram.ext import filters, ContextTypes
from functools import wraps
import logging
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, CallbackQuery
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, CallbackContext, filters
from token_1 import token


from genshin_game import pull, bag, reward_primos, add_primos, leaderboard, handle_message, button, reset_bag_data, drop_primos
from minigame import dart, basketball, flip, dice, credits_leaderboard,football
from limbo import limbo, handle_limbo_buttons
from bdice import bdice
from claim import daily, random_claim, claim_credits, send_random_claim
from hilo_game import HiLo, HiLo_click, HiLo_CashOut
from bank import exchange, sell, store, withdraw, bank

# Global variables
OWNER_ID = 5667016949
muted_users = set()
last_interaction_time = {}

# List of owner IDs
OWNER_IDS = [5667016949, 1474610394]

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot') 
db = client['telegram_bot']
users_collection = db['users']
genshin_collection = db['genshin_users']

# MongoDB management functions
def get_user_by_id(user_id):
    return users_collection.find_one({"user_id": user_id})

def save_user(user_data):
    users_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

def get_genshin_user_by_id(user_id):
    return genshin_collection.find_one({"user_id": user_id})

def save_genshin_user(user_data):
    genshin_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

def escape_markdown_v2(text):
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)


def check_started(func):
    @wraps(func)
    async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = str(update.effective_user.id)
        if get_user_by_id(user_id) is None:
            await update.message.reply_text("You need to start the bot first by using /start.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)
    first_name = user.first_name  # Get user's first name

    # Save in general users collection
    existing_user = get_user_by_id(user_id)

    if existing_user is None:
        new_user = {
            "user_id": user_id,
            "first_name": first_name,  # Save the first name
            "join_date": datetime.now().strftime('%m/%d/%y'),
            "credits": 5000,
            "daily": None,
            "win": 0,
            "loss": 0,
            "achievement": [],
            "faction": "None",
            "ban": None,
            "title": "None",
            "primos": 0,
            "bag": {}
        }
        save_user(new_user)
        logger.info(f"User {user_id} started the bot with first name: {first_name}.")

        await update.message.reply_text(
            f"Welcome {first_name}! You've received 5000 credits to start betting. Use /profile to check your details."
        )
    else:
        logger.info(f"User {user_id} ({first_name}) already exists.")
        await update.message.reply_text(
            f"Welcome back, {first_name}! Use /profile to view your details."
        )

    # Save in genshin_users collection
    existing_genshin_user = get_genshin_user_by_id(user_id)

    if existing_genshin_user is None:
        new_genshin_user = {
            "user_id": user_id,
            "first_name": first_name,  # Save the first name in Genshin users
            "primos": 16000,  # Adjust initial primogems as needed
            "bag": {}
        }
        save_genshin_user(new_genshin_user)
        logger.info(f"Genshin user {user_id} initialized with first name: {first_name}.")
    else:
        logger.info(f"Genshin user {user_id} ({first_name}) already exists.")


async def profile(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    # Fetch user data from the database
    user_data = get_user_by_id(user_id)

    if user_data:
        # Get the number of gold, silver, and bronze coins in the user's bag
        gold_coins = user_data['bag'].get('gold', 0)
        silver_coins = user_data['bag'].get('silver', 0)
        bronze_coins = user_data['bag'].get('bronze', 0)

        # Construct the profile message with clear boundaries and formatting
        profile_message = (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 User: {user.first_name}\n"
            f"🆔 ID: {user_data['user_id']}\n"
            f"💰 Credits: {user_data['credits']} 💎\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏆 Wins: {user_data['win']}\n"
            f"💔 Losses: {user_data['loss']}\n"
            f"🎖️ Title: {user_data['title']}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💎 Gold Coins: {gold_coins}\n"
            f"🥈 Silver Coins: {silver_coins}\n"
            f"🥉 Bronze Coins: {bronze_coins}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        # Send profile message with photo if available
        try:
            photos = await context.bot.get_user_profile_photos(user_id)
            if photos.photos:
                # Use the smallest size available (last element in the list)
                smallest_photo = photos.photos[0][-1].file_id
                await update.message.reply_photo(photo=smallest_photo, caption=profile_message)
            else:
                await update.message.reply_text(profile_message)
        except Exception as e:
            logger.error(f"Error fetching user photo: {e}")
            await update.message.reply_text(profile_message)
    else:
        await update.message.reply_text("You need to start the bot first by using /start.")


async def add_credits(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = user.id
    target_user_id = None
    credits_to_add = None

    # Check if the user is the owner
    if user_id not in OWNER_IDS:
        await update.message.reply_text("You don't have permission to use this command.")
        return

    # Parse command arguments
    try:
        target_user_id = int(context.args[0])  # User ID of the target user
        credits_to_add = int(context.args[1])  # Amount of credits to add
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /addcredits <user_id> <credits_amount>")
        return

    # Fetch the user's data from the database
    target_user_data = get_user_by_id(str(target_user_id))
    if target_user_data is None:
        await update.message.reply_text("User not found.")
        return

    # Add the credits to the target user
    new_credits = target_user_data['credits'] + credits_to_add
    target_user_data['credits'] = new_credits
    save_user(target_user_data)

    # Send confirmation message
    await update.message.reply_text(f"Successfully added {credits_to_add} credits to user {target_user_id}. New balance: {new_credits} credits.")

async def check_game_timeout():
    current_time = datetime.now()
    
    for user_id, last_time in last_interaction_time.items():
        if (current_time - last_time).total_seconds() > 180:  # If no interaction for 3 minutes
            game_state = cd.get(user_id)
            if game_state:
                # Refund the credits and remove the game data
                bet = game_state['bet']
                user_data = get_user_by_id(user_id)
                if user_data:
                    user_data['credits'] += bet
                    save_user(user_data)
                
                # Notify user and delete game data
                await context.bot.send_message(user_id, "Your game was canceled due to inactivity. Your credits have been refunded.")
                del cd[user_id]  # Remove the game state

            # Remove from the timeout tracker
            del last_interaction_time[user_id]

async def timeout_task():
    while True:
        await asyncio.sleep(60)  # Wait for 1 minute
        await check_game_timeout()


async def reset(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id

    # Check if the user is the owner
    if user_id not in OWNER_IDS:
        await update.message.reply_text("You don't have permission to use this command.")
        return

    # Create inline keyboard for confirmation
    keyboard = [
        [
            InlineKeyboardButton("Yes", callback_data="reset_yes"),
            InlineKeyboardButton("No", callback_data="reset_no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Are you sure you want to reset all user data? This will wipe all progress!", reply_markup=reply_markup)

# Handle the callback data when the owner confirms reset
async def reset_confirmation(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id

    # Check if the user is the owner
    if user_id not in OWNER_IDS:
        await query.answer("You don't have permission to do this.", show_alert=True)
        return

    # Check the callback data (Yes or No)
    if query.data == "reset_yes":
        # Reset all users' data and give them 5000 credits
        users_collection.update_many({}, {"$set": {
            "credits": 5000,  # Set credits to 5000 after reset
            "daily": None,
            "win": 0,
            "loss": 0,
            "achievement": [],
            "faction": "None",
            "ban": None,
            "title": "None",
            "primos": 0,
            "bag": {}
        }})
        
        # Inform the owner that the reset was successful
        await query.answer("All user data has been reset to default values, and all users have received 5000 credits.", show_alert=True)

    elif query.data == "reset_no":
        # Inform the owner that the reset was canceled
        await query.answer("User data reset was canceled.", show_alert=True)

    # Delete the inline keyboard after answering
    await query.edit_message_reply_markup(reply_markup=None)

def main() -> None:
    # Create the Application and pass the bot token
    application = Application.builder().token(token).build()

    # Add command handlers with check_started decorator
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("profile", check_started(profile)))
    application.add_handler(CommandHandler("flip", check_started(flip)))
    application.add_handler(CommandHandler("dart", check_started(dart)))
    application.add_handler(CommandHandler("basketball", check_started(basketball)))
    application.add_handler(CommandHandler("football", check_started(football)))
    application.add_handler(CommandHandler("dice", check_started(dice)))
    application.add_handler(CommandHandler("pull", check_started(pull)))
    application.add_handler(CommandHandler("bag", check_started(bag)))
    application.add_handler(CommandHandler('add_primos', check_started(add_primos)))
    application.add_handler(CommandHandler("Primos_leaderboard", check_started(leaderboard)))
    application.add_handler(CommandHandler('drop_primos', check_started(drop_primos)))
    application.add_handler(CommandHandler("addcredits", check_started(add_credits)))
    application.add_handler(CommandHandler("reset_bag_data", check_started(reset_bag_data)))
    application.add_handler(CommandHandler("leaderboard", check_started(credits_leaderboard)))
    application.add_handler(CommandHandler("hilo", check_started(HiLo)))
    application.add_handler(CallbackQueryHandler(HiLo_click, pattern='^Hilo_'))
    application.add_handler(CallbackQueryHandler(HiLo_CashOut, pattern='^HiLoCashOut$'))
    application.add_handler(CommandHandler("exchange", check_started(exchange)))  # For exchanging credits to coins
    application.add_handler(CommandHandler("sell", check_started(sell)))  # For exchanging coins back to credits
    application.add_handler(CommandHandler("store", check_started(store)))  # For storing credits in the bank
    application.add_handler(CommandHandler("withdraw", check_started(withdraw))) 
    application.add_handler(CommandHandler("bank", bank))

    # Limbo game handlers
    # Ensure callback data for Limbo starts with "limbo_"
    application.add_handler(CommandHandler("limbo", limbo))
    application.add_handler(CallbackQueryHandler(handle_limbo_buttons))
    # Dice-related command
    application.add_handler(CommandHandler("bdice", check_started(bdice)))

    # Daily-related commands
    application.add_handler(CommandHandler("daily", check_started(daily)))
    application.add_handler(CallbackQueryHandler(claim_credits, pattern="^claim_"))
    application.add_handler(CallbackQueryHandler(random_claim, pattern="^random_claim$"))

    # Reset functionality (ensure callback data pattern is distinct)
    application.add_handler(CommandHandler("reset", reset))  # Command to initiate reset
    application.add_handler(CallbackQueryHandler(reset_confirmation, pattern="^reset_"))  # Pattern adjusted for reset callbacks

    # Message handlers for rewards and other messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reward_primos))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run the timeout task every minute (this checks for timeout game interactions)
    application.job_queue.run_once(timeout_task, 0)

    # Add callback query handler for inline buttons (ensure inline button callbacks are unique)
    application.add_handler(CallbackQueryHandler(button))

    # Start polling for updates
    application.run_polling()

if __name__ == '__main__':
    main()
