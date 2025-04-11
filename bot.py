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
    chat_cricket,
    handle_join_button,
    handle_watch_button,
    toss_button,
    choose_button,
    play_button,
    handle_wicket,
    end_innings,
    declare_winner,
    update_game_interface,
    get_cricket_handlers)
from claim import get_claim_handlers, daily
from bank import store, withdraw, bank, get_bank_handlers
from hilo_game import start_hilo, hilo_click, hilo_cashout, get_hilo_handlers
from mines_game import Mines, Mines_click, Mines_CashOut, get_mines_handlers
from xox_game import get_xox_handlers

# Constants and settings
OWNER_ID = 5667016949
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot') 
db = client['telegram_bot']
users_collection = db['users']
genshin_collection = db['genshin_users']

# Global variable for tracking last interaction time
last_interaction_time = {}

async def timeout_task(context: CallbackContext) -> None:
    """Checks for game timeouts and handles them."""
    now = datetime.utcnow()
    
    # Check each game collection for timeouts
    for game_type in ['cricket', 'hilo', 'mines', 'xox']:
        games = db[f'{game_type}_games'].find({"active": True})
        
        for game in games:
            if game.get("last_move") is None:
                continue
            if (now - game["last_move"]) > timedelta(minutes=5):
                # Create a dummy query for timeout
                class DummyQuery:
                    pass
                dummy_query = DummyQuery()
                dummy_query.message = None
                await handle_timeout(dummy_query, game)


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

def generate_referral_link(user_id):
    return f"https://t.me/YourBotUsername?start=ref{user_id}"

async def start(update: Update, context: CallbackContext) -> None:
    """Handle the /start command."""
    user = update.effective_user
    user_id = str(user.id)
    
    # Check if user exists in database
    user_data = users_collection.find_one({"user_id": user_id})
    if not user_data:
        # Create new user
        users_collection.insert_one({
            "user_id": user_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "created_at": datetime.utcnow(),
            "last_active": datetime.utcnow()
        })
        await update.message.reply_text(
            f"👋 Welcome {user.first_name}! I'm your cricket game bot.\n\n"
            f"Use /chatcricket in a group to start a new game!"
        )
    else:
        # Update last active
        users_collection.update_one(
            {"user_id": user_id},
            {"$set": {"last_active": datetime.utcnow()}}
        )
        await update.message.reply_text(
            f"👋 Welcome back {user.first_name}! Use /chatcricket in a group to start a new game!"
        )

async def help_command(update: Update, context: CallbackContext) -> None:
    """Handle the /help command."""
    help_text = (
        "🎮 *Cricket Game Bot Commands:*\n\n"
        "/start - Start the bot\n"
        "/help - Show this help message\n"
        "/chatcricket - Start a new cricket game (group only)\n"
        "/join [code] - Join an existing game\n"
        "/watch [code] - Watch an existing game\n\n"
        "*How to Play:*\n"
        "1. Start a game with /chatcricket in a group\n"
        "2. Share the game code with your opponent\n"
        "3. Join the game using the code\n"
        "4. Play the toss and choose to bat or bowl\n"
        "5. Take turns choosing numbers (1-6)\n"
        "6. Score runs or take wickets!\n\n"
        "*Game Rules:*\n"
        "• 5 overs per innings\n"
        "• 10 wickets per innings\n"
        "• Choose numbers 1-6 for runs\n"
        "• Matching numbers = wicket\n"
        "• Different numbers = runs (batter's choice)"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

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

    # Get user's credits
    credits = user_data.get('credits', 0)

    # Create profile message
    profile_message = (
        f"👤 <b>Profile for {user.first_name}</b>\n\n"
        f"💰 Credits: {credits}\n"
        f"🆔 User ID: {user_id}\n"
    )

    await update.message.reply_text(profile_message, parse_mode='HTML')

async def add_credits(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = user.id
    target_user_id = None
    credits_to_add = None

    # Check if the user is the owner
    if user_id != OWNER_ID:  # Ensure OWNER_ID is a single integer
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


async def reset_confirmation(update: Update, context: CallbackContext) -> None:
    """Handle reset confirmation callback."""
    query = update.callback_query
    user_id = query.from_user.id

    # Check if the user is the owner
    if user_id != OWNER_ID:
        await query.answer("You don't have permission to do this.", show_alert=True)
        return

    # Check the callback data (Yes or No)
    if query.data == "reset_yes":
        # Reset all users' data and set specified values to defaults
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
            "bag": {},
            "bank": 0,  # Reset bank balance to 0
            "cards": [],  # Reset cards to 0
        }})
        
        # Inform the owner that the reset was successful
        await query.answer("All user data has been reset to default values, and all users have received 5000 credits.", show_alert=True)

    elif query.data == "reset_no":
        # Inform the owner that the reset was canceled
        await query.answer("User data reset was canceled.", show_alert=True)

    # Delete the inline keyboard after answering
    await query.edit_message_reply_markup(reply_markup=None)

async def reset(update: Update, context: CallbackContext) -> None:
    """Handle the reset command."""
    user_id = update.effective_user.id

    # Check if the user is the owner
    if user_id != OWNER_ID:
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

    await update.message.reply_text(
        "Are you sure you want to reset all user data? This will wipe all progress!",
        reply_markup=reply_markup
    )

async def reach(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    # Check if the user is the owner
    if user_id != OWNER_ID:
        await update.message.reply_text("🔒 You don't have permission to use this command.")
        return

    try:
        # Fetch total users
        total_users = users_collection.count_documents({})

        # Fetch total Genshin users
        total_genshin_users = genshin_collection.count_documents({})

        # Fetch total credits in the game
        total_credits_result = users_collection.aggregate([
            {"$group": {"_id": None, "total_credits": {"$sum": "$credits"}}}
        ])
        total_credits_value = next(total_credits_result, {}).get("total_credits", 0)

        # Fetch total groups the bot is in
        total_groups = db["groups"].count_documents({})  # Assuming you have a 'groups' collection

        # Construct the stats message
        stats_message = (
            "<b>🤖 Bot Statistics:</b>\n\n"
            f"👥 Total Users: {total_users}\n"
            f"🌌 Total Genshin Users: {total_genshin_users}\n"
            f"💰 Total Credits in Game: {total_credits_value}\n"
            f"🏢 Total Groups: {total_groups}\n"
        )

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
        await update.message.reply_text("❗ Usage: /broadcast <message>")
        return

    # Combine the arguments into a single message
    broadcast_message = " ".join(context.args)

    # Fetch all users and groups from the database
    users = users_collection.find({}, {"user_id": 1})
    groups = []  

    # Counters for tracking
    successful_users = 0
    failed_users = 0
    successful_groups = 0
    failed_groups = 0

    # Send the message to all users
    for user in users:
        user_id = user["user_id"]
        try:
            await context.bot.send_message(chat_id=user_id, text=broadcast_message)
            successful_users += 1
        except Exception as e:
            logger.error(f"Failed to send broadcast to user {user_id}: {e}")
            failed_users += 1

    # Send the message to all groups (if applicable)
    for group in groups:
        group_id = group["group_id"]
        try:
            await context.bot.send_message(chat_id=group_id, text=broadcast_message)
            successful_groups += 1
        except Exception as e:
            logger.error(f"Failed to send broadcast to group {group_id}: {e}")
            failed_groups += 1

    # Send a report to the owner
    report_message = (
        "📢 **Broadcast Report**\n\n"
        f"✅ Successfully sent to {successful_users} users and {successful_groups} groups.\n"
        f"❌ Failed to send to {failed_users} users and {failed_groups} groups.\n\n"
        f"Total recipients: {successful_users + successful_groups}\n"
        f"Total failures: {failed_users + failed_groups}"
    )

    await update.message.reply_text(report_message)

async def give(update: Update, context: CallbackContext) -> None:
    giver = update.effective_user
    giver_id = str(giver.id)
    message = update.message

    # Check if the command is a reply or has a tagged user
    if message.reply_to_message:
        receiver = message.reply_to_message.from_user
    elif message.entities and len(message.entities) > 1:
        receiver = message.parse_entities().get(list(message.entities)[1])
    else:
        await update.message.reply_text("Please tag a user or reply to their message to give credits.")
        return

    receiver_id = str(receiver.id)

    # Ensure the giver and receiver are not the same
    if giver_id == receiver_id:
        await update.message.reply_text("You cannot give credits to yourself.")
        return

    # Check if an amount was provided
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /give <amount> (by tagging or replying to a user).")
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
    if giver_data['credits'] < amount:
        await update.message.reply_text(f"You don't have enough credits to give. Your current balance is {giver_data['credits']}.")
        return

    # Update the balances
    giver_data['credits'] -= amount
    receiver_data['credits'] += amount

    save_user(giver_data)
    save_user(receiver_data)

    # Notify both users
    await update.message.reply_text(
        f"Successfully transferred {amount} credits to {receiver.first_name}. Your new balance is {giver_data['credits']} credits."
    )
    await context.bot.send_message(
        chat_id=receiver_id,
        text=f"You have received {amount} credits from {giver.first_name}! Your new balance is {receiver_data['credits']} credits."
    )


async def universal_handler(update: Update, context: CallbackContext):
    try:
        if update.effective_chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            # Only reward primos for text messages
            if update.message and update.message.text and not update.message.text.startswith("/"):
                user_id = str(update.effective_user.id)
                user_data = get_genshin_user_by_id(user_id)
                
                if not user_data:
                    # Create new user data if it doesn't exist
                    user_data = {
                        "user_id": user_id,
                        "primos": 0,
                        "bag": {},
                        "last_primo_reward": None
                    }
                
                # Check if user has received primos in the last hour
                current_time = datetime.utcnow()
                last_reward = user_data.get("last_primo_reward")
                
                if not last_reward or (current_time - last_reward).total_seconds() > 3600:  # 1 hour cooldown
                    # Add 5 primos
                    user_data["primos"] += 5
                    user_data["last_primo_reward"] = current_time
                    save_genshin_user(user_data)
                    
                    # Log the reward
                    logger.info(f"User {user_id} received 5 primos for group chat message")
                    
        elif update.effective_chat.type == ChatType.PRIVATE:
            await dm_forwarder(update, context)
            await handle_message(update, context)
    except Exception as e:
        logger.error(f"Universal handler error: {str(e)}")
        if update.effective_chat.type == ChatType.PRIVATE:
            await update.message.reply_text("❌ An error occurred while processing your message.")
async def handle_message(update: Update, context: CallbackContext):
    if not update.message or not update.message.text:
        return

    user_id = str(update.effective_user.id)
    message = update.message.text.lower()
    
    chat_id = update.effective_chat.id

    # Check if user is muted
    # Update last interaction time
    last_interaction_time[user_id] = datetime.utcnow()

    # Handle game-specific messages
    if chat_id == update.effective_user.id:  # Private chat
        # Check for active games
        active_game = None
        for game_type in ['xox', 'cricket', 'hilo', 'mines']:
            game = db[f'{game_type}_games'].find_one({
                "$or": [{"player1": user_id}, {"player2": user_id}],
                "active": True
            })
            if game:
                active_game = (game_type, game)
                break

        if active_game:
            game_type, game = active_game
            if game_type == 'xox':
                await handle_xox_message(update, context, game)
            elif game_type == 'cricket':
                await handle_cricket_message(update, context, game)
            elif game_type == 'hilo':
                await handle_hilo_message(update, context, game)
            elif game_type == 'mines':
                await handle_mines_message(update, context, game)

async def handle_cricket_message(update: Update, context: CallbackContext, game: dict) -> None:
    """Handle messages during an active Cricket game.
    Deletes user messages and asks them to use the buttons to play
    """
    """Handle messages during an active Cricket game."""
    user_id = str(update.effective_user.id)
    
    # Check if the message is from a player in the game
    if user_id not in [game["player1"], game["player2"]]:
        return
        
    # Check for game timeout
    if (datetime.utcnow() - game["last_move"]) > timedelta(minutes=5):
        await handle_timeout(update.callback_query, game)
        return
        
    # Ignore messages during active games
    await update.message.delete()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="⚠️ Please use the game buttons to play!",
        delete_after=3
    )

async def handle_hilo_message(update: Update, context: CallbackContext, game: dict) -> None:
    """Handle messages during an active HiLo game.
    Deletes user messages and asks them to use the buttons to play
    """
    
    """Handle messages during an active HiLo game."""
    user_id = str(update.effective_user.id)
    
    # Check if the message is from a player in the game
    if user_id != game["player_id"]:
        return
        
    # Check for game timeout
    if (datetime.utcnow() - game["last_move"]) > timedelta(minutes=5):
        await handle_timeout(update.callback_query, game)
        return
        
    # Ignore messages during active games
    await update.message.delete()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="⚠️ Please use the game buttons to play!",
        delete_after=3
    )

async def handle_mines_message(update: Update, context: CallbackContext, game: dict) -> None:
    """Handle messages during an active Mines game.
    Deletes user messages and asks them to use the buttons to play
    """

    """Handle messages during an active Mines game."""
    user_id = str(update.effective_user.id)
    
    # Check if the message is from a player in the game
    if user_id != game["player_id"]:
        return
        
    # Check for game timeout
    if (datetime.utcnow() - game["last_move"]) > timedelta(minutes=5):
        await handle_timeout(update.callback_query, game)
        return
        
    # Ignore messages during active games
    await update.message.delete()
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="⚠️ Please use the game buttons to play!",
        delete_after=3
    )

async def handle_timeout(query: CallbackQuery, game: dict) -> None:
    """Handle game timeout for any game type."""

    """Handle game timeout for any game type."""
    game_type = game.get("game_type", "unknown")
    game_id = game.get("_id", game.get("game_code", "unknown"))
    
    # Update game status in database
    db[f"{game_type}_games"].update_one(
        {"_id": game_id},
        {"$set": {"active": False}}
    )
    
    # Send timeout message
    timeout_message = (
        f"⏰ *Game Timed Out!* ⏰\n\n"
        "The game has ended due to inactivity.\n"
        "Your credits have been refunded."
    )
    
    try:
        if query and query.message:
            await query.edit_message_text(
                timeout_message,
                parse_mode="Markdown"
            )
        else:
            # If no query or message, send a new message to the game's chat
            chat_id = game.get("chat_id") or game.get("group_chat_id")
            if chat_id:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=timeout_message,
                    parse_mode="Markdown"
                )
    except Exception as e:
        logger.error(f"Error sending timeout message: {e}")
    
    # Refund credits if applicable
    if "bet" in game:
        user_id = game.get("player_id") or game.get("player1")
        if user_id:
            user_data = get_user_by_id(user_id)
            if user_data:
                user_data["credits"] += game["bet"]
                save_user(user_data)


            

async def dm_forwarder(update: Update, context: CallbackContext) -> None:
    """Forward messages between users in cricket games."""
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    message = update.message.text

    # Ignore commands
    if message.startswith('/'):
        return

    # Check for active cricket game
    game = db['cricket_games'].find_one({
        "$or": [{"player1": user_id}, {"player2": user_id}],
        "active": True
    })
    
    if game:
        # Get the other player's ID
        other_player = game["player2"] if user_id == game["player1"] else game["player1"]
        
        # Forward the message to the other player
        try:
            await context.bot.send_message(
                chat_id=other_player,
                text=f"💬 {update.effective_user.first_name}: {message}"
            )
        except Exception as e:
            logger.error(f"Error forwarding message: {e}")

async def chat_command_cricket(update: Update, context: CallbackContext) -> None:
    """Handle the /c command for chat during cricket games."""
    if not context.args:
        await update.message.reply_text("Usage: /c <message>")
        return

    user = update.effective_user
    user_id = str(user.id)
    message = " ".join(context.args)

    # Check for active cricket game
    game = db['cricket_games'].find_one({
        "$or": [{"player1": user_id}, {"player2": user_id}],
        "active": True
    })
    
    if game:
        # Get the other player's ID
        other_player_id = game["player2"] if user_id == game["player1"] else game["player1"]
        
        # Format the message
        formatted_message = f"💬 {user.first_name}: {message}"

        try:
            # Send the message to the other player's DM
            await context.bot.send_message(
                chat_id=int(other_player_id),  # Convert to integer
                text=formatted_message
            )
            # Delete the command message in private chat
            await update.message.delete()
        except Exception as e:
            logger.error(f"Error sending chat message: {e}")
            await update.message.reply_text("❌ Failed to send message to the other player.")
    else:
        await update.message.reply_text("❌ You are not in an active cricket game.")
    

    async def wrapper(update: Update, context: CallbackContext):
        user_id = str(update.effective_user.id)
        user_data = get_user_by_id(user_id)
        if user_data is None:
            await update.message.reply_text("You need to start the bot first by using /start.")
            return
        await func(update, context)
    return wrapper

def check_started(func):

def main() -> None:

    application = Application.builder().token(token).build()
    
    # Add all handlers inside the main function
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("profile", check_started(profile)))
    application.add_handler(CommandHandler("give", check_started(give)))
    application.add_handler(CommandHandler("reach", reach))
    application.add_handler(CommandHandler("reffer", reffer))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("daily", daily))
    application.add_handler(CallbackQueryHandler(reset_confirmation, pattern="^reset_"))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("help", help_command))
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
    application.add_handler(CallbackQueryHandler(handle_join_button, pattern="^join_"))
    application.add_handler(CallbackQueryHandler(handle_watch_button, pattern="^watch_"))

    # Add cricket game deep link handlers
    application.add_handler(MessageHandler(
        filters.Regex(r"^/start ([0-9]{3})$"),
        handle_join_button
    ))
    application.add_handler(MessageHandler(
        filters.Regex(r"^/start watch_([0-9]{3})$"),
        handle_watch_button
    ))

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


    # Add the /c command handler before the universal message handler
    application.add_handler(CommandHandler("c", chat_command_cricket))

    # Universal message handler (must come after all other specific handlers)
    application.add_handler(MessageHandler(
        (filters.TEXT | filters.Sticker.ALL) & ~filters.COMMAND,
        universal_handler
    ))


    application.job_queue.run_repeating(timeout_task, interval=60, first=10, name='timeout_task')

    # Add error handler
    application.add_error_handler(error_handler)

    # Run the bot
    application.run_polling()

if __name__ == '__main__':
    main()
