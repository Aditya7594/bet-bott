from __future__ import annotations

import random
import logging
import asyncio
from collections import defaultdict
from functools import lru_cache, wraps
from typing import Dict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
    filters, ThrottlingHandler
)
from pymongo import MongoClient
import time as time_module

# Reduce logging level to WARNING
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Command throttling settings
THROTTLE_RATE = 1.0  # seconds between commands
THROTTLE_BURST = 3   # number of commands allowed in burst

# Command throttling decorator
def throttle_command(rate=THROTTLE_RATE, burst=THROTTLE_BURST):
    def decorator(func):
        last_called = {}
        tokens = defaultdict(lambda: burst)
        last_update = {}

        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
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
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    user_collection = None

# Game state storage using defaultdict for better performance
limbo_games = defaultdict(dict)

# Cache for user data
@lru_cache(maxsize=1000)
def get_user_by_id_cached(user_id: str) -> Optional[Dict]:
    """Cached version of get_user_by_id to reduce database operations."""
    if not user_collection:
        return None
    return user_collection.find_one({"user_id": user_id})

# Cache for user names
@lru_cache(maxsize=1000)
def get_user_name_cached(user_id: str) -> str:
    """Cached version of get_user_name to reduce database operations."""
    user = get_user_by_id_cached(user_id)
    return user.get('first_name', 'Unknown') if user else 'Unknown'

@throttle_command()
async def limbo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle limbo command with throttling."""
    if not should_process_update(update):
        return

    user = update.effective_user
    user_id = str(user.id)
    
    # Get user data with caching
    user_data = get_user_by_id_cached(user_id)
    if not user_data:
        await update.message.reply_text("Please use /start first to register.")
        return

    # Check if user has enough credits
    if user_data.get('credits', 0) < 100:
        await update.message.reply_text("You need at least 100 credits to play.")
        return

    # Create game state
    limbo_games[user_id] = {
        'bet_amount': 100,
        'target_multiplier': 2.0,
        'result': None
    }

    # Create keyboard
    keyboard = [
        [
            InlineKeyboardButton("1.5x", callback_data="limbo_1.5"),
            InlineKeyboardButton("2.0x", callback_data="limbo_2.0"),
            InlineKeyboardButton("3.0x", callback_data="limbo_3.0")
        ],
        [
            InlineKeyboardButton("5.0x", callback_data="limbo_5.0"),
            InlineKeyboardButton("10.0x", callback_data="limbo_10.0"),
            InlineKeyboardButton("20.0x", callback_data="limbo_20.0")
        ],
        [InlineKeyboardButton("Play", callback_data="limbo_play")]
    ]

    await update.message.reply_text(
        f"🎲 Limbo Game\n\n"
        f"Bet: {limbo_games[user_id]['bet_amount']} credits\n"
        f"Target Multiplier: {limbo_games[user_id]['target_multiplier']}x\n\n"
        f"Select your target multiplier and click Play!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_limbo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle limbo game callbacks with async optimization."""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    if user_id not in limbo_games:
        await query.edit_message_text("Game expired. Use /limbo to start a new game.")
        return

    game = limbo_games[user_id]
    action = query.data.split('_')[1]

    if action == "play":
        # Generate random multiplier
        result = round(random.uniform(1.0, 20.0), 2)
        game['result'] = result

        # Calculate winnings
        if result >= game['target_multiplier']:
            winnings = int(game['bet_amount'] * game['target_multiplier'])
            message = f"🎉 You won {winnings} credits!\nMultiplier: {result}x"
            
            # Update user credits asynchronously
            if user_collection:
                await asyncio.to_thread(
                    user_collection.update_one,
                    {"user_id": user_id},
                    {"$inc": {"credits": winnings}}
                )
        else:
            message = f"💥 You lost {game['bet_amount']} credits!\nMultiplier: {result}x"

        await query.edit_message_text(message)
        del limbo_games[user_id]
        return

    # Handle multiplier selection
    try:
        multiplier = float(action)
        game['target_multiplier'] = multiplier
        
        # Update keyboard
        keyboard = [
            [
                InlineKeyboardButton("1.5x", callback_data="limbo_1.5"),
                InlineKeyboardButton("2.0x", callback_data="limbo_2.0"),
                InlineKeyboardButton("3.0x", callback_data="limbo_3.0")
            ],
            [
                InlineKeyboardButton("5.0x", callback_data="limbo_5.0"),
                InlineKeyboardButton("10.0x", callback_data="limbo_10.0"),
                InlineKeyboardButton("20.0x", callback_data="limbo_20.0")
            ],
            [InlineKeyboardButton("Play", callback_data="limbo_play")]
        ]

        await query.edit_message_text(
            f"🎲 Limbo Game\n\n"
            f"Bet: {game['bet_amount']} credits\n"
            f"Target Multiplier: {game['target_multiplier']}x\n\n"
            f"Select your target multiplier and click Play!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except ValueError:
        await query.answer("Invalid multiplier selected.")

def register_handlers(application: Application) -> None:
    """Register handlers with throttling."""
    # Add throttling handler
    application.add_handler(ThrottlingHandler(THROTTLE_RATE, THROTTLE_BURST))

    # Register command handlers with throttling
    application.add_handler(CommandHandler("limbo", throttle_command()(limbo)))
    
    # Register callback query handler
    application.add_handler(CallbackQueryHandler(handle_limbo_callback, pattern="^limbo_"))
    
    logger.info("Limbo game handlers registered successfully")
