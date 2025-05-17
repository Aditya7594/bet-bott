from __future__ import annotations

import random
import logging
import asyncio
from collections import defaultdict
from functools import lru_cache, wraps
from typing import Dict, List, Optional
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
mines_games = defaultdict(dict)

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
async def mines(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle mines command with throttling."""
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
    mines_games[user_id] = {
        'bet_amount': 100,
        'mines': random.sample(range(25), 5),
        'revealed': set(),
        'multiplier': 1.0
    }

    # Create keyboard
    keyboard = []
    for i in range(0, 25, 5):
        row = []
        for j in range(5):
            button = InlineKeyboardButton("?", callback_data=f"mines_{i+j}")
            row.append(button)
        keyboard.append(row)
    
    # Add control buttons
    keyboard.append([
        InlineKeyboardButton("Cash Out", callback_data="mines_cashout"),
        InlineKeyboardButton("New Game", callback_data="mines_new")
    ])

    await update.message.reply_text(
        f"💎 Mines Game\n\n"
        f"Bet: {mines_games[user_id]['bet_amount']} credits\n"
        f"Multiplier: {mines_games[user_id]['multiplier']}x\n\n"
        f"Click on a tile to reveal it!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_mines_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle mines game callbacks with async optimization."""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    if user_id not in mines_games:
        await query.edit_message_text("Game expired. Use /mines to start a new game.")
        return

    game = mines_games[user_id]
    action = query.data.split('_')[1]

    if action == "cashout":
        # Calculate winnings
        winnings = int(game['bet_amount'] * game['multiplier'])
        
        # Update user credits asynchronously
        if user_collection:
            await asyncio.to_thread(
                user_collection.update_one,
                {"user_id": user_id},
                {"$inc": {"credits": winnings}}
            )

        await query.edit_message_text(
            f"🎉 You won {winnings} credits!\n"
            f"Multiplier: {game['multiplier']}x"
        )
        del mines_games[user_id]
        return

    if action == "new":
        await mines(update, context)
        return

    # Handle tile reveal
    tile = int(action)
    if tile in game['revealed']:
        return

    if tile in game['mines']:
        # Game over - hit a mine
        await query.edit_message_text(
            f"💥 BOOM! You hit a mine!\n"
            f"Lost: {game['bet_amount']} credits"
        )
        del mines_games[user_id]
        return

    # Reveal tile and update multiplier
    game['revealed'].add(tile)
    game['multiplier'] += 0.1

    # Update keyboard
    keyboard = []
    for i in range(0, 25, 5):
        row = []
        for j in range(5):
            tile_num = i + j
            if tile_num in game['revealed']:
                button = InlineKeyboardButton("✅", callback_data=f"mines_{tile_num}")
            else:
                button = InlineKeyboardButton("?", callback_data=f"mines_{tile_num}")
            row.append(button)
        keyboard.append(row)

    # Add control buttons
    keyboard.append([
        InlineKeyboardButton("Cash Out", callback_data="mines_cashout"),
        InlineKeyboardButton("New Game", callback_data="mines_new")
    ])

    await query.edit_message_text(
        f"💎 Mines Game\n\n"
        f"Bet: {game['bet_amount']} credits\n"
        f"Multiplier: {game['multiplier']}x\n\n"
        f"Click on a tile to reveal it!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def register_handlers(application: Application) -> None:
    """Register handlers with throttling."""
    # Add throttling handler
    application.add_handler(ThrottlingHandler(THROTTLE_RATE, THROTTLE_BURST))

    # Register command handlers with throttling
    application.add_handler(CommandHandler("mines", throttle_command()(mines)))
    
    # Register callback query handler
    application.add_handler(CallbackQueryHandler(handle_mines_callback, pattern="^mines_"))
    
    logger.info("Mines game handlers registered successfully")
