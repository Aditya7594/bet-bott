from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, CallbackContext, ChatMemberHandler, filters,ChatMemberHandler
from pymongo import MongoClient
import logging
from datetime import datetime, timedelta
from functools import wraps

# MongoDB connection setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
users_collection = db['users']
genshin_collection = db['genshin_users']
blacklist_collection = db['blacklist']

OWNER_IDS = [5667016949] 

# Fetch user data from database
def get_user_by_id(user_id):
    return users_collection.find_one({"user_id": user_id})

def save_user(user_data):
    users_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

# Fetch Genshin user data from the database
def get_genshin_user_by_id(user_id):
    return genshin_collection.find_one({"user_id": user_id})

def save_genshin_user(user_data):
    genshin_collection.update_one({"user_id": user_data["user_id"]}, {"$set": user_data}, upsert=True)

# Bank system - Store credits
async def store(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    try:
        amount = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /store <amount>")
        return

    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    if user_data['credits'] < amount:
        await update.message.reply_text(f"You don't have enough credits to store. Your balance is {user_data['credits']} credits.")
        return

    user_data['credits'] -= amount
    user_data['bank'] = user_data.get('bank', 0) + amount
    save_user(user_data)

    await update.message.reply_text(f"Successfully stored {amount} credits in your virtual bank. Your bank balance is now {user_data['bank']} credits.")

# Bank system - Withdraw credits
async def withdraw(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    try:
        amount = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /withdraw <amount>")
        return

    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    if user_data.get('bank', 0) < amount:
        await update.message.reply_text(f"You don't have enough funds in your bank. Your bank balance is {user_data.get('bank', 0)} credits.")
        return

    user_data['credits'] += amount
    user_data['bank'] -= amount
    save_user(user_data)

    await update.message.reply_text(f"Successfully withdrew {amount} credits from your virtual bank. Your current balance is {user_data['credits']} credits.")

# Show bank balance
async def bank(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text("You need to start the bot first by using /start.")
        return

    bank_balance = user_data.get('bank', 0)
    await update.message.reply_text(f"Your virtual bank balance is: {bank_balance} credits.")

async def add_credits(update: Update, context: CallbackContext) -> None:
    sender_id = update.effective_user.id

    if sender_id not in OWNER_IDS:
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return

    try:
        user_id = str(int(context.args[0]))
        amount = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /addcredits <user_id> <amount>")
        return

    user_data = get_user_by_id(user_id)
    if not user_data:
        await update.message.reply_text(f"User with ID {user_id} not found.")
        return

    user_data["credits"] = user_data.get("credits", 0) + amount
    save_user(user_data)

    await update.message.reply_text(f"✅ Added {amount} credits to user {user_id}. New balance: {user_data['credits']} credits.")


# Add user to blacklist
async def blacklist(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /blacklist <user_id>")
        return

    blacklist_collection.update_one({"user_id": target_id}, {"$set": {"user_id": target_id}}, upsert=True)
    await update.message.reply_text(f"User ID {target_id} has been blacklisted.")

# Remove user from blacklist
async def unblacklist(update: Update, context: CallbackContext) -> None:
    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: /unblacklist <user_id>")
        return

    result = blacklist_collection.delete_one({"user_id": target_id})
    if result.deleted_count > 0:
        await update.message.reply_text(f"User ID {target_id} has been removed from the blacklist.")
    else:
        await update.message.reply_text(f"User ID {target_id} was not found in the blacklist.")

# Auto-ban blacklisted users when they join
def is_blacklisted(user_id):
    return blacklist_collection.find_one({"user_id": user_id}) is not None

async def auto_ban(update: Update, context: CallbackContext):
    chat_member = update.chat_member
    user = chat_member.new_chat_member.user
    if chat_member.difference().get("status") == ("left", "member") or chat_member.new_chat_member.status != "member":
        return

    if is_blacklisted(user.id):
        try:
            await context.bot.ban_chat_member(chat_id=update.effective_chat.id, user_id=user.id)
            print(f"Banned blacklisted user {user.full_name} (ID: {user.id})")
        except Exception as e:
            print(f"Failed to ban user {user.id}: {e}")
# Scan group and auto-ban all blacklisted users
async def scan_blacklist(update: Update, context: CallbackContext):
    chat = update.effective_chat

    if not update.effective_user or not update.effective_user.id:
        return

    try:
        members = await context.bot.get_chat_administrators(chat.id)
        if not any(admin.user.id == update.effective_user.id for admin in members):
            await update.message.reply_text("Only admins can run this command.")
            return
    except Exception:
        await update.message.reply_text("Failed to fetch admins.")
        return

    banned = []
    try:
        # Use get_chat_members_count to estimate number of members and handle a workaround for fetch
        total_members = await context.bot.get_chat_members_count(chat.id)
        
        # You can add logic here if you have manually tracked member IDs
        for i in range(total_members):
            # Use get_chat_member to check each user (but this might hit limits)
            try:
                member = await context.bot.get_chat_member(chat.id, i)
                if is_blacklisted(member.user.id):
                    await context.bot.ban_chat_member(chat.id, member.user.id)
                    banned.append(member.user.id)
            except Exception as e:
                print(f"Failed to process member {i}: {e}")
    except Exception as e:
        await update.message.reply_text(f"Failed to scan members: {e}")
        return

    await update.message.reply_text(f"Scan complete. Banned users: {', '.join(map(str, banned)) if banned else 'None'}")


# Register command handlers
def get_bank_handlers():
    return [
        CommandHandler("store", store),
        CommandHandler("withdraw", withdraw),
        CommandHandler("bank", bank),
        CommandHandler("blacklist", blacklist),
        CommandHandler("unblacklist", unblacklist),
        ChatMemberHandler(auto_ban, ChatMemberHandler.CHAT_MEMBER)
    ]
