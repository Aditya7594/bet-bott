from flask import Flask
from threading import Thread
import asyncio
from pymongo import MongoClient
import os
import secrets
import requests
import logging
from datetime import datetime, timedelta, timezone, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, 
    CallbackContext, filters, ChatMemberHandler, ThrottlingHandler
)
from telegram.constants import ChatType
from token_1 import token
from functools import lru_cache, wraps
from collections import defaultdict
import time as time_module

# Reduce logging level to WARNING
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.WARNING
)
logger = logging.getLogger(__name__)

# Command throttling settings
THROTTLE_RATE = 1.0  # seconds between commands
THROTTLE_BURST = 3   # number of commands allowed in burst

# Module enable/disable settings
ENABLED_MODULES = {
    'wordle': True,
    'wordhunt': True,
    'cricket': True,
    'multiplayer': True,
    'mines': True,
    'limbo': True,
    'genshin': True
}

# Command throttling decorator
def throttle_command(rate=THROTTLE_RATE, burst=THROTTLE_BURST):
    def decorator(func):
        last_called = {}
        tokens = defaultdict(lambda: burst)
        last_update = {}

        @wraps(func)
        async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
            user_id = update.effective_user.id
            current_time = time_module.time()

            # Initialize user's last called time
            if user_id not in last_called:
                last_called[user_id] = 0
                tokens[user_id] = burst

            # Check if enough time has passed to add a token
            time_passed = current_time - last_called[user_id]
            if time_passed >= rate:
                new_tokens = int(time_passed / rate)
                tokens[user_id] = min(burst, tokens[user_id] + new_tokens)
                last_called[user_id] = current_time

            # Check if user has tokens available
            if tokens[user_id] <= 0:
                await update.message.reply_text(
                    f"Please wait {rate:.1f} seconds before using this command again."
                )
                return

            # Use a token and execute the command
            tokens[user_id] -= 1
            return await func(update, context, *args, **kwargs)

        return wrapper
    return decorator

# Update filter function
def should_process_update(update: Update) -> bool:
    """Filter updates to reduce processing load."""
    if not update or not update.effective_user:
        return False
    
    # Skip updates from bots
    if update.effective_user.is_bot:
        return False
    
    # Skip non-message updates
    if not update.message and not update.callback_query:
        return False
    
    # Skip command messages if module is disabled
    if update.message and update.message.text and update.message.text.startswith('/'):
        command = update.message.text.split()[0][1:].lower()
        if command in ENABLED_MODULES and not ENABLED_MODULES[command]:
            return False
    
    return True

# MongoDB setup with connection pooling and reduced operations
try:
    client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot',
                        serverSelectionTimeoutMS=5000,
                        maxPoolSize=50,
                        minPoolSize=10,
                        maxIdleTimeMS=30000)
    db = client['telegram_bot']
    user_collection = db['users']
    genshin_collection = db['genshin_users']
    groups_collection = db['groups']
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    user_collection = None
    genshin_collection = None
    groups_collection = None

# Cache for user data with TTL
@lru_cache(maxsize=1000)
def get_user_by_id_cached(user_id):
    """Cached version of get_user_by_id with TTL."""
    if not user_collection:
        return None
    return user_collection.find_one({"user_id": str(user_id)})

# Cache for genshin user data with TTL
@lru_cache(maxsize=1000)
def get_genshin_user_by_id_cached(user_id):
    """Cached version of get_genshin_user_by_id with TTL."""
    if not genshin_collection:
        return None
    return genshin_collection.find_one({"user_id": str(user_id)})

# Cache for group settings
@lru_cache(maxsize=100)
def get_group_settings_cached(chat_id):
    """Cached version of get_group_settings to reduce database operations."""
    return {"artifact_enabled": True, "artifact_threshold": 50}

# Optimize message handling
MESSAGE_COOLDOWN = 5  # seconds
MAX_DAILY_PRIMOS = 100
PRIMO_REWARD_AMOUNT = 5

# Use defaultdict for better performance
message_counts = defaultdict(lambda: {
    "count": 0,
    "last_message": datetime.now(timezone.utc),
    "participants": set(),
    "message_types": {}
})

# Cache for user names
@lru_cache(maxsize=1000)
def get_user_name_cached(user_id):
    """Cached version of get_user_name to reduce database operations."""
    user = get_user_by_id_cached(user_id)
    return user.get('first_name', 'Unknown') if user else 'Unknown'

# Optimize message handling with async
async def handle_group_message(update: Update, context: CallbackContext):
    """Async message handler with filtering and throttling."""
    if not should_process_update(update):
        return

    user = update.effective_user
    user_id = str(user.id)
    chat_id = str(update.effective_chat.id)
    
    # Skip if message is from a bot or is a command
    if user.is_bot or (update.message.text and update.message.text.startswith('/')):
        return
    
    # Determine message type efficiently
    message_type = next((attr for attr in ['sticker', 'photo', 'video', 'document', 
                                         'audio', 'voice', 'animation', 'video_note',
                                         'location', 'contact', 'poll', 'dice'] 
                        if getattr(update.message, attr, None)), 'text')
    
    # Handle Genshin system with optimized checks
    user_data = get_genshin_user_by_id_cached(user_id)
    now = datetime.now(timezone.utc)

    if not user_data:
        user_data = {
            "user_id": user_id,
            "primos": 0,
            "bag": {},
            "message_primo": {
                "count": 0,
                "earned": 0,
                "last_reset": now,
                "last_message": now,
                "message_types": {}
            }
        }
        if genshin_collection:
            await asyncio.to_thread(
                genshin_collection.insert_one,
                user_data
            )
    else:
        # Optimize message primo handling
        message_primo = user_data.get("message_primo", {})
        last_message = message_primo.get("last_message", now)
        last_reset = message_primo.get("last_reset", now)
        
        # Convert to timezone-aware if needed
        if isinstance(last_message, datetime) and last_message.tzinfo is None:
            last_message = last_message.replace(tzinfo=timezone.utc)
        if isinstance(last_reset, datetime) and last_reset.tzinfo is None:
            last_reset = last_reset.replace(tzinfo=timezone.utc)
        
        # Check cooldown and limits
        message_cooldown = (now - last_message).total_seconds()
        if message_cooldown >= MESSAGE_COOLDOWN:
            current_earned = message_primo.get("earned", 0)
            if current_earned < MAX_DAILY_PRIMOS:
                # Update primos efficiently
                user_data["primos"] = user_data.get("primos", 0) + PRIMO_REWARD_AMOUNT
                message_primo.update({
                    "count": message_primo.get("count", 0) + 1,
                    "earned": current_earned + PRIMO_REWARD_AMOUNT,
                    "last_message": now
                })
                
                # Update message types efficiently
                message_types = message_primo.get("message_types", {})
                message_types[message_type] = message_types.get(message_type, 0) + 1
                message_primo["message_types"] = message_types
                
                if genshin_collection:
                    await asyncio.to_thread(
                        genshin_collection.update_one,
                        {"user_id": user_id},
                        {"$set": {
                            "primos": user_data["primos"],
                            "message_primo": message_primo
                        }}
                    )

    # Handle artifact system efficiently
    settings = get_group_settings_cached(chat_id)
    if settings.get("artifact_enabled", True):
        chat_data = message_counts[chat_id]
        if (now - chat_data["last_message"]).total_seconds() >= MESSAGE_COOLDOWN:
            chat_data["count"] += 1
            chat_data["last_message"] = now
            chat_data["participants"].add(user_id)
            chat_data["message_types"][message_type] = chat_data["message_types"].get(message_type, 0) + 1
            
            # Clean up old participants efficiently
            chat_data["participants"] = {
                pid for pid in chat_data["participants"]
                if (now - user_data.get("message_primo", {}).get("last_message", now)).total_seconds() < 3600
            }
            
            if chat_data["count"] >= settings.get("artifact_threshold", 50):
                chat_data["count"] = 0
                await send_artifact_reward(chat_id, context)

    # Handle leveling system
    await handle_message(update, context)

# Create Flask app
app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'Shadow'

# Function to run Flask
def run_flask():
    app.run(host="0.0.0.0", port=8000)

# Start Flask server in background thread
flask_thread = Thread(target=run_flask)
flask_thread.start()

import asyncio
from pymongo import MongoClient
import os
import secrets
import requests
import logging
from datetime import datetime, timedelta, timezone, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, CallbackContext, filters, ChatMemberHandler
from telegram.constants import ChatType
from token_1 import token

# Constants and settings
OWNER_ID = 5667016949
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority')
db = client['telegram_bot']
user_collection = db['users']
genshin_collection = db['genshin_users']
groups_collection = db['groups']  # Collection for tracking groups

# Global variable for tracking last interaction time
last_interaction_time = {}

# Global variable for tracking message counts for artifact rewards
message_counts = {}

# Constants
PRIMO_REWARD_AMOUNT = 5
MESSAGE_COOLDOWN_SECONDS = 5
RESET_INTERVAL_SECONDS = 3600  # 1 hour
MAX_DAILY_PRIMOS = 100

def get_group_settings(chat_id):
    # TODO: Replace with actual group settings retrieval
    return {"artifact_enabled": True, "artifact_threshold": 50}

def get_user_by_id(user_id):
    return user_collection.find_one({"user_id": user_id})

def save_user(user_data):
    user_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

def get_genshin_user_by_id(user_id):
    return genshin_collection.find_one({"user_id": user_id})

def save_genshin_user(user_data):
    genshin_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

def save_group(group_data):
    groups_collection.update_one({"group_id": group_data["group_id"]}, {"$set": group_data}, upsert=True)

def escape_markdown_v2(text):
    escape_chars = r'\_*[]()~`>#+-=|{}.! '
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)

def generate_referral_link(user_id):
    return f"https://t.me/YourBotUsername?start=ref{user_id}"

async def start(update: Update, context: CallbackContext) -> None:
    """Handle the /start command."""
    user = update.effective_user
    user_id = str(user.id)
    
    # Check if user exists in database
    user_data = user_collection.find_one({"user_id": user_id})
    
    # Process referral if present in start command
    referrer_id = None
    if context.args and len(context.args) > 0 and context.args[0].startswith("ref"):
        try:
            referrer_id = context.args[0][3:]  # Remove "ref" prefix
            if referrer_id == user_id:  # Prevent self-referral
                referrer_id = None
        except:
            referrer_id = None
    
    if not user_data:
        # Create new user
        user_collection.insert_one({
            "user_id": user_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "created_at": datetime.utcnow(),
            "last_active": datetime.utcnow(),
            "credits": 5000,  # Default credits for new users
            "daily": None,
            "win": 0,
            "loss": 0,
            "achievement": [],
            "faction": "None",
            "ban": None,
            "title": "None",
            "bank": 0,
            "cards": [],
            "referrals": 0
        })
        
        # Process referral reward if applicable
        if referrer_id:
            referrer_data = get_user_by_id(referrer_id)
            if referrer_data:
                # Update referrer's referral count and add credits
                referrer_data["referrals"] = referrer_data.get("referrals", 0) + 1
                referrer_data["credits"] = referrer_data.get("credits", 0) + 1000
                
                # Add primogems to referrer
                genshin_referrer = get_genshin_user_by_id(referrer_id)
                if genshin_referrer:
                    genshin_referrer["primos"] = genshin_referrer.get("primos", 0) + 1000
                    save_genshin_user(genshin_referrer)
                else:
                    # Create genshin user if not exists
                    genshin_referrer = {
                        "user_id": referrer_id,
                        "primos": 1000,
                        "bag": {},
                        "last_primo_reward": None
                    }
                    save_genshin_user(genshin_referrer)
                
                save_user(referrer_data)
                
                # Notify referrer
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=f"🎉 {user.first_name} joined using your referral link! You received 1000 credits and 1000 Primogems!"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify referrer: {e}")
                
                # Add primogems to new user
                genshin_user = {
                    "user_id": user_id,
                    "primos": 1000,
                    "bag": {},
                    "last_primo_reward": None
                }
                save_genshin_user(genshin_user)
                
                await update.message.reply_text(
                    f"👋 Welcome {user.first_name}! I'm your cricket game bot.\n\n"
                    f"You received 5000 credits to start and 1000 Primogems for joining via a referral!\n\n"
                    f"Use /chatcricket in a group to start a new game!"
                )
            else:
                await update.message.reply_text(
                    f"👋 Welcome {user.first_name}! I'm your cricket game bot.\n\n"
                    f"Use /chatcricket in a group to start a new game!"
                )
        else:
            await update.message.reply_text(
                f"👋 Welcome {user.first_name}! I'm your cricket game bot.\n\n"
                f"Use /chatcricket in a group to start a new game!"
            )
    else:
        # Update last active
        user_collection.update_one(
            {"user_id": user_id},
            {"$set": {"last_active": datetime.utcnow()}}
        )
        await update.message.reply_text(
            f"👋 Welcome back {user.first_name}! Use /chatcricket in a group to start a new game!"
        )
    
    # If the command was used in a group, add the group to the database
    if update.effective_chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        group_id = str(update.effective_chat.id)
        group_data = {
            "group_id": group_id,
            "title": update.effective_chat.title,
            "added_at": datetime.utcnow(),
            "last_active": datetime.utcnow()
        }
        save_group(group_data)

async def error_handler(update: Update, context: CallbackContext) -> None:
    """Log Errors caused by Updates."""
    logger.warning(f'Update "{update}" caused error "{context.error}"')

async def reffer(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    # Fetch user data from the database to check how many users they've referred
    user_data = get_user_by_id(user_id)

    if user_data:
        referral_count = user_data.get('referrals', 0)
    else:
        referral_count = 0

    # Generate a referral link
    bot_username = (await context.bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start=ref{user_id}"

    # Send the referral link and the referral count to the user
    await update.message.reply_text(
        f"🔗 Share this referral link with your friends:\n\n"
        f"{referral_link}\n\n"
        f"You have referred {referral_count} users.\n\n"
        "When they join and start the bot using your link, both of you will receive 1000 credits and 1000 Primogems!"
    )

async def profile(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)
    user_data = get_user_by_id(user_id)

    if not user_data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return  # Exit early if user is not registered

    # Get user's credits and other profile data
    credits = user_data.get('credits', 0)
    bank_balance = user_data.get('bank', 0)
    wins = user_data.get('win', 0)
    losses = user_data.get('loss', 0)
    referrals = user_data.get('referrals', 0)
    
    # Get Genshin data if available
    genshin_data = get_genshin_user_by_id(user_id)
    primos = genshin_data.get('primos', 0) if genshin_data else 0

    # Create profile message with better formatting
    profile_message = (
        f"👤 <b>Profile</b>\n\n"
        f"🆔 User ID: {user_id}\n"
        f"👤 Name: {user.first_name}\n"
        f"💰 Credits: {credits:,}\n"
        f"🏦 Bank: {bank_balance:,}\n"
        f"💎 Primogems: {primos:,}\n"
        f"🏆 Wins: {wins:,}\n"
        f"❌ Losses: {losses:,}\n"
        f"👥 Referrals: {referrals:,}\n"
    )

    await update.message.reply_text(profile_message, parse_mode='HTML')

async def add_credits(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = user.id
    target_user_id = None
    credits_to_add = None

    # Check if the user is the owner
    if user_id != OWNER_ID:
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
    new_credits = target_user_data.get('credits', 0) + credits_to_add  # Handle missing 'credits' key
    target_user_data['credits'] = new_credits
    save_user(target_user_data)

    # Send confirmation message
    await update.message.reply_text(f"Successfully added {credits_to_add} credits to user {target_user_id}. New balance: {new_credits} credits.")

async def reset(update: Update, context: CallbackContext) -> None:
    """Handle the reset command with direct execution or confirmation."""
    user_id = update.effective_user.id

    # Check if the user is the owner
    if user_id != OWNER_ID:
        await update.message.reply_text("You don't have permission to use this command.")
        return
    
    # Check if force parameter is provided
    force_reset = False
    if context.args and context.args[0].lower() == "force":
        force_reset = True
    
    if force_reset:
        # Reset all users' data and set specified values to defaults
        user_collection.update_many({}, {"$set": {
            "credits": 5000,  # Set credits to 5000 after reset
            "daily": None,
            "win": 0,
            "loss": 0,
            "achievement": [],
            "faction": "None",
            "ban": None,
            "title": "None",
            "primos": 0,
            "bag": {},
            "bank": 0,  # Reset bank balance to 0
            "cards": [],  # Reset cards to 0
        }})
        
        # Inform the owner that the reset was successful
        await update.message.reply_text("✅ All user data has been reset to default values, and all users have received 5000 credits.")
    else:
        # Create inline keyboard for confirmation
        keyboard = [
            [
                InlineKeyboardButton("Yes", callback_data="reset_yes"),
                InlineKeyboardButton("No", callback_data="reset_no"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "⚠️ Are you sure you want to reset all user data? This will wipe all progress!\n\n"
            "All users will receive 5000 credits, and all other progress will be reset.",
            reply_markup=reply_markup
        )

async def reset_confirmation(update: Update, context: CallbackContext) -> None:
    """Handle reset confirmation callback."""
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    # Check if the user is the owner
    if user_id != OWNER_ID:
        await query.edit_message_text("You don't have permission to do this.")
        return

    # Check the callback data (Yes or No)
    if query.data == "reset_yes":
        # Reset all users' data and set specified values to defaults
        user_collection.update_many({}, {"$set": {
            "credits": 5000,  # Set credits to 5000 after reset
            "daily": None,
            "win": 0,
            "loss": 0,
            "achievement": [],
            "faction": "None",
            "ban": None,
            "title": "None",
            "primos": 0,
            "bag": {},
            "bank": 0,  # Reset bank balance to 0
            "cards": [],  # Reset cards to 0
        }})
        
        # Inform the owner that the reset was successful
        await query.edit_message_text("✅ All user data has been reset to default values, and all users have received 5000 credits.")

    elif query.data == "reset_no":
        # Inform the owner that the reset was canceled
        await query.edit_message_text("❌ User data reset was canceled.")

async def reach(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    # Check if the user is the owner
    if user_id != OWNER_ID:
        await update.message.reply_text("🔒 You don't have permission to use this command.")
        return

    try:
        # Fetch total users
        total_users = user_collection.count_documents({})

        # Fetch total Genshin users
        total_genshin_users = genshin_collection.count_documents({})

        # Fetch total credits in the game
        total_credits_result = user_collection.aggregate([
            {"$group": {"_id": None, "total_credits": {"$sum": "$credits"}}}
        ])
        total_credits_value = next(total_credits_result, {}).get("total_credits", 0)
        
        # Fetch total bank deposits
        total_bank_result = user_collection.aggregate([
            {"$group": {"_id": None, "total_bank": {"$sum": "$bank"}}}
        ])
        total_bank_value = next(total_bank_result, {}).get("total_bank", 0)

        # Fetch total groups the bot is in
        total_groups = groups_collection.count_documents({})

        # Get active users in the last 24 hours
        yesterday = datetime.utcnow() - timedelta(days=1)
        active_users = user_collection.count_documents({"last_active": {"$gte": yesterday}})

        # Construct the stats message
        stats_message = (
            "<b>🤖 Bot Statistics:</b>\n\n"
            f"👥 Total Users: {total_users}\n"
            f"👤 Active Users (24h): {active_users}\n"
            f"🌌 Total Genshin Users: {total_genshin_users}\n"
            f"💰 Total Credits in Game: {total_credits_value:,}\n"
            f"🏦 Total Bank Deposits: {total_bank_value:,}\n"
            f"📊 Total Economy Value: {(total_credits_value + total_bank_value):,}\n"
            f"🏢 Total Groups: {total_groups}\n"
        )

        # Get top 5 richest users
        richest_users = user_collection.find().sort([("credits", -1)]).limit(5)
        
        if richest_users:
            stats_message += "\n<b>💎 Top 5 Richest Users:</b>\n"
            position = 1
            for user in richest_users:
                user_name = user.get('first_name', 'Unknown')
                user_credits = user.get('credits', 0)
                stats_message += f"{position}. {user_name}: {user_credits:,} credits\n"
                position += 1

        await update.message.reply_text(stats_message, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error in /reach command: {e}")
        await update.message.reply_text("An error occurred while fetching bot stats. Please try again later.")

async def broadcast(update: Update, context: CallbackContext) -> None:
    # Check if the user is the owner
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("🔒 You don't have permission to use this command.")
        return

    # Check if a message is provided
    if not context.args:
        await update.message.reply_text(
            "❗ Usage: /broadcast <message>\n\n"
            "To send to specific audience:\n"
            "/broadcast -u <message> (Users only)\n"
            "/broadcast -g <message> (Groups only)\n"
            "/broadcast -a <message> (All - default)"
        )
        return

    # Determine the target audience
    target = "all"  # Default: broadcast to all
    message_start = 0
    
    if context.args[0] == "-u":
        target = "users"
        message_start = 1
    elif context.args[0] == "-g":
        target = "groups"
        message_start = 1
    elif context.args[0] == "-a":
        target = "all"
        message_start = 1
    
    # Get the original message text with line breaks preserved
    original_text = update.message.text
    # Remove the command part (/broadcast or /broadcast -u etc)
    command_end = original_text.find(" ", message_start)
    if command_end == -1:
        await update.message.reply_text("❗ Please provide a message to broadcast.")
        return
    broadcast_message = original_text[command_end + 1:].strip()
    
    if not broadcast_message:
        await update.message.reply_text("❗ Please provide a message to broadcast.")
        return
    
    # Send progress message
    progress_msg = await update.message.reply_text("🔄 Broadcasting in progress...")
    
    # Counters for tracking
    successful_users = 0
    failed_users = 0
    successful_groups = 0
    failed_groups = 0
    
    try:
        # Send to users if requested
        if target in ["users", "all"]:
            # Fetch all users from the database
            users = list(user_collection.find({}, {"user_id": 1}))
            total_users = len(users)
            
            if total_users == 0:
                await progress_msg.edit_text("❌ No users found in the database.")
                return
            
            current_count = 0
            for user in users:
                try:
                    user_id = int(user.get("user_id"))  # Convert to integer
                    # Add a small delay to avoid hitting rate limits
                    await asyncio.sleep(0.05)
                    await context.bot.send_message(
                        chat_id=user_id, 
                        text=f"📢 <b>Broadcast Message</b>\n\n{broadcast_message}",
                        parse_mode="HTML"
                    )
                    successful_users += 1
                except Exception as e:
                    logger.error(f"Failed to send broadcast to user {user.get('user_id')}: {e}")
                    failed_users += 1
                
                current_count += 1
                if current_count % 10 == 0:  # Update progress more frequently
                    try:
                        await progress_msg.edit_text(
                            f"🔄 Broadcasting to users...\n"
                            f"Progress: {current_count}/{total_users}\n"
                            f"✅ Success: {successful_users}\n"
                            f"❌ Failed: {failed_users}"
                        )
                    except Exception as e:
                        logger.error(f"Failed to update progress message: {e}")
        
        # Send to groups if requested
        if target in ["groups", "all"]:
            # Fetch all groups from the database
            groups = list(groups_collection.find({}, {"group_id": 1}))
            total_groups = len(groups)
            
            if total_groups == 0:
                await progress_msg.edit_text("❌ No groups found in the database.")
                return
            
            current_count = 0
            for group in groups:
                try:
                    group_id = int(group.get("group_id"))  # Convert to integer
                    # Add a small delay to avoid hitting rate limits
                    await asyncio.sleep(0.05)
                    await context.bot.send_message(
                        chat_id=group_id, 
                        text=f"📢 <b>Broadcast Message</b>\n\n{broadcast_message}",
                        parse_mode="HTML"
                    )
                    successful_groups += 1
                except Exception as e:
                    logger.error(f"Failed to send broadcast to group {group.get('group_id')}: {e}")
                    failed_groups += 1
                
                current_count += 1
                if current_count % 5 == 0:  # Update progress more frequently
                    try:
                        await progress_msg.edit_text(
                            f"🔄 Broadcasting to groups...\n"
                            f"Progress: {current_count}/{total_groups}\n"
                            f"✅ Success: {successful_groups}\n"
                            f"❌ Failed: {failed_groups}"
                        )
                    except Exception as e:
                        logger.error(f"Failed to update progress message: {e}")
        
        # Send final report
        report_message = (
            "📊 <b>Broadcast Report</b>\n\n"
            f"✅ Successfully sent to {successful_users} users and {successful_groups} groups.\n"
            f"❌ Failed to send to {failed_users} users and {failed_groups} groups.\n\n"
            f"Total recipients: {successful_users + successful_groups}\n"
            f"Total failures: {failed_users + failed_groups}"
        )
        
        await progress_msg.edit_text(report_message, parse_mode="HTML")
        
    except Exception as e:
        error_message = f"❌ An error occurred during broadcasting: {str(e)}"
        logger.error(error_message)
        await progress_msg.edit_text(error_message)

async def give(update: Update, context: CallbackContext) -> None:
    giver = update.effective_user
    giver_id = str(giver.id)
    message = update.message

    # Check if the command is a reply or has a tagged user
    if message.reply_to_message:
        receiver = message.reply_to_message.from_user
        receiver_id = str(receiver.id)
    elif message.entities and len(message.entities) > 1:
        # This is more complex and might not work reliably
        await update.message.reply_text("Please reply to a message from the user you want to give credits to.")
        return
    else:
        await update.message.reply_text("Please reply to a message from the user you want to give credits to.")
        return

    # Ensure the giver and receiver are not the same
    if giver_id == receiver_id:
        await update.message.reply_text("You cannot give credits to yourself.")
        return

    # Check if an amount was provided
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /give <amount> (by replying to a user's message).")
        return

    amount = int(context.args[0])
    if amount <= 0:
        await update.message.reply_text("Please specify a positive amount of credits to give.")
        return

    # Fetch data for both users
    giver_data = get_user_by_id(giver_id)
    receiver_data = get_user_by_id(receiver_id)

    if not giver_data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return
    if not receiver_data:
        await update.message.reply_text("The user you are trying to give credits to hasn't started the bot.")
        return

    # Check if the giver has enough credits
    if giver_data.get('credits', 0) < amount:
        await update.message.reply_text(f"You don't have enough credits to give. Your current balance is {giver_data.get('credits', 0)}.")
        return

    # Update the balances
    giver_data['credits'] -= amount
    receiver_data['credits'] = receiver_data.get('credits', 0) + amount

    save_user(giver_data)
    save_user(receiver_data)

    # Notify both users
    await update.message.reply_text(
        f"✅ Successfully transferred {amount} credits to {receiver.first_name}. Your new balance is {giver_data['credits']} credits."
    )
    
    # Try to notify the receiver in private if possible
    try:
        await context.bot.send_message(
            chat_id=receiver_id,
            text=f"💰 You have received {amount} credits from {giver.first_name}! Your new balance is {receiver_data['credits']} credits."
        )
    except Exception as e:
        logger.error(f"Failed to notify receiver {receiver_id}: {e}")

async def daily(update: Update, context: CallbackContext) -> None:
    """Handle the daily command with async optimization."""
    if not should_process_update(update):
        return

    user = update.effective_user
    user_id = str(user.id)
    
    # Get user data with caching
    user_data = get_user_by_id_cached(user_id)
    if not user_data:
        await update.message.reply_text("Please use /start first to register.")
        return

    now = datetime.now(timezone.utc)
    last_daily = user_data.get('daily')
    
    if last_daily:
        # Convert to timezone-aware if needed
        if isinstance(last_daily, datetime) and last_daily.tzinfo is None:
            last_daily = last_daily.replace(tzinfo=timezone.utc)
        
        time_diff = now - last_daily
        if time_diff.total_seconds() < 86400:  # 24 hours
            hours_left = int((86400 - time_diff.total_seconds()) / 3600)
            minutes_left = int(((86400 - time_diff.total_seconds()) % 3600) / 60)
            await update.message.reply_text(
                f"⏳ You can claim your daily reward again in {hours_left}h {minutes_left}m"
            )
            return

    # Award daily credits
    daily_amount = 1000
    user_data['credits'] = user_data.get('credits', 0) + daily_amount
    user_data['daily'] = now
    
    # Update database asynchronously
    if user_collection:
        await asyncio.to_thread(
            user_collection.update_one,
            {"user_id": user_id},
            {"$set": user_data}
        )

    await update.message.reply_text(
        f"💰 You received {daily_amount} credits!\n"
        f"Your new balance: {user_data['credits']} credits"
    )

def main() -> None:
    application = Application.builder().token(token).build()

    # Add throttling handler
    application.add_handler(ThrottlingHandler(THROTTLE_RATE, THROTTLE_BURST))

    # Add command handlers with throttling
    command_handlers = [
        ("start", throttle_command()(start)),
        ("profile", throttle_command()(profile)),
        ("reach", throttle_command()(reach)),
        ("reffer", throttle_command()(reffer)),
        ("reset", throttle_command()(reset)),
        ("broadcast", throttle_command()(broadcast)),
        ("daily", throttle_command()(daily)),
        ("give", throttle_command()(give)),
        ("bank", throttle_command()(bank)),
        ("store", throttle_command()(store)),
        ("withdraw", throttle_command()(withdraw)),
        ("addcredits", throttle_command()(add_credits)),
        ("blacklist", throttle_command()(blacklist)),
        ("unblacklist", throttle_command()(unblacklist)),
        ("scan_blacklist", throttle_command()(scan_blacklist)),
        ("chatcricket", throttle_command()(chat_cricket)),
        ("join", throttle_command()(handle_join_button)),
        ("watch", throttle_command()(handle_watch_button)),
        ("limbo", throttle_command()(limbo)),
        ("multiplayer", throttle_command()(multiplayer)),
        ("current", throttle_command()(show_current_players)),
        ("extend", throttle_command()(extend_time)),
        ("stop", throttle_command()(stop_game)),
        ("list", throttle_command()(list_players)),
    ]
    
    for command, handler in command_handlers:
        if command in ENABLED_MODULES and ENABLED_MODULES[command]:
            application.add_handler(CommandHandler(command, handler))
    
    # Add callback query handlers with throttling
    callback_handlers = [
        ("^reset_", throttle_command()(reset_confirmation)),
        ("^toss_", throttle_command()(toss_button)),
        ("^choose_", throttle_command()(choose_button)),
        ("^play_", throttle_command()(play_button)),
        ("^join_", throttle_command()(handle_join_button)),
        ("^watch_", throttle_command()(handle_watch_button)),
        ("^(take|next)_", throttle_command()(handle_limbo_buttons)),
        ("^Mjoin_.*$", throttle_command()(MButton_join)),
        ("^Mremove_.*$", throttle_command()(Mhandle_remove_button)),
        ("^Mplay_.*$", throttle_command()(Mhandle_play_button)),
        ("^Mcancel_.*$", throttle_command()(Mhandle_cancel_button)),
    ]
    
    for pattern, handler in callback_handlers:
        application.add_handler(CallbackQueryHandler(handler, pattern=pattern))
    
    # Add special handlers
    application.add_handler(ChatMemberHandler(auto_ban, ChatMemberHandler.CHAT_MEMBER))
    
    # Add module handlers with filtering
    modules_to_register = [
        get_multiplayer_handlers() if ENABLED_MODULES['multiplayer'] else [],
        get_claim_handlers(),
        get_bdice_handlers(),
        get_mines_handlers() if ENABLED_MODULES['mines'] else [],
        get_hilo_handlers(),
        get_xox_handlers(),
        get_cricket_handlers() if ENABLED_MODULES['cricket'] else [],
        get_genshin_handlers() if ENABLED_MODULES['genshin'] else [],
        get_gambling_handlers(),
    ]
    
    for handlers in modules_to_register:
        for handler in handlers:
            application.add_handler(handler)
    
    # Register word games handlers with filtering
    if ENABLED_MODULES['wordle'] or ENABLED_MODULES['wordhunt']:
        register_handlers(application)
    
    # Register Finder game handlers
    finder_handlers(application)
    
    # Update message handler with filtering
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & filters.ALL & ~filters.COMMAND,
        handle_group_message
    ))

    # Add level system handlers
    for command, handler in get_level_handlers():
        application.add_handler(CommandHandler(command, handler))

    # Schedule daily tax
    job_queue = application.job_queue
    job_queue.run_daily(apply_daily_tax, time=time(hour=0, minute=0))

    application.add_error_handler(error_handler)
   
    application.run_polling()

if __name__ == '__main__':
    main()

