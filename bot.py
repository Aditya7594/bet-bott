from flask import Flask, request, Response
from threading import Thread
import os

# Create Flask app
app = Flask(__name__)

@app.route('/')
def hello_world():
    return Response('Bot is running!', status=200)

@app.route('/health')
def health_check():
    return Response('OK', status=200)

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle webhook requests from Telegram"""
    if request.method == "POST":
        return Response(status=200)
    return Response(status=400)

# Function to run Flask
def run_flask():
    # Force port to 8000 for health checks
    app.run(host="0.0.0.0", port=8000)

# Start Flask server in background thread
flask_thread = Thread(target=run_flask)
flask_thread.daemon = True  # Make thread daemon so it exits when main program exits
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
from genshin_game import get_genshin_handlers, send_artifact_reward
from multiplayer import (
    get_multiplayer_handlers,
    multiplayer,
    show_current_players,
    extend_time,
    stop_game,
    list_players,
    MButton_join,
    Mhandle_remove_button,
    Mhandle_play_button,
    Mhandle_cancel_button
)
from cricket import (
    get_cricket_handlers,
    chat_cricket,
    cricket_games,
    handle_join_button,
    handle_watch_button,
    toss_button,
    choose_button,
    play_button,
    chat_command,
    stats,
    leaderboard,
    game_history,
    achievements_command,
    category_navigation_callback,
    check_user_started_bot,
    get_user_name_cached,
    update_game_interface,
    game_activity
)
from claim import get_claim_handlers, daily
from wordhunt import register_handlers as get_wordhunt_handlers
from wordle import registers_handlers as get_wordle_handlers
from Finder import get_finder_handlers
from bank import bank, store, withdraw, add_credits, blacklist, unblacklist, auto_ban, scan_blacklist
from mines_game import get_mines_handlers
from hilo_game import get_hilo_handlers
from xox_game import get_xox_handlers
from bdice import get_bdice_handlers
from gambling import get_gambling_handlers
from limbo import limbo, handle_limbo_buttons
from level_system import handle_message, get_handlers as get_level_handlers, apply_daily_tax
from shop import (
    get_shop_handlers,
    shop_command,
    mycollection_command,
    view_command,
    manage_cards,
    reset_collection_command,
    buy_callback,
    setmain_callback
)

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

# Initialize game tracking dictionaries
if not game_activity:
    game_activity = {}

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

    # Add message deduplication
    message_id = update.message.message_id
    if hasattr(context.bot_data, 'last_broadcast_id') and context.bot_data.last_broadcast_id == message_id:
        return
    context.bot_data.last_broadcast_id = message_id

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

async def handle_group_message(update: Update, context: CallbackContext):
    # logger.info("handle_group_message called")
    user = update.effective_user
    user_id = str(user.id)
    chat_id = str(update.effective_chat.id)
    
    # Skip if message is from a bot
    if user.is_bot:
        logger.info(f"Skipping bot message from {user_id}")
        return
        
    # Skip if message is a command
    if update.message.text and update.message.text.startswith('/'):
        logger.info(f"Skipping command message: {update.message.text}")
        return
    
    # Determine message type
    message_type = "text"
    if update.message.sticker:
        message_type = "sticker"
    elif update.message.photo:
        message_type = "photo"
    elif update.message.video:
        message_type = "video"
    elif update.message.document:
        message_type = "document"
    elif update.message.audio:
        message_type = "audio"
    elif update.message.voice:
        message_type = "voice"
    elif update.message.animation:
        message_type = "animation"
    elif update.message.video_note:
        message_type = "video_note"
    elif update.message.location:
        message_type = "location"
    elif update.message.contact:
        message_type = "contact"
    elif update.message.poll:
        message_type = "poll"
    elif update.message.dice:
        message_type = "dice"
    
    logger.info(f"Processing {message_type} message from {user_id}")
    
    # First handle Genshin system
    user_data = get_genshin_user_by_id(user_id)
    now = datetime.now(timezone.utc)

    if not user_data:
        logger.info(f"Creating new Genshin user data for {user_id}")
        # Create new user with timezone-aware datetime
        user_data = {
            "user_id": user_id,
            "primos": 16000,
            "bag": {},
            "message_primo": {
                "count": 0,
                "earned": 0,
                "last_reset": now,
                "last_message": now,
                "message_types": {}
            }
        }
        save_genshin_user(user_data)
    else:
        # Ensure message_primo exists and has timezone-aware datetime
        if "message_primo" not in user_data:
            logger.info(f"Initializing message_primo for {user_id}")
            user_data["message_primo"] = {
                "count": 0,
                "earned": 0,
                "last_reset": now,
                "last_message": now,
                "message_types": {}
            }
        elif user_data["message_primo"].get("last_reset") is None:
            user_data["message_primo"]["last_reset"] = now
            user_data["message_primo"]["last_message"] = now
            user_data["message_primo"]["message_types"] = {}

        # Convert last_reset to timezone-aware if it's not already
        last_reset = user_data["message_primo"]["last_reset"]
        last_message = user_data["message_primo"].get("last_message", now)
        
        if isinstance(last_reset, datetime) and last_reset.tzinfo is None:
            last_reset = last_reset.replace(tzinfo=timezone.utc)
            user_data["message_primo"]["last_reset"] = last_reset
            
        if isinstance(last_message, datetime) and last_message.tzinfo is None:
            last_message = last_message.replace(tzinfo=timezone.utc)
            user_data["message_primo"]["last_message"] = last_message

        # Reset if 1 hour has passed
        time_diff = (now - last_reset).total_seconds()
        if time_diff > 3600:
            logger.info(f"Resetting message count for {user_id} after {time_diff} seconds")
            user_data["message_primo"]["count"] = 0
            user_data["message_primo"]["earned"] = 0
            user_data["message_primo"]["last_reset"] = now
            user_data["message_primo"]["last_message"] = now
            user_data["message_primo"]["message_types"] = {}

        # Check for message cooldown (5 seconds)
        message_cooldown = (now - last_message).total_seconds()
        if message_cooldown >= 5:  # Only count messages that are at least 5 seconds apart
            # Award primos if under limit
            current_earned = user_data["message_primo"]["earned"]
            if current_earned < 100:
                user_data["message_primo"]["count"] += 1
                user_data["message_primo"]["earned"] += 5
                user_data["primos"] = user_data.get("primos", 0) + 5
                user_data["message_primo"]["last_message"] = now
                
                # Track message types
                if "message_types" not in user_data["message_primo"]:
                    user_data["message_primo"]["message_types"] = {}
                user_data["message_primo"]["message_types"][message_type] = user_data["message_primo"]["message_types"].get(message_type, 0) + 1
                
                logger.info(f"Awarded 5 primos to {user_id} for {message_type} message. Total primos: {user_data['primos']}")

        # Save updated user data
        save_genshin_user(user_data)

        # Handle artifact system
        settings = get_group_settings(chat_id)
        if settings.get("artifact_enabled", True):
            if chat_id not in message_counts:
                message_counts[chat_id] = {
                    "count": 0,
                    "last_message": now,
                    "participants": set(),
                    "message_types": {}
                }

            # Check for message cooldown (5 seconds)
            if message_cooldown >= 5:
                message_counts[chat_id]["count"] += 1
                message_counts[chat_id]["last_message"] = now
                message_counts[chat_id]["participants"].add(user_id)
                
                # Track message types
                message_counts[chat_id]["message_types"][message_type] = message_counts[chat_id]["message_types"].get(message_type, 0) + 1
                
                # Clean up old participants (older than 1 hour)
                current_participants = message_counts[chat_id]["participants"]
                message_counts[chat_id]["participants"] = {
                    pid for pid in current_participants 
                    if (now - user_data.get("message_primo", {}).get("last_message", now)).total_seconds() < 3600
                }

                threshold = settings.get("artifact_threshold", 50)
                logger.info(f"Message count for chat {chat_id}: {message_counts[chat_id]['count']}/{threshold}")
                
                if message_counts[chat_id]["count"] >= threshold:
                    message_counts[chat_id]["count"] = 0
                    logger.info(f"Threshold reached for chat {chat_id}, sending artifact reward")
                    await send_artifact_reward(chat_id, context)
    
    # Then handle leveling system
    logger.info("Calling handle_message for leveling system")
    await handle_message(update, context)
    logger.info("handle_group_message completed")

async def handle_watch_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    _, game_id = query.data.split('_', 1)  

    if not await check_user_started_bot(update, context):
        return

    if game_id not in cricket_games:
        await query.answer("Game not found or expired!")
        return

    game = cricket_games[game_id]
    
    if user_id in [game["player1"], game["player2"]]:
        await query.answer("You're already playing in this game!")
        return
    
    game["spectators"].add(user_id)
    
    player1_name = (await get_user_name_cached(game["player1"], context))
    player2_name = "Waiting for opponent" if not game["player2"] else (await get_user_name_cached(game["player2"], context))
    
    bot_username = (await context.bot.get_me()).username
    keyboard = [[InlineKeyboardButton("🎮 Open Cricket Game", url=f"https://t.me/{bot_username}")]]
    
    try:
        msg = await context.bot.send_message(
            chat_id=user_id,
            text=f"👁️ You're now watching the cricket match!\n"
                 f"🧑 Player 1: {player1_name}\n"
                 f"🧑 Player 2: {player2_name}\n\n"
                 f"Open the bot to view live match updates:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        game["message_id"][user_id] = msg.message_id
    except Exception as e:
        logger.error(f"Error sending watch confirmation to {user_id}: {e}")
        await query.answer("Error joining as spectator!")
        return
    
    if game["player2"] and "batter" in game and game["batter"]:
        try:
            await update_game_interface(game_id, context)
        except Exception as e:
            logger.error(f"Error updating game interface for spectator {user_id}: {e}")

async def chat_command(update: Update, context: CallbackContext) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /chat <message>")
        return

    user = update.effective_user
    user_id = str(user.id)
    message = " ".join(context.args)

    if not await check_user_started_bot(update, context):
        return

    # Find active game
    active_game = None
    active_game_id = None
    for game_id, game in cricket_games.items():
        if user_id in [game["player1"], game["player2"]] or user_id in game.get("spectators", set()):
            active_game = game
            active_game_id = game_id
            break

    if not active_game:
        await update.message.reply_text("❌ You're not part of an active cricket game.")
        return

    # Get current time
    now = datetime.now(timezone.utc)

    # Initialize or update message tracking
    if "chat_messages" not in active_game:
        active_game["chat_messages"] = []
    
    # Check for message cooldown (5 seconds)
    last_message_time = active_game.get("last_chat_message", now - timedelta(seconds=10))
    if isinstance(last_message_time, datetime) and last_message_time.tzinfo is None:
        last_message_time = last_message_time.replace(tzinfo=timezone.utc)
    
    message_cooldown = (now - last_message_time).total_seconds()
    if message_cooldown < 5:
        await update.message.reply_text("⏳ Please wait 5 seconds between chat messages.")
        return

    # Update game activity and message tracking
    update_game_activity(active_game_id)
    active_game["last_chat_message"] = now

    # Format and store message
    sender_name = user.first_name or "Player"
    formatted_message = f"💬 {sender_name}: {message}"
    
    # Store message with timestamp
    active_game["chat_messages"].append({
        "sender": user_id,
        "sender_name": sender_name,
        "message": message,
        "timestamp": now
    })

    # Get all recipients (players and spectators)
    recipients = set([active_game["player1"], active_game["player2"]] + list(active_game.get("spectators", [])))
    message_ids = []

    # Send to all recipients privately and collect message_ids
    for uid in recipients:
        if uid != user_id:  # Don't send to sender
            try:
                sent_msg = await context.bot.send_message(
                    chat_id=uid,
                    text=formatted_message,
                    parse_mode="Markdown"
                )
                message_ids.append((uid, sent_msg.message_id))
            except Exception as e:
                logger.error(f"Couldn't send DM to {uid}: {e}")

    # Schedule deletion of command and DMs in background
    async def delete_later():
        await asyncio.sleep(10)
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=update.message.message_id
            )
        except Exception as e:
            logger.error(f"Error deleting /chat command message: {e}")
        
        for uid, mid in message_ids:
            try:
                await context.bot.delete_message(
                    chat_id=uid,
                    message_id=mid
                )
            except Exception as e:
                logger.error(f"Error deleting DM message for {uid}: {e}")

    asyncio.create_task(delete_later())

def main() -> None:
    # Create the Application
    application = Application.builder().token(token).build()

    # Add command handlers
    command_handlers = [
        ("start", start),
        ("profile", profile),
        ("reach", reach),
        ("reffer", reffer),
        ("reset", reset),
        ("broadcast", broadcast),
        ("daily", daily),
        ("give", give),
        ("bank", bank),
        ("store", store),
        ("withdraw", withdraw),
        ("addcredits", add_credits),
        ("blacklist", blacklist),
        ("unblacklist", unblacklist),
        ("scan_blacklist", scan_blacklist),
        ("chatcricket", chat_cricket),
        ("join", handle_join_button),
        ("watch", handle_watch_button),
        ("limbo", limbo),
        ("multiplayer", multiplayer),
        ("current", show_current_players),
        ("extend", extend_time),
        ("stop", stop_game),
        ("list", list_players),
        ("shop", shop_command),
        ("mycollection", mycollection_command),
        ("view", view_command),
        ("managecards", manage_cards),
        ("resetcollection", reset_collection_command),
        ("chat", chat_command),
        ("stats", stats),
        ("leaderboard", leaderboard),
        ("history", game_history),
        ("achievements", achievements_command),
    ]
    
    for command, handler in command_handlers:
        application.add_handler(CommandHandler(command, handler))
    
    # Add callback query handlers
    callback_handlers = [
        ("^reset_", reset_confirmation),
        ("^toss_", toss_button),
        ("^choose_", choose_button),
        ("^play_", play_button),
        ("^join_", handle_join_button),
        ("^watch_", handle_watch_button),
        ("^(take|next)_", handle_limbo_buttons),
        ("^Mjoin_.*$", MButton_join),
        ("^Mremove_.*$", Mhandle_remove_button),
        ("^Mplay_.*$", Mhandle_play_button),
        ("^Mcancel_.*$", Mhandle_cancel_button),
        ("^buy_", buy_callback),
        ("^setmain_", setmain_callback),
        ("^category_", category_navigation_callback),
        ("^close_achievements$", category_navigation_callback),
    ]
    
    for pattern, handler in callback_handlers:
        application.add_handler(CallbackQueryHandler(handler, pattern=pattern))
    
    # Add special handlers
    application.add_handler(ChatMemberHandler(auto_ban, ChatMemberHandler.CHAT_MEMBER))
    
    # Add module handlers
    modules_to_register = [
        get_multiplayer_handlers(),
        get_claim_handlers(),
        get_bdice_handlers(),
        get_mines_handlers(),
        get_hilo_handlers(),
        get_xox_handlers(),
        get_cricket_handlers(),
        get_genshin_handlers(),
        get_gambling_handlers(),
        get_wordhunt_handlers(application),  # WordHunt handlers
        get_wordle_handlers(application),    # Wordle handlers
        get_finder_handlers(application),
        get_shop_handlers(),  # Add shop handlers
    ]
    
    for handlers in modules_to_register:
        for handler in handlers:
            application.add_handler(handler)
    
    # Update message handler to handle all message types in groups
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
    
    # Start the bot in polling mode
    logger.info("Starting bot in polling mode...")
    application.run_polling()

if __name__ == '__main__':
    main()