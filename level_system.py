import json
import random
from datetime import datetime, timezone, timedelta, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from pymongo import MongoClient
import logging

# Setup logging
logger = logging.getLogger(__name__)

# MongoDB setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority')
db = client['telegram_bot']
users_collection = db['users']
chat_levels_collection = db['chat_levels']

# Load level rewards
with open('level_rewards.json', 'r') as f:
    LEVEL_REWARDS = json.load(f)

# Global variables for tracking
last_collect_times = {}
message_counts = {}

async def get_user_level(user_id: int, chat_id: int) -> int:
    """Get user's current level in a chat."""
    user_data = chat_levels_collection.find_one({
        'user_id': user_id,
        'chat_id': chat_id
    })
    return user_data['level'] if user_data else 1

async def get_user_messages(user_id: int, chat_id: int) -> int:
    """Get user's total messages in a chat."""
    user_data = chat_levels_collection.find_one({
        'user_id': user_id,
        'chat_id': chat_id
    })
    return user_data['messages'] if user_data else 0

async def update_user_level(user_id: int, chat_id: int, messages: int) -> tuple[int, int]:
    """Update user's level based on message count. Returns (old_level, new_level)."""
    user_data = chat_levels_collection.find_one({
        'user_id': user_id,
        'chat_id': chat_id
    })
    
    if not user_data:
        user_data = {
            'user_id': user_id,
            'chat_id': chat_id,
            'level': 1,
            'messages': 0,
            'last_level_up': datetime.now(timezone.utc)
        }
        chat_levels_collection.insert_one(user_data)
    
    old_level = user_data['level']
    new_level = old_level
    
    # Find the highest level the user qualifies for
    for level, required_messages in LEVEL_REWARDS.items():
        if messages >= required_messages:
            new_level = int(level)
    
    if new_level > old_level:
        user_data['level'] = new_level
        user_data['messages'] = messages
        user_data['last_level_up'] = datetime.now(timezone.utc)
        chat_levels_collection.update_one(
            {'user_id': user_id, 'chat_id': chat_id},
            {'$set': user_data},
            upsert=True
        )
    
    return old_level, new_level

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages for leveling system."""
    if not update.message or update.message.chat.type not in ['group', 'supergroup']:
        return
    logger.info(f"Level system: received message from user {update.message.from_user.id} in chat {update.message.chat.id}")
    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    
    # Initialize message count for this chat if not exists
    if chat_id not in message_counts:
        message_counts[chat_id] = {}
    
    # Increment message count for user
    if user_id not in message_counts[chat_id]:
        message_counts[chat_id][user_id] = 0
    message_counts[chat_id][user_id] += 1

    # Update message count in the database every message
    user_data = chat_levels_collection.find_one({'user_id': user_id, 'chat_id': chat_id})
    if not user_data:
        user_data = {
            'user_id': user_id,
            'chat_id': chat_id,
            'level': 1,
            'messages': 1,
            'last_level_up': datetime.now(timezone.utc)
        }
        chat_levels_collection.insert_one(user_data)
    else:
        chat_levels_collection.update_one(
            {'user_id': user_id, 'chat_id': chat_id},
            {'$inc': {'messages': 1}}
        )

    # Get total messages and update level
    total_messages = await get_user_messages(user_id, chat_id) + 1
    old_level, new_level = await update_user_level(user_id, chat_id, total_messages)
    
    # If user leveled up, send congratulations message
    if new_level > old_level:
        reward = new_level * 1000  # 1k credits per level
        user_data = users_collection.find_one({'user_id': user_id})
        if not user_data:
            user_data = {'user_id': user_id, 'credits': 0}
            users_collection.insert_one(user_data)
        
        users_collection.update_one(
            {'user_id': user_id},
            {'$inc': {'credits': reward}}
        )
        
        await update.message.reply_text(
            f"🎉 Congratulations {update.message.from_user.first_name}! "
            f"You've reached level {new_level}!\n"
            f"Reward: {reward:,} credits"
        )

async def collect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /collect command."""
    user_id = update.message.from_user.id
    current_time = datetime.now(timezone.utc)
    
    # Check cooldown
    if user_id in last_collect_times:
        time_diff = current_time - last_collect_times[user_id]
        if time_diff < timedelta(minutes=10):
            remaining = timedelta(minutes=10) - time_diff
            minutes = int(remaining.total_seconds() / 60)
            seconds = int(remaining.total_seconds() % 60)
            await update.message.reply_text(
                f"⏳ Please wait {minutes}m {seconds}s before collecting again!"
            )
            return
    
    # Generate random credits (0-500)
    credits = random.randint(0, 500)
    
    # Update user's credits
    user_data = users_collection.find_one({'user_id': user_id})
    if not user_data:
        user_data = {'user_id': user_id, 'credits': 0}
        users_collection.insert_one(user_data)
    
    users_collection.update_one(
        {'user_id': user_id},
        {'$inc': {'credits': credits}}
    )
    
    # Update last collect time
    last_collect_times[user_id] = current_time
    
    # Get updated user data to show correct balance
    updated_user_data = users_collection.find_one({'user_id': user_id})
    
    await update.message.reply_text(
        f"💰 You collected {credits:,} credits!\n"
        f"Total balance: {updated_user_data['credits']:,} credits"
    )

async def apply_daily_tax():
    """Apply daily tax to user credits."""
    users = users_collection.find({})
    total_tax_collected = 0
    
    for user in users:
        credits = user.get('credits', 0)
        if credits > 0:
            # Increased progressive tax rate
            if credits > 1_000_000:  # Over 1M credits
                tax_rate = 0.15  # 15% tax
            elif credits > 500_000:  # Over 500K credits
                tax_rate = 0.07  # 7% tax
            elif credits > 100_000:  # Over 100K credits
                tax_rate = 0.03  # 3% tax
            else:
                tax_rate = 0  # No tax for less than 100k
            
            tax_amount = int(credits * tax_rate)
            if tax_amount > 0:
                users_collection.update_one(
                    {'user_id': user['user_id']},
                    {'$inc': {'credits': -tax_amount}}
                )
                total_tax_collected += tax_amount
    
    # Update taxbox collection
    taxbox = db['taxbox']
    taxbox.update_one(
        {'_id': 'total_tax'},
        {'$inc': {'amount': total_tax_collected}},
        upsert=True
    )

async def taxbox_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /taxbox command to show total tax collected."""
    user_id = str(update.effective_user.id)
    
    # Check if user is owner
    if user_id != '5667016949':  # Replace with your owner ID
        await update.message.reply_text("❌ This command is only available to the bot owner.")
        return
    
    taxbox = db['taxbox']
    tax_data = taxbox.find_one({'_id': 'total_tax'})
    total_tax = tax_data['amount'] if tax_data else 0
    
    await update.message.reply_text(
        f"💰 <b>Tax Box</b>\n\n"
        f"Total tax collected: {total_tax:,} credits",
        parse_mode='HTML'
    )

def get_handlers():
    """Return command handlers for the level system."""
    from telegram.ext import CommandHandler
    return [
        ('collect', collect_command),
        ('taxbox', taxbox_command),
        ('chatlevel', chatlevel),
    ]

async def chatlevel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /chatlevel command."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    level = await get_user_level(user_id, chat_id)
    messages = await get_user_messages(user_id, chat_id)
    next_level = level + 1
    next_level_messages = LEVEL_REWARDS.get(str(next_level), 0)
    
    await update.message.reply_text(
        f"📊 <b>Level Info</b>\n\n"
        f"👤 User: {update.effective_user.first_name}\n"
        f"📈 Level: {level}\n"
        f"💬 Messages: {messages:,}\n"
        f"🎯 Next Level: {next_level} ({next_level_messages:,} messages)\n"
        f"💰 Reward: {next_level * 1000:,} credits",
        parse_mode="HTML"
    )

def get_level_handlers():
    """Return all level system handlers."""
    return [
        CommandHandler("collect", collect_command),
        CommandHandler("chatlevel", chatlevel)
    ] 