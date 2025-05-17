from __future__ import annotations

import os
import random
import logging
from collections import Counter
from typing import Sequence, Optional, Dict, Any

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes,
    filters
)
from pymongo import MongoClient

# Logging setup - reduce logging level to WARNING to minimize CPU usage
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# MongoDB setup - create connection once
try:
    client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot', serverSelectionTimeoutMS=5000)
    db = client['telegram_bot']
    wordle_col = db["leaderboard"]
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    wordle_col = None

# Game constants
ABSENT, PRESENT, CORRECT = 0, 1, 2
BLOCKS = {0: "🟥", 1: "🟨", 2: "🟩"}
MAX_TRIALS = 20

# Load word lists - load once at module level
WORD_LIST, CRICKET_WORD_LIST = [], []
THIS_FOLDER = os.path.dirname(os.path.abspath(__file__))

# Game state storage
wordle_games: Dict[int, Dict[str, Any]] = {}

def load_word_list():
    global WORD_LIST, CRICKET_WORD_LIST
    if not WORD_LIST or not CRICKET_WORD_LIST:
        try:
            with open(os.path.join(THIS_FOLDER, 'word_list.txt'), "r") as f:
                WORD_LIST = [line.strip().lower() for line in f if line.strip()]
            with open(os.path.join(THIS_FOLDER, 'cricket_word_list.txt'), "r") as f:
                CRICKET_WORD_LIST = [line.strip().lower() for line in f if line.strip()]
        except Exception as e:
            logger.error(f"Failed to load word lists: {e}")

# Load word lists at module level
load_word_list()

def verify_solution(guess: str, solution: str) -> Sequence[int]:
    result = [-1] * len(solution)
    counter = Counter(solution)
    for i, l in enumerate(solution):
        if guess[i] == l:
            result[i] = CORRECT
            counter[l] -= 1
    for i, l in enumerate(guess):
        if result[i] == -1:
            if counter.get(l, 0) > 0:
                result[i] = PRESENT
                counter[l] -= 1
            else:
                result[i] = ABSENT
    return result

def adjust_score(user_id, name, chat_id, points):
    if not wordle_col:
        return
        
    try:
        user = wordle_col.find_one({"_id": user_id})
        if not user:
            wordle_col.insert_one({
                "_id": user_id,
                "name": name,
                "points": points,
                "group_points": {str(chat_id): points}
            })
        else:
            new_total = user.get("points", 0) + points
            group_points = user.get("group_points", {})
            group_points[str(chat_id)] = group_points.get(str(chat_id), 0) + points
            wordle_col.update_one(
                {"_id": user_id},
                {"$set": {"points": new_total, "group_points": group_points, "name": name}}
            )
    except Exception as e:
        logger.error(f"Failed to adjust score: {e}")

async def wordle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not WORD_LIST:
        await update.message.reply_text("Word list is missing.")
        return
        
    chat_id = update.effective_chat.id
    if chat_id in wordle_games:
        await update.message.reply_text("Game already in progress.")
        return

    word = get_random_wordle_word()
    
    wordle_games[chat_id] = {
        'game_active': True,
        'solution': word,
        'attempts': 0,
        'mode': "wordle",
        'guesses': []
    }

    await update.message.reply_text(f"WORDLE started! Guess the {len(word)}-letter word. You have {MAX_TRIALS} trials.")

async def cricketwordle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not CRICKET_WORD_LIST:
        await update.message.reply_text("Cricket word list is missing.")
        return
        
    chat_id = update.effective_chat.id
    if chat_id in wordle_games:
        await update.message.reply_text("Game already in progress.")
        return

    word = random.choice(CRICKET_WORD_LIST)
    
    wordle_games[chat_id] = {
        'game_active': True,
        'solution': word,
        'attempts': 0,
        'mode': "cricketwordle",
        'guesses': []
    }

    await update.message.reply_text(f"CRICKETWORDLE started! Guess the {len(word)}-letter cricket-related word. You have {MAX_TRIALS} trials.")

async def handle_guess(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if chat_id not in wordle_games:
        return

    game = wordle_games[chat_id]
    user = update.effective_user
    guess = update.message.text.strip().lower()
    solution = game['solution']
    
    word_list = CRICKET_WORD_LIST if game['mode'] == 'cricketwordle' else WORD_LIST

    previous_guess_words = [entry.split()[-1].lower() for entry in game['guesses']]
    if guess in previous_guess_words:
        await update.message.reply_text("You already tried that word!")
        return

    if len(guess) != len(solution):
        await update.message.reply_text(f"Word must be {len(solution)} letters.")
        return
    
    if word_list and guess not in word_list:
        await update.message.reply_text("Word not in list.")
        return

    game['attempts'] += 1
    result = verify_solution(guess, solution)
    result_blocks = "".join(BLOCKS[r] for r in result)

    game['guesses'].append(f"{result_blocks}   {guess.upper()}")
    adjust_score(user.id, user.first_name, chat_id, 1)

    board_display = "\n".join(game['guesses'])

    if all(r == CORRECT for r in result):
        board_display += f"\n🎉 You won in {game['attempts']} tries!"
        adjust_score(user.id, user.first_name, chat_id, 20)
        del wordle_games[chat_id]
    elif game['attempts'] >= MAX_TRIALS:
        board_display += f"\n❌ Out of tries ({MAX_TRIALS}). The word was: {solution.upper()}"
        del wordle_games[chat_id]

    await update.message.reply_text(board_display)

async def wordleaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not wordle_col:
        await update.message.reply_text("Leaderboard is currently unavailable.")
        return
        
    try:
        chat_id = str(update.effective_chat.id)
        pipeline = [
            {"$project": {"name": {"$ifNull": ["$name", "Anonymous"]}, "points": {"$ifNull": [f"$group_points.{chat_id}", 0]}}}
        ]
        top = list(wordle_col.aggregate(pipeline))
        msg = "🏅 Group Word Leaderboard:\n\n"
        for i, user in enumerate(top, 1):
            msg += f"{i}. {user['name']} - {user.get('points', 0)} pts\n"
        await update.message.reply_text(msg.strip() or "No leaderboard data.")
    except Exception as e:
        logger.error(f"Failed to get leaderboard: {e}")
        await update.message.reply_text("Failed to get leaderboard data.")

async def wordglobal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not wordle_col:
        await update.message.reply_text("Global leaderboard is currently unavailable.")
        return
        
    try:
        top = list(wordle_col.find().sort("points", -1))
        msg = "🌍 Global Word Leaderboard:\n\n"
        for i, user in enumerate(top, 1):
            msg += f"{i}. {user.get('name', 'Anonymous')} - {user.get('points', 0)} pts\n"
        await update.message.reply_text(msg.strip() or "No leaderboard data.")
    except Exception as e:
        logger.error(f"Failed to get global leaderboard: {e}")
        await update.message.reply_text("Failed to get global leaderboard data.")

def get_random_wordle_word():
    """Get a random word for Wordle game."""
    # Use 10 random letters from a-z
    letters = random.sample('abcdefghijklmnopqrstuvwxyz', 10)
    return ''.join(random.choices(letters, k=10))

def registers_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("wordle", wordle))
    application.add_handler(CommandHandler("cricketwordle", cricketwordle))
    application.add_handler(CommandHandler("wordleaderboard", wordleaderboard))
    application.add_handler(CommandHandler("wordglobal", wordglobal))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_guess))
