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
    try:
        with open(os.path.join(THIS_FOLDER, 'word_list.txt'), "r") as f:
            WORD_LIST.extend(line.strip().lower() for line in f if line.strip())
        with open(os.path.join(THIS_FOLDER, 'cricket_word_list.txt'), "r") as f:
            CRICKET_WORD_LIST.extend(line.strip().lower() for line in f if line.strip())
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

async def start_wordle(update: Update, context: ContextTypes.DEFAULT_TYPE, word_list: list[str], mode: str):
    if not word_list:
        await update.message.reply_text("Word list is missing.")
        return
    if context.chat_data.get('game_active'):
        await update.message.reply_text("Game already in progress. Use /end to stop.")
        return

    word = random.choice(word_list)
    context.chat_data.update({
        'game_active': True,
        'solution': word,
        'attempts': 0,
        'mode': mode,
        'guesses': []
    })

    context.chat_data['inactivity_task'] = asyncio.create_task(
        timeout_inactive(update, context)
    )

    await update.message.reply_text(f"{mode.upper()} Wordle started! Guess the word. You have {MAX_TRIALS} trials.")

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

async def end_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stop_timeout(context)
    if context.chat_data.get('game_active'):
        solution = context.chat_data.get('solution', '').upper()
        context.chat_data.clear()
        await update.message.reply_text(f"Game ended. The word was: {solution}")
    else:
        await update.message.reply_text("No active game to end.")

async def handle_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.chat_data.get('game_active'):
        return

    user = update.effective_user
    chat_id = update.effective_chat.id
    guess = update.message.text.strip().lower()
    solution = context.chat_data['solution']
    word_list = CRICKET_WORD_LIST if context.chat_data['mode'] == 'cricketwordle' else WORD_LIST

    await stop_timeout(context)
    context.chat_data['inactivity_task'] = asyncio.create_task(
        timeout_inactive(update, context)
    )

    if guess in [g.lower().split()[-1] for g in context.chat_data['guesses']]:
        await update.message.reply_text("You already tried that word!")
        return

    if len(guess) != len(solution):
        await update.message.reply_text(f"Word must be {len(solution)} letters.")
        return
    if guess not in word_list:
        await update.message.reply_text("Word not in list.")
        return

    context.chat_data['attempts'] += 1
    result = verify_solution(guess, solution)
    result_blocks = "".join(BLOCKS[r] for r in result)

    context.chat_data['guesses'].append(f"{result_blocks}   {guess.upper()}")
    adjust_score(user.id, user.first_name, chat_id, 1)

    board_display = "\n".join(context.chat_data['guesses'])

    if all(r == CORRECT for r in result):
        board_display += f"\n🎉 You won in {context.chat_data['attempts']} tries!"
        adjust_score(user.id, user.first_name, chat_id, 20)
        await stop_timeout(context)
        context.chat_data.clear()
    elif context.chat_data['attempts'] >= MAX_TRIALS:
        board_display += f"\n❌ Out of tries ({MAX_TRIALS}). The word was: {solution.upper()}"
        await stop_timeout(context)
        context.chat_data.clear()

    await update.message.reply_text(board_display)

async def group_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def global_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top = list(wordle_col.find().sort("points", -1).limit(10))
    msg = "🌍 Global Word Leaderboard:\n\n"
    for i, user in enumerate(top, 1):
        msg += f"{i}. {user.get('name', 'Anonymous')} - {user.get('points', 0)} pts\n"
    await update.message.reply_text(msg.strip() or "No leaderboard data.")

def get_wordle_handlers() -> list:
    load_word_list()

    return [
        CommandHandler("wordle", lambda update, context: start_wordle(update, context, WORD_LIST, "wordle")),
        CommandHandler("cricketwordle", lambda update, context: start_wordle(update, context, CRICKET_WORD_LIST, "cricketwordle")),
        CommandHandler("leaderboard", global_leaderboard),
        CommandHandler("wordleaderboard", group_leaderboard),
        CommandHandler("wordglobal", global_leaderboard),
        CommandHandler("end", end_game),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_guess),
    ]
