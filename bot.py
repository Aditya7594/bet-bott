from pymongo import MongoClient
import asyncio
import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext
from token_1 import token
import random
import secrets

# Global variables
OWNER_ID = 5667016949

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot') 
db = client['telegram_bot']
users_collection = db['users']

# MongoDB management functions
def get_user_by_id(user_id):
    return users_collection.find_one({"user_id": user_id})

def save_user(user_data):
    users_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

def update_user_credits(user_id, amount):
    users_collection.update_one({"user_id": user_id}, {"$inc": {"credits": amount}})

def update_user_win_loss(user_id, win=True):
    if win:
        users_collection.update_one({"user_id": user_id}, {"$inc": {"win": 1}})
    else:
        users_collection.update_one({"user_id": user_id}, {"$inc": {"loss": 1}})

# Telegram message formatting function
def escape_markdown_v2(text):
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)

# Start function
async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    existing_user = get_user_by_id(user_id)

    if not existing_user:
        new_user = {
            "user_id": user_id,
            "join_date": datetime.now().strftime('%m/%d/%y'),
            "credits": 5000,  # Starting credits
            "daily": None,
            "win": 0,
            "loss": 0,
            "achievement": [],
            "faction": "None",
            "ban": None,
            "title": "None"
        }
        save_user(new_user)
        logger.info(f"User {user_id} started the bot.")

        await update.message.reply_text(
            "Welcome! You've received 5000 credits to start betting. Use /profile to check your details."
        )
    else:
        await update.message.reply_text(
            "You have already started the bot. Use /profile to view your details."
        )

# Profile function
async def profile(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    user_data = get_user_by_id(user_id)

    if user_data:
        profile_message = (
            f"👤 *{user.first_name}* 【{user_data['faction']}】\n"
            f"🆔 *ID*: {user_data['user_id']}\n"
            f"💰 *Units*: {user_data['credits']} 💎\n\n"
            f"🏆 *Wins*: {user_data['win']}\n"
            f"💔 *Losses*: {user_data['loss']}\n\n"
            f"🎖️ *Title*: {user_data['title']}\n"
        )

        try:
            photos = await context.bot.get_user_profile_photos(user_id=user.id)
            if photos.total_count > 0:
                await update.message.reply_photo(photos.photos[0][-1].file_id, caption=profile_message, parse_mode='Markdown')
            else:
                await update.message.reply_text(profile_message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error fetching profile picture for user {user_id}: {e}")
            await update.message.reply_text(profile_message, parse_mode='Markdown')
    else:
        await update.message.reply_text("You have not started using the bot yet. Use /start to begin.")

# Roulette game
async def roulette(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    user_data = get_user_by_id(user_id)

    if not user_data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    try:
        bet_amount = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Please use the format: /roulette <amount>")
        return

    if bet_amount <= 0 or bet_amount > user_data["credits"]:
        await update.message.reply_text("Invalid bet amount or insufficient credits.")
        return

    result = secrets.choice(["win", "lose"])
    if result == "win":
        update_user_credits(user_id, bet_amount * 2)
        message = f"🎉 You won! Your bet doubled to {bet_amount * 2} units."
    else:
        update_user_credits(user_id, -bet_amount)
        message = f"😞 You lost! {bet_amount} units have been deducted from your profile."

    await update.message.reply_text(message)

async def flip(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    users = load_users()

    if user_id not in users:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    try:
        choice = context.args[0].upper()
        bet_amount = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /flip [H/T] [amount]")
        return

    if choice not in ["H", "T"]:
        await update.message.reply_text("Invalid choice. Use 'H' for heads or 'T' for tails.")
        return

    if bet_amount <= 0 or bet_amount > users[user_id]["credits"]:
        await update.message.reply_text("Invalid bet amount.")
        return

    result = random.choice(["H", "T"])
    if result == choice:
        users[user_id]["credits"] += bet_amount
        message = f"🎉 You won! {bet_amount} credits added."
    else:
        users[user_id]["credits"] -= bet_amount
        message = f"😞 You lost! {bet_amount} credits deducted."

    save_users(users)
    await update.message.reply_text(message)

# Generic bet command
async def bet(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)
    users = load_users()

    if user_id not in users:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    try:
        bet_amount = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Please use the format: /bet <amount>")
        return

    if bet_amount <= 0 or bet_amount > users[user_id]["credits"]:
        await update.message.reply_text("Invalid bet amount or insufficient credits.")
        return

    result = secrets.choice(["win", "lose"])
    if result == "win":
        users[user_id]["credits"] += bet_amount
        users[user_id]["win"] += 1
        message = f"You won! {bet_amount} credits have been added to your profile."
    else:
        users[user_id]["credits"] -= bet_amount
        users[user_id]["loss"] += 1
        message = f"You lost! {bet_amount} credits have been deducted from your profile."

    save_users(users)
    await update.message.reply_text(message)


import random

# Dart game function
async def dart(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    users = load_users()

    if user_id not in users:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    result = random.choice(["bullseye", "miss"])
    if result == "bullseye":
        users[user_id]["credits"] += 100
        await update.message.reply_text("🎯")  # Send emoji first
        await update.message.reply_text("Bullseye! You earned 100 credits! 😎")  # Send text message
    else:
        users[user_id]["credits"] -= 100
        await update.message.reply_text("🎯")  # Send emoji first
        await update.message.reply_text("Miss! You lost 100 credits. 😢")  # Send text message

    save_users(users)  # Save user data

# Basketball game function
async def basketball(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    users = load_users()

    if user_id not in users:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    result = random.choice(["score", "miss"])
    if result == "score":
        users[user_id]["credits"] += 75
        await update.message.reply_text("🏀")  # Send emoji first
        await update.message.reply_text("Score! You earned 75 credits! 🏆")  # Send text message
    else:
        users[user_id]["credits"] -= 75
        await update.message.reply_text("🏀")  # Send emoji first
        await update.message.reply_text("Miss! You lost 75 credits. 😕")  # Send text message

    save_users(users)  # Save user data

# Football game function
async def football(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    users = load_users()

    if user_id not in users:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    result = random.choice(["goal", "miss"])
    if result == "goal":
        users[user_id]["credits"] += 50
        await update.message.reply_text("⚽")  # Send emoji first
        await update.message.reply_text("Goal! You earned 50 credits! 🎉")  # Send text message
    else:
        users[user_id]["credits"] -= 50
        await update.message.reply_text("⚽")  # Send emoji first
        await update.message.reply_text("Miss! You lost 50 credits. 😔")  # Send text message

    save_users(users)  # Save user data

# Slot Machine game function
async def slot_machine(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    users = load_users()

    if user_id not in users:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    slot_emojis = ["🍒", "🍋", "🍇", "🍉", "🔔", "💎"]
    slot_result = [random.choice(slot_emojis) for _ in range(3)]

    # Send slot result emojis first
    await update.message.reply_text(f"{slot_result[0]} {slot_result[1]} {slot_result[2]}")

    if len(set(slot_result)) == 1:  # All three are the same
        users[user_id]["credits"] += 500
        await update.message.reply_text("Jackpot! You won 500 credits! 💰")  # Send text message
    else:
        users[user_id]["credits"] -= 100
        await update.message.reply_text("No luck this time. You lost 100 credits. 😞")  # Send text message

    save_users(users)  # Save user data

async def add_units(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    try:
        target_user_id = context.args[0]
        amount = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /add <user_id> <amount>")
        return

    update_user_credits(target_user_id, amount)
    await update.message.reply_text(f"Added {amount} credits to user {target_user_id}.")

async def backup(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("You do not have permission to use this command.")
        return

    files_to_send = [USERS_FILE]  
    for file_path in files_to_send:
        try:
            with open(file_path, 'rb') as file:
                await context.bot.send_document(chat_id=OWNER_ID, document=file, filename=os.path.basename(file_path))
        except FileNotFoundError:
            await update.message.reply_text(f"File {file_path} not found.")
        except Exception as e:
            logger.error(f"Error sending file {file_path}: {e}")
            await update.message.reply_text(f"Error sending file {file_path}: {str(e)}")

async def inline_start(update: Update, context: CallbackContext) -> None:
    button = InlineKeyboardButton("Start Bot", url=f"https://t.me/{context.bot.username}?start=start")
    reply_markup = InlineKeyboardMarkup([[button]])
    await update.message.reply_text("Please start the bot by clicking the button below:", reply_markup=reply_markup)

async def broadcast(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if user_id not in load_sudo_ids():  # Assuming you have a function to load sudo IDs
        await update.message.reply_text("You do not have permission to use this command.")
        return

    message = ' '.join(context.args)
    if not message:
        await update.message.reply_text("Please provide a message to broadcast.")
        return

    users = load_users()  # Load users to get their IDs
    for uid in users.keys():
        try:
            await context.bot.send_message(chat_id=uid, text=message)
        except Exception as e:
            logger.error(f"Failed to send message to {uid}: {e}")

# Main function
def main():
    application = Application.builder().token(token).build()

    # Command handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('profile', profile))
    application.add_handler(CommandHandler('roulette', roulette))
    application.add_handler(CommandHandler('slot', slot_machine))
    application.add_handler(CommandHandler('flip', flip))
    application.add_handler(CommandHandler('bet', bet))
    application.add_handler(CommandHandler('dart', dart))
    application.add_handler(CommandHandler('basketball', basketball))
    application.add_handler(CommandHandler('football', football))
    application.add_handler(CommandHandler('add', add_units))
    application.add_handler(CommandHandler('backup', backup))
    application.add_handler(CommandHandler('broadcast', broadcast))
    

    # Start polling
    application.run_polling()

if __name__ == '__main__':
    main()
