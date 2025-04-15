import asyncio
from pymongo import MongoClient
import os
import secrets
import requests
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, CallbackContext, filters
from telegram.constants import ChatType
from token_1 import token

from genshin_game import get_genshin_handlers
from cricket import (
    chat_command,
    chat_cricket,
    cricket_games,
    handle_join_button,
    handle_watch_button,
    toss_button,
    choose_button,
    play_button,
    handle_wicket,
    end_innings,
    declare_winner,
    update_game_interface,
    setup_jobs,
    get_cricket_handlers
)
from claim import get_claim_handlers, daily
from bank import store, withdraw, bank, get_bank_handlers
from mines_game import  get_mines_handlers
from hilo_game import  get_hilo_handlers
from xox_game import  get_xox_handlers
from bdice import get_bdice_handlers

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
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
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

    # Create profile message
    profile_message = (
        f"👤 <b>Profile for {user.first_name}</b>\n\n"
        f"💰 Credits: {credits}\n"
        f"🏦 Bank: {bank_balance}\n"
        f"💎 Primogems: {primos}\n"
        f"🏆 Wins: {wins}\n"
        f"❌ Losses: {losses}\n"
        f"👥 Referrals: {referrals}\n"
        f"🆔 User ID: {user_id}\n"
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
    
    # Combine the arguments into a single message
    broadcast_message = " ".join(context.args[message_start:])
    
    # Send progress message
    progress_msg = await update.message.reply_text("🔄 Broadcasting in progress...")
    
    # Counters for tracking
    successful_users = 0
    failed_users = 0
    successful_groups = 0
    failed_groups = 0
    
    # Send to users if requested
    if target in ["users", "all"]:
        # Fetch all users from the database
        users = user_collection.find({}, {"user_id": 1})
        total_users = user_collection.count_documents({})
        
        current_count = 0
        for user in users:
            user_id = user["user_id"]
            try:
                await context.bot.send_message(
                    chat_id=user_id, 
                    text=f"📢 <b>Broadcast Message</b>\n\n{broadcast_message}",
                    parse_mode="HTML"
                )
                successful_users += 1
            except Exception as e:
                logger.error(f"Failed to send broadcast to user {user_id}: {e}")
                failed_users += 1
            
            current_count += 1
            if current_count % 50 == 0:  # Update progress every 50 users
                try:
                    await progress_msg.edit_text(f"🔄 Broadcasting in progress... {current_count}/{total_users} users processed")
                except:
                    pass
    
    # Send to groups if requested
    if target in ["groups", "all"]:
        # Fetch all groups from the database
        groups = groups_collection.find({}, {"group_id": 1})
        total_groups = groups_collection.count_documents({})
        
        current_count = 0
        for group in groups:
            group_id = group["group_id"]
            try:
                await context.bot.send_message(
                    chat_id=group_id, 
                    text=f"📢 <b>Broadcast Message</b>\n\n{broadcast_message}",
                    parse_mode="HTML"
                )
                successful_groups += 1
            except Exception as e:
                logger.error(f"Failed to send broadcast to group {group_id}: {e}")
                failed_groups += 1
            
            current_count += 1
            if current_count % 10 == 0:  # Update progress every 10 groups
                try:
                    await progress_msg.edit_text(f"🔄 Broadcasting to groups... {current_count}/{total_groups} groups processed")
                except:
                    pass
    
    # Send a report to the owner
    report_message = (
        "📊 <b>Broadcast Report</b>\n\n"
        f"✅ Successfully sent to {successful_users} users and {successful_groups} groups.\n"
        f"❌ Failed to send to {failed_users} users and {failed_groups} groups.\n\n"
        f"Total recipients: {successful_users + successful_groups}\n"
        f"Total failures: {failed_users + failed_groups}"
    )

    await progress_msg.edit_text(report_message, parse_mode="HTML")

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

async def universal_handler(update: Update, context: CallbackContext):
    try:
        if update.effective_chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            # Add new groups to database only once
            group_id = str(update.effective_chat.id)
            group = groups_collection.find_one({"group_id": group_id})
            
            if not group:
                group_data = {
                    "group_id": group_id,
                    "title": update.effective_chat.title,
                    "added_at": datetime.utcnow(),
                    "last_active": datetime.utcnow()
                }
                save_group(group_data)
            else:
                # Update last active time only if it's been more than 5 minutes
                last_update = group.get("last_active", datetime.utcnow() - timedelta(minutes=6))
                if (datetime.utcnow() - last_update).total_seconds() > 300:
                    groups_collection.update_one(
                        {"group_id": group_id},
                        {"$set": {"last_active": datetime.utcnow()}}
                    )
            
            # Process message reward for genshin users
            user_id = str(update.effective_user.id)
            user_data = get_genshin_user_by_id(user_id)
            
            if not user_data:
                user_data = {
                    "user_id": user_id,
                    "primos": 0,
                    "bag": {},
                    "last_primo_reward": None
                }
            
            # Add 5 primos for every message (with cooldown)
            if not user_data.get("last_primo_reward") or (datetime.utcnow() - user_data["last_primo_reward"]).total_seconds() > 300:
                user_data["primos"] = user_data.get("primos", 0) + 5
                user_data["last_primo_reward"] = datetime.utcnow()
                save_genshin_user(user_data)
        elif update.effective_chat.type == ChatType.PRIVATE:
            await dm_forwarder(update, context)
            await handle_message(update, context)
    except Exception as e:
        logger.error(f"Universal handler error: {str(e)}")
        if update.effective_chat.type == ChatType.PRIVATE:
            await update.message.reply_text("❌ An error occurred while processing your message.")
            
message_deletion_semaphore = asyncio.Semaphore(10)  # Allow 10 concurrent deletions

async def delete_messages(sent_messages, original_message):
    async with message_deletion_semaphore:
        await asyncio.sleep(10)
        for msg in sent_messages:
            try:
                await msg.delete()
            except:
                pass
        try:
            await original_message.delete()
        except:
            pass

async def handle_message(update: Update, context: CallbackContext):
    if not update.message or not update.message.text:
        return

    user_id = str(update.effective_user.id)
    message = update.message.text.lower()
    
    chat_id = update.effective_chat.id

    # Update last interaction time
    last_interaction_time[user_id] = datetime.utcnow()

    # Handle game-specific messages
    if chat_id == update.effective_user.id:  # Private chat
        # Check for active games
        active_game = None
        for game_type in ['cricket']:
            game = db[f'{game_type}_games'].find_one({
                "$or": [
                    {"player1": user_id}, 
                    {"player2": user_id},
                    {"player_id": user_id}  # For single-player games
                ],
                "active": True
            })
            if game:
                active_game = (game_type, game)
                break

        # Check in-memory cricket_games after DB-based ones
        if not active_game:
            for game_id, game_data in cricket_games.items():
                if str(update.effective_user.id) in [str(game_data.get("player1")), str(game_data.get("player2"))]:
                    active_game = ("cricket", game_data)
                    break

        if active_game:
            game_type, game = active_game
            if game_type == 'xox':
                await handle_xox_message(update, context, game)
            elif game_type == 'cricket':
                await handle_cricket_message(update, context, game)
                        
async def handle_cricket_message(update: Update, context: CallbackContext, game: dict) -> None:
    """Handle messages during an active Cricket game.
    Deletes user messages and asks them to use the buttons to play
    """
    user_id = str(update.effective_user.id)
    
    # Check if the message is from a player in the game
    if user_id not in [game.get("player1", ""), game.get("player2", "")]:
        return
        
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="⚠️ Please use the game buttons to play!"
    )

async def handle_hilo_message(update: Update, context: CallbackContext, game: dict) -> None:
    """Handle messages during an active HiLo game.
    Asks them to use the buttons to play
    """
    user_id = str(update.effective_user.id)
    
    # Check if the message is from a player in the game
    if user_id != game.get("player_id", ""):
        return
        
    # Remind them to use buttons
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="⚠️ Please use the game buttons to play!"
    )

async def handle_mines_message(update: Update, context: CallbackContext, game: dict) -> None:
    """Handle messages during an active Mines game.
    Asks them to use the buttons to play
    """
    user_id = str(update.effective_user.id)
    
    # Check if the message is from a player in the game
    if user_id != game.get("player_id", ""):
        return
    # Remind them to use buttons
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="⚠️ Please use the game buttons to play!"
    )

async def handle_xox_message(update: Update, context: CallbackContext, game: dict) -> None:
    """Handle messages during an active XOX game.
    Asks them to use the buttons to play
    """
    user_id = str(update.effective_user.id)
    
    # Check if the message is from a player in the game
    if user_id not in [game.get("player1", ""), game.get("player2", "")]:
        return
    # Remind them to use buttons
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="⚠️ Please use the game buttons to play!"
    )

async def enhanced_chat_system(update: Update, context: CallbackContext) -> None:
    if not update.message or not update.message.text:
        return

    user_id = str(update.effective_user.id)
    message = update.message.text

    # Ignore commands
    if message.startswith('/'):
        return

    # Find active games where the user is involved (either from in-memory or MongoDB)
    active_game = None
    
    # First check in-memory cricket games
    for game_id, game in cricket_games.items():
        if user_id in [str(game.get("player1")), str(game.get("player2"))] or (
            "spectators" in game and user_id in game.get("spectators", set())
        ):
            if game.get("active", True):  # Check if game is active
                active_game = game
                break
    
    # If not found in memory, check MongoDB
    if not active_game:
        game_doc = db['cricket_games'].find_one({
            "$or": [
                {"player1": user_id}, 
                {"player2": user_id},
                {"spectators": user_id}
            ],
            "active": True
        })
        if game_doc:
            active_game = game_doc
    
    if not active_game:
        # No active game or game is over
        return
    
    # Format the message based on user role
    user_name = update.effective_user.first_name
    if user_id == str(active_game.get("player1")):
        role = "🏏 Player 1"
    elif user_id == str(active_game.get("player2")):
        role = "🏏 Player 2"
    else:
        role = "👁️ Spectator"
    
    formatted_message = f"{role} {user_name}: {message}"
    
    # Collect all recipients (players and spectators)
    recipients = []
    if active_game.get("player1"):
        recipients.append(active_game["player1"])
    if active_game.get("player2"):
        recipients.append(active_game["player2"])
    
    # Add spectators (handling both set and list cases)
    spectators = active_game.get("spectators", set())
    if isinstance(spectators, set):
        recipients.extend(spectators)
    elif isinstance(spectators, list):
        recipients.extend(spectators)
    
    # Remove duplicates and the sender
    recipients = list(set(recipients))
    if user_id in recipients:
        recipients.remove(user_id)
    
    # Send message to all recipients and store sent messages for deletion
    sent_messages = []
    for recipient in recipients:
        try:
            sent = await context.bot.send_message(
                chat_id=recipient,
                text=formatted_message
            )
            sent_messages.append(sent)
        except Exception as e:
            logger.error(f"Error sending message to {recipient}: {e}")
    
    # Send confirmation to sender that will also be deleted
    confirmation = await update.message.reply_text("✅ Message sent!")
    sent_messages.append(confirmation)
    
    # Update the last_move timestamp to prevent timeout
    if "game_id" in active_game:
        # Update in-memory game
        game_id = active_game["game_id"]
        if game_id in cricket_games:
            cricket_games[game_id]["last_move"] = datetime.utcnow()
        
        # Also update in MongoDB if applicable
        db['cricket_games'].update_one(
            {"game_id": game_id},
            {"$set": {"last_move": datetime.utcnow(), "active": True}}
        )
    elif "_id" in active_game:
        # Only in MongoDB
        db['cricket_games'].update_one(
            {"_id": active_game["_id"]},
            {"$set": {"last_move": datetime.utcnow(), "active": True}}
        )
    
    # Schedule message deletion after 10 seconds
    async def delete_messages():
        await asyncio.sleep(10)
        for msg in sent_messages:
            try:
                await msg.delete()
            except Exception as e:
                logger.error(f"Error deleting message: {e}")
        
        # Also try to delete the original message
        try:
            await update.message.delete()
        except Exception as e:
            logger.error(f"Error deleting original message: {e}")
    
    # Run the deletion task in the background
    asyncio.create_task(delete_messages())
async def dm_forwarder(update: Update, context: CallbackContext) -> None:
    if not update.message or not update.message.text:
        return

    user_id = str(update.effective_user.id)
    message = update.message.text

    # Ignore commands
    if message.startswith('/'):
        return

    # Check for active cricket game
    game = None
    
    # Check in-memory games first
    for game_id, game_data in cricket_games.items():
        if user_id in [str(game_data.get("player1")), str(game_data.get("player2"))]:
            if game_data.get("active", True):
                game = game_data
                break
    
    # If not found, check MongoDB
    if not game:
        game = db['cricket_games'].find_one({
            "$or": [{"player1": user_id}, {"player2": user_id}],
            "active": True
        })
    
    if not game:
        return
    
    # Get the other player's ID
    other_player_id = game["player2"] if user_id == game["player1"] else game["player1"]
    
    # Forward the message to the other player
    try:
        await context.bot.send_message(
            chat_id=other_player_id,
            text=f"💬 {update.effective_user.first_name}: {message}"
        )
        # Update the last_move timestamp to prevent timeout
        if "game_id" in game:
            game_id = game["game_id"]
            if game_id in cricket_games:
                cricket_games[game_id]["last_move"] = datetime.utcnow()
            db['cricket_games'].update_one(
                {"game_id": game_id},
                {"$set": {"last_move": datetime.utcnow()}}
            )
        elif "_id" in game:
            db['cricket_games'].update_one(
                {"_id": game["_id"]},
                {"$set": {"last_move": datetime.utcnow()}}
            )
    except Exception as e:
        logger.error(f"Error forwarding message: {e}")
        

def main() -> None:
    
    application = Application.builder().token(token).build()

    # Add all handlers inside the main function
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("reach", reach))    
    application.add_handler(CommandHandler("reffer", reffer))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("daily", daily))
    application.add_handler(CommandHandler("give", give))
    application.add_handler(CallbackQueryHandler(reset_confirmation, pattern="^reset_"))
    
    for handler in get_claim_handlers():        
        application.add_handler(handler)
    
    application.add_handler(CommandHandler("addcredits", add_credits))    

    # Add cricket game handlers    
    application.add_handler(CommandHandler("chatcricket", chat_cricket))    
    application.add_handler(CommandHandler("join", handle_join_button))    
    application.add_handler(CommandHandler("watch", handle_watch_button))

    # Add cricket game callback handlers    
    application.add_handler(CallbackQueryHandler(toss_button, pattern="^toss_"))    
    application.add_handler(CallbackQueryHandler(choose_button, pattern="^choose_"))    
    application.add_handler(CallbackQueryHandler(play_button, pattern="^play_"))    
    application.add_handler(CallbackQueryHandler(handle_join_button, pattern=r"^join_"))    
    application.add_handler(CallbackQueryHandler(handle_watch_button, pattern=r"^watch_"))

    # Add cricket game deep link handlers    
    application.add_handler(MessageHandler(        
        filters.Regex(r"^/start ([0-9]{3})$"),        
        handle_join_button    
    ))    
    application.add_handler(MessageHandler(        
        filters.Regex(r"^/start watch_([0-9]{3})$"),        
        handle_watch_button    
    ))

    # Add the banking handlers
    application.add_handler(CommandHandler("bank", bank))
    application.add_handler(CommandHandler("store", store))
    application.add_handler(CommandHandler("withdraw", withdraw))

    # Add game handlers    
    for handler in get_xox_handlers():        
        application.add_handler(handler)    
    for handler in get_hilo_handlers():        
        application.add_handler(handler)    
    for handler in get_mines_handlers():        
        application.add_handler(handler)    
    for handler in get_genshin_handlers():        
        application.add_handler(handler)    
    for handler in get_bank_handlers():        
        application.add_handler(handler)
    for handler in get_cricket_handlers():        
        application.add_handler(handler)
  

    # Universal message handler (must come after all other specific handlers)    
    application.add_handler(MessageHandler(        
        (filters.TEXT | filters.Sticker.ALL) & ~filters.COMMAND,        
        universal_handler    
    ))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Set up other jobs
    setup_jobs(application)

    # Run the bot
    application.run_polling()

if __name__ == '__main__':
    main()
