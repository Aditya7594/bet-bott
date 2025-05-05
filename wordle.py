from __future__ import annotations

import os
import random
import logging
from collections import Counter
from typing import Sequence, Optional
import asyncio

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes,
    filters
)
from pymongo import MongoClient

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
wordle_col = db["leaderboard"]

# Game constants
ABSENT, PRESENT, CORRECT = 0, 1, 2
BLOCKS = {0: "🟥", 1: "🟨", 2: "🟩"}
MAX_TRIALS = 20
INACTIVITY_TIMEOUT = 30

# Load word lists
WORD_LIST, CRICKET_WORD_LIST = [], []
THIS_FOLDER = os.path.dirname(os.path.abspath(__file__))

def load_word_list():
    global WORD_LIST, CRICKET_WORD_LIST
    # Only load if lists are empty
    if not WORD_LIST or not CRICKET_WORD_LIST:
        try:
            logger.info(f"Loading word lists from {THIS_FOLDER}")
            with open(os.path.join(THIS_FOLDER, 'word_list.txt'), "r") as f:
                WORD_LIST = [line.strip().lower() for line in f if line.strip()]
            with open(os.path.join(THIS_FOLDER, 'cricket_word_list.txt'), "r") as f:
                CRICKET_WORD_LIST = [line.strip().lower() for line in f if line.strip()]
            logger.info(f"Loaded {len(WORD_LIST)} regular words and {len(CRICKET_WORD_LIST)} cricket words")
        except Exception as e:
            logger.error(f"Failed to load word lists: {e}")

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

async def timeout_inactive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(INACTIVITY_TIMEOUT)
    if context.chat_data.get('game_active'):
        solution = context.chat_data.get('solution', '').upper()
        context.chat_data.clear()
        await update.message.reply_text(f"Game ended due to inactivity. The word was: {solution}")

async def stop_timeout(context: ContextTypes.DEFAULT_TYPE):
    task = context.chat_data.get('inactivity_task')
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

async def wordle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    load_word_list()
    logger.info("Wordle command received")
    
    if not WORD_LIST:
        await update.message.reply_text("Word list is missing.")
        return
    if context.chat_data.get('game_active'):
        await update.message.reply_text("Game already in progress. Use /end to stop.")
        return

    word = random.choice(WORD_LIST)
    logger.info(f"Selected word: {word}")
    
    context.chat_data.update({
        'game_active': True,
        'solution': word,
        'attempts': 0,
        'mode': "wordle",
        'guesses': []
    })

    context.chat_data['inactivity_task'] = asyncio.create_task(
        timeout_inactive(update, context)
    )

    await update.message.reply_text(f"WORDLE started! Guess the {len(word)}-letter word. You have {MAX_TRIALS} trials.")

async def cricketwordle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    load_word_list()
    logger.info("Cricket Wordle command received")
    
    if not CRICKET_WORD_LIST:
        await update.message.reply_text("Cricket word list is missing.")
        return
    if context.chat_data.get('game_active'):
        await update.message.reply_text("Game already in progress. Use /end to stop.")
        return

    word = random.choice(CRICKET_WORD_LIST)
    logger.info(f"Selected cricket word: {word}")
    
    context.chat_data.update({
        'game_active': True,
        'solution': word,
        'attempts': 0,
        'mode': "cricketwordle",
        'guesses': []
    })

    context.chat_data['inactivity_task'] = asyncio.create_task(
        timeout_inactive(update, context)
    )

    await update.message.reply_text(f"CRICKETWORDLE started! Guess the {len(word)}-letter cricket-related word. You have {MAX_TRIALS} trials.")

async def end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await stop_timeout(context)
    if context.chat_data.get('game_active'):
        solution = context.chat_data.get('solution', '').upper()
        context.chat_data.clear()
        await update.message.reply_text(f"Game ended. The word was: {solution}")
    else:
        await update.message.reply_text("No active game to end.")

async def handle_guess(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Log every message received to understand what's going on
    logger.info(f"Message received: {update.message.text}")
    
    if not context.chat_data.get('game_active'):
        logger.info("No active game, ignoring message")
        return

    user = update.effective_user
    chat_id = update.effective_chat.id
    guess = update.message.text.strip().lower()
    solution = context.chat_data['solution']
    
    logger.info(f"Processing guess: {guess}, solution: {solution}")
    
    word_list = CRICKET_WORD_LIST if context.chat_data['mode'] == 'cricketwordle' else WORD_LIST

    await stop_timeout(context)
    context.chat_data['inactivity_task'] = asyncio.create_task(
        timeout_inactive(update, context)
    )

    # Simplify previous guess check - just check if the lowercase guess is in any previous guess
    previous_guesses = [g.lower() for g in context.chat_data.get('guesses', [])]
    if any(guess in g for g in previous_guesses):
        logger.info(f"Duplicate guess: {guess}")
        await update.message.reply_text("You already tried that word!")
        return

    if len(guess) != len(solution):
        logger.info(f"Wrong length: {len(guess)} vs {len(solution)}")
        await update.message.reply_text(f"Word must be {len(solution)} letters.")
        return
    
    # Check if word is in list
    if word_list and guess not in word_list:
        logger.info(f"Word not in list: {guess}")
        await update.message.reply_text("Word not in list.")
        return

    context.chat_data['attempts'] += 1
    result = verify_solution(guess, solution)
    result_blocks = "".join(BLOCKS[r] for r in result)

    context.chat_data['guesses'].append(f"{result_blocks}   {guess.upper()}")
    adjust_score(user.id, user.first_name, chat_id, 1)

    board_display = "\n".join(context.chat_data['guesses'])
    logger.info(f"Current board: {board_display}")

    if all(r == CORRECT for r in result):
        board_display += f"\n🎉 You won in {context.chat_data['attempts']} tries!"
        adjust_score(user.id, user.first_name, chat_id, 20)
        await stop_timeout(context)
        context.chat_data.clear()
        logger.info("Game won!")
    elif context.chat_data['attempts'] >= MAX_TRIALS:
        board_display += f"\n❌ Out of tries ({MAX_TRIALS}). The word was: {solution.upper()}"
        await stop_timeout(context)
        context.chat_data.clear()
        logger.info("Game lost - out of tries")

    await update.message.reply_text(board_display)

async def wordleaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    pipeline = [
        {"$project": {"name": {"$ifNull": ["$name", "Anonymous"]}, "points": {"$ifNull": [f"$group_points.{chat_id}", 0]}}},
        {"$sort": {"points": -1}},
        {"$limit": 10}
    ]
    top = list(wordle_col.aggregate(pipeline))
    msg = "🏅 Group Word Leaderboard:\n\n"
    for i, user in enumerate(top, 1):
        msg += f"{i}. {user['name']} - {user['points']} pts\n"
    await update.message.reply_text(msg.strip() or "No leaderboard data.")

async def wordglobal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    top = list(wordle_col.find().sort("points", -1).limit(10))
    msg = "🌍 Global Word Leaderboard:\n\n"
    for i, user in enumerate(top, 1):
        msg += f"{i}. {user.get('name', 'Anonymous')} - {user.get('points', 0)} pts\n"
    await update.message.reply_text(msg.strip() or "No leaderboard data.")

# Debug command to check word list
async def check_wordlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    load_word_list()
    regular_count = len(WORD_LIST)
    cricket_count = len(CRICKET_WORD_LIST)
    await update.message.reply_text(
        f"Word lists status:\n"
        f"Regular words: {regular_count}\n"
        f"Cricket words: {cricket_count}\n"
        f"Example regular words: {', '.join(random.sample(WORD_LIST, min(5, regular_count)))}\n"
        f"Example cricket words: {', '.join(random.sample(CRICKET_WORD_LIST, min(5, cricket_count)))}"
    )

def registers_handlers(application: Application) -> None:
    # Load word lists at startup
    load_word_list()

    # Register all handlers
    application.add_handler(CommandHandler("wordle", wordle))
    application.add_handler(CommandHandler("cricketwordle", cricketwordle))
    application.add_handler(CommandHandler("end", end))
    application.add_handler(CommandHandler("wordleaderboard", wordleaderboard))
    application.add_handler(CommandHandler("wordglobal", wordglobal))
    application.add_handler(CommandHandler("checkwordlist", check_wordlist))
    
    # Make sure this handler is registered LAST
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_guess))
    
    logger.info("Wordle handlers registered successfully")
