from __future__ import annotations

import random
import asyncio
from collections import defaultdict
from functools import lru_cache, wraps
from typing import Dict, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
    filters
)
from pymongo import MongoClient
import time as time_module

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
    user_collection = None

# Game state storage using defaultdict for better performance
xox_games = defaultdict(dict)

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
async def xox(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle xox command with throttling."""
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
    game_id = str(random.randint(100000, 999999))
    xox_games[game_id] = {
        'host': user_id,
        'players': [user_id],
        'bet_amount': 100,
        'status': 'waiting',
        'current_turn': user_id,
        'board': [' ' for _ in range(9)],
        'last_action': time_module.time()
    }

    # Create keyboard
    keyboard = [
        [InlineKeyboardButton("Join Game", callback_data=f"xox_join_{game_id}")],
        [InlineKeyboardButton("Start Game", callback_data=f"xox_start_{game_id}")]
    ]

    message = await update.message.reply_text(
        f"⭕ XOX Game\n\n"
        f"Game ID: {game_id}\n"
        f"Host: {get_user_name_cached(user_id)}\n"
        f"Bet: {xox_games[game_id]['bet_amount']} credits\n"
        f"Players: 1/2\n\n"
        f"Waiting for opponent to join...",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_xox_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle xox game callbacks with async optimization."""
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    action, game_id = query.data.split('_')[1:3]

    if game_id not in xox_games:
        await query.edit_message_text("Game expired. Use /xox to start a new game.")
        return

    game = xox_games[game_id]

    if action == "join":
        if user_id in game['players']:
            await query.answer("You're already in this game!")
            return

        if len(game['players']) >= 2:
            await query.answer("Game is full!")
            return

        game['players'].append(user_id)
        
        # Update game message
        players_text = "\n".join([f"- {get_user_name_cached(pid)}" for pid in game['players']])
        keyboard = [
            [InlineKeyboardButton("Join Game", callback_data=f"xox_join_{game_id}")],
            [InlineKeyboardButton("Start Game", callback_data=f"xox_start_{game_id}")]
        ]

        await query.edit_message_text(
            f"⭕ XOX Game\n\n"
            f"Game ID: {game_id}\n"
            f"Host: {get_user_name_cached(game['host'])}\n"
            f"Bet: {game['bet_amount']} credits\n"
            f"Players ({len(game['players'])}/2):\n{players_text}\n\n"
            f"Waiting for opponent to join...",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == "start":
        if user_id != game['host']:
            await query.answer("Only the host can start the game!")
            return

        if len(game['players']) < 2:
            await query.answer("Need 2 players to start!")
            return

        game['status'] = 'playing'
        game['current_turn'] = game['players'][0]
        
        # Create game board
        keyboard = []
        for i in range(0, 9, 3):
            row = []
            for j in range(3):
                row.append(InlineKeyboardButton(" ", callback_data=f"xox_move_{game_id}_{i+j}"))
            keyboard.append(row)

        await query.edit_message_text(
            f"⭕ XOX Game\n\n"
            f"Game ID: {game_id}\n"
            f"Bet: {game['bet_amount']} credits\n"
            f"Players:\n"
            f"- {get_user_name_cached(game['players'][0])} (X)\n"
            f"- {get_user_name_cached(game['players'][1])} (O)\n\n"
            f"Current Turn: {get_user_name_cached(game['current_turn'])}\n"
            f"Make your move!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif action == "move":
        if user_id != game['current_turn']:
            await query.answer("It's not your turn!")
            return

        position = int(query.data.split('_')[3])
        if game['board'][position] != ' ':
            await query.answer("This position is already taken!")
            return

        # Make move
        symbol = 'X' if game['players'].index(user_id) == 0 else 'O'
        game['board'][position] = symbol

        # Check for winner
        winner = check_winner(game['board'])
        if winner:
            # Game won
            winnings = int(game['bet_amount'] * 2)
            message = f"🎉 {get_user_name_cached(user_id)} won {winnings} credits!"
            
            # Update user credits asynchronously
            if user_collection:
                await asyncio.to_thread(
                    user_collection.update_one,
                    {"user_id": user_id},
                    {"$inc": {"credits": winnings}}
                )
            
            await query.edit_message_text(message)
            del xox_games[game_id]
            return

        # Check for draw
        if ' ' not in game['board']:
            await query.edit_message_text("Game ended in a draw!")
            del xox_games[game_id]
            return

        # Switch turns
        next_player_index = (game['players'].index(user_id) + 1) % 2
        game['current_turn'] = game['players'][next_player_index]

        # Update board
        keyboard = []
        for i in range(0, 9, 3):
            row = []
            for j in range(3):
                row.append(InlineKeyboardButton(
                    game['board'][i+j],
                    callback_data=f"xox_move_{game_id}_{i+j}"
                ))
            keyboard.append(row)

        await query.edit_message_text(
            f"⭕ XOX Game\n\n"
            f"Game ID: {game_id}\n"
            f"Bet: {game['bet_amount']} credits\n"
            f"Players:\n"
            f"- {get_user_name_cached(game['players'][0])} (X)\n"
            f"- {get_user_name_cached(game['players'][1])} (O)\n\n"
            f"Current Turn: {get_user_name_cached(game['current_turn'])}\n"
            f"Make your move!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

def check_winner(board: List[str]) -> Optional[str]:
    """Check if there's a winner in the XOX game."""
    # Check rows
    for i in range(0, 9, 3):
        if board[i] == board[i+1] == board[i+2] != ' ':
            return board[i]

    # Check columns
    for i in range(3):
        if board[i] == board[i+3] == board[i+6] != ' ':
            return board[i]

    # Check diagonals
    if board[0] == board[4] == board[8] != ' ':
        return board[0]
    if board[2] == board[4] == board[6] != ' ':
        return board[2]

    return None

def get_xox_handlers():
    """Return list of handlers."""
    return [
        CommandHandler("xox", throttle_command()(xox)),
        CallbackQueryHandler(handle_xox_callback, pattern="^xox_")
    ]

async def handle_game_timeout(game_id: str, context: ContextTypes.DEFAULT_TYPE):
    """Handle game timeout."""
    if game_id not in xox_games:
        return
    
    game = xox_games[game_id]
    
    # Send timeout message
    await context.bot.send_message(
        chat_id=game['chat_id'],
        text="⏰ Game timed out due to inactivity!"
    )
    
    # Remove game
    del xox_games[game_id]
