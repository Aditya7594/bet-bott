from __future__ import annotations

import asyncio
import logging
from logging.handlers import RotatingFileHandler
import os
from collections import Counter
import random
import sys
import time
from typing import Sequence

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, CallbackQueryHandler, filters, JobQueue
from telegram.constants import ChatMemberStatus
from pymongo import MongoClient

# MongoDB Setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
user_collection = db["users"]
wordle_col = db["leaderboard"]
logger = logging.getLogger(__name__)

# Constants
ABSENT = 0
PRESENT = 1
CORRECT = 2
MAX_TRIALS = 30
BLOCKS = {0: "🟥", 1: "🟨", 2: "🟩"} 

WORD_LIST = []
CRICKET_WORD_LIST = []

THIS_FOLDER = os.path.dirname(os.path.abspath(__file__))

def load_word_lists():
        word_list_path = os.path.join(THIS_FOLDER, 'word_list.txt')
        with open(word_list_path, "r", encoding="utf-8") as f:
            WORD_LIST.extend([line.strip().lower() for line in f if line.strip()])
        
        # Load cricket word list
        cricket_word_list_path = os.path.join(THIS_FOLDER, 'cricket_word_list.txt')
        with open(cricket_word_list_path, "r", encoding="utf-8") as f:
            CRICKET_WORD_LIST.extend([line.strip().lower() for line in f if line.strip()])

def setup_logger(level=logging.INFO):
    frm = (
        "%(levelname)-.3s [%(asctime)s] thr=%(thread)d %(name)s:%(lineno)d: %(message)s"
    )
    handler = RotatingFileHandler("bot.log", maxBytes=10 * 1024 * 1024, backupCount=5)
    handler.setFormatter(logging.Formatter(frm))
    handler.setLevel(level)
    logger.setLevel(level)
    logger.addHandler(handler)

def check_with_solution(guess: str, solution: str) -> Sequence[int]:
    result = [-1] * len(solution)
    counter = Counter(solution)
    for i, l in enumerate(solution):
        if guess[i] == l:
            result[i] = CORRECT
            counter[l] -= 1
    for i, l in enumerate(guess):
        if result[i] > -1:
            continue
        elif counter.get(l, 0) > 0:
            result[i] = PRESENT
            counter[l] -= 1
        else:
            result[i] = ABSENT
    return result

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if update.effective_chat.type == "private":
        return True
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        return chat_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False

async def is_owner(update: Update) -> bool:
    OWNER_ID = 1234567890  # Replace with your actual owner ID
    return update.effective_user.id == OWNER_ID

async def check_user_started_bot(user_id: int, bot) -> bool:
    try:
        await bot.get_chat(user_id)
        return True
    except Exception:
        return False

def update_leaderboard(chat_id: int, user_id: int, username: str, trials: int, won: bool):
    try:
        query = {"user_id": user_id}
        update = {
            "$set": {"username": username},
            "$inc": {"games": 1, "wins": int(won)},
            "$min": {"best_score": trials if won else MAX_TRIALS + 1},
        }
        wordle_col.update_one({"chat_id": chat_id, **query}, update, upsert=True)
        wordle_col.update_one({"chat_id": "global", **query}, update, upsert=True)
    except Exception as e:
        logger.error(f"Error updating leaderboard: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Welcome to the Wordle Bot! Use /wordle to start a classic game or /cricketwordle for a cricket-themed game."
    )

async def start_wordle_game(update: Update, context: ContextTypes.DEFAULT_TYPE, word_list: list[str], mode: str):
    chat_id = update.effective_chat.id
    
    if not word_list:
        await update.message.reply_text("Sorry, the word list is currently unavailable. Please try again later.")
        return
    
    if 'game_active' in context.chat_data and context.chat_data['game_active']:
        await update.message.reply_text("A game is already ongoing, reply with your guess.")
        return

    context.chat_data['solution'] = random.choice(word_list)
    context.chat_data['trials'] = 0
    context.chat_data['game_active'] = True
    context.chat_data['current_player'] = update.effective_user.id
    context.chat_data['current_player_name'] = update.effective_user.username or update.effective_user.first_name
    context.chat_data['mode'] = mode

    context.application.job_queue.run_once(
        check_inactivity, 
        30,
        chat_id=chat_id,
        user_id=update.effective_user.id
    )

    await update.message.reply_text(f"A new {mode.upper()} game starts, reply with your guess.")

async def check_inactivity(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    chat_data = context.application.chat_data.get(chat_id)
    
    if chat_data and chat_data.get('game_active') and chat_data.get('trials') == 0:
        solution = chat_data.get('solution')
        username = chat_data.get('current_player_name')
        trials = chat_data.get('trials')
        
        update_leaderboard(chat_id, chat_data.get('current_player'), username, trials, False)
        chat_data['game_active'] = False
        
        await context.bot.send_message(
            chat_id,
            f"Game stopped due to inactivity. The word was '{solution.upper()}'"
        )

async def wordle_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start_wordle_game(update, context, WORD_LIST, "wordle")

async def cricketwordle_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start_wordle_game(update, context, CRICKET_WORD_LIST, "cricketwordle")

async def stopgame_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context) and not await is_owner(update):
        await update.message.reply_text("Only admins or owner can stop the game.")
        return
    
    if 'game_active' not in context.chat_data or not context.chat_data['game_active']:
        await update.message.reply_text("No game is currently active.")
        return
    
    solution = context.chat_data['solution']
    user_id = context.chat_data['current_player']
    username = context.chat_data['current_player_name']
    trials = context.chat_data['trials']
    
    try:
        update_leaderboard(update.effective_chat.id, user_id, username, trials, False)
        context.chat_data['game_active'] = False
        await update.message.reply_text(f"Game stopped. The word was '{solution.upper()}'")
    except Exception as e:
        logger.error(f"Error in stopgame_command: {e}")
        await update.message.reply_text("An error occurred while stopping the game.")

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await display_leaderboard(update, group_only=True)

async def global_leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await display_leaderboard(update, group_only=False)

async def display_leaderboard(update: Update, group_only=True):
    try:
        cid = update.effective_chat.id
        query = {"chat_id": cid} if group_only else {"chat_id": "global"}
        top = list(wordle_col.find(query).sort([("wins", -1), ("best_score", 1)]).limit(10))
        
        if not top:
            await update.message.reply_text("No leaderboard data available yet.")
            return
        
        title = "🏆 WORDLE LEADERBOARD 🏆\n\n" if group_only else "🌎 GLOBAL WORDLE LEADERBOARD 🌎\n\n"
        message = title
        
        for i, user in enumerate(top, 1):
            win_rate = (user['wins'] / user['games']) * 100 if user['games'] else 0
            best = user['best_score'] if user['best_score'] <= MAX_TRIALS else "N/A"
            message += f"{i}. {user['username']}: {user['wins']}/{user['games']} wins ({win_rate:.1f}%), Best: {best}\n"
        
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error displaying leaderboard: {e}")
        await update.message.reply_text("An error occurred while retrieving the leaderboard.")

async def handle_start_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await start_command(update, context)
    await query.message.edit_text("You've started the bot! You can now play Wordle games.")

async def handle_guess(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if 'game_active' not in context.chat_data or not context.chat_data['game_active']:
        return

    user = update.effective_user
    guess = update.message.text.strip().lower()
    solution = context.chat_data['solution']
    word_list = CRICKET_WORD_LIST if context.chat_data.get('mode') == 'cricketwordle' else WORD_LIST

    if not await check_user_started_bot(user.id, context.bot):
        keyboard = [[InlineKeyboardButton("Start Bot", callback_data="start_bot")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "You need to start the bot first to play. Click below to start.", reply_markup=reply_markup
        )
        return

    if len(guess) != len(solution):
        await update.message.reply_text("The word must be 5 letters.")
        return
    elif guess not in word_list:
        await update.message.reply_text("Not in word list.")
        return

    try:
        context.chat_data['trials'] += 1
        trials = context.chat_data['trials']
        user_id = user.id
        username = user.username or user.first_name

        result = check_with_solution(guess, solution)
        colored_row = "".join(BLOCKS[r] for r in result)
        
        if 'guess_history' not in context.chat_data:
            context.chat_data['guess_history'] = []
        context.chat_data['guess_history'].append(colored_row + "   " + guess.upper())

        game_won = all(r == 2 for r in result)
        final_message = "\n".join(context.chat_data['guess_history'])

        if game_won:
            final_message += f"\n🎉 {username} guessed the word in {trials} tries!"
            context.chat_data['game_active'] = False
            update_leaderboard(update.effective_chat.id, user_id, username, trials, True)
        elif trials == MAX_TRIALS:
            final_message += f"\n❌ {username} failed! The word was '{solution.upper()}'"
            context.chat_data['game_active'] = False
            update_leaderboard(update.effective_chat.id, user_id, username, trials, False)

        await update.message.reply_text(final_message)
    except Exception as e:
        logger.error(f"Error processing guess: {e}")
        await update.message.reply_text("An error occurred while processing your guess.")

# Command handlers
wordle_handlers = [
    CommandHandler("start", start_command),
    CommandHandler("wordle", wordle_command),
    CommandHandler("cricketwordle", cricketwordle_command),
    CommandHandler("stopgame", stopgame_command),
    CommandHandler("wordleaderboard", leaderboard_command),
    CommandHandler("wordglobal", global_leaderboard_command),
    CallbackQueryHandler(handle_start_button, pattern="start_bot"),
    MessageHandler(filters.TEXT & ~filters.COMMAND, handle_guess)
]
