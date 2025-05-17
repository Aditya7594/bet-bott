from __future__ import annotations

import os
import random
import logging
import asyncio
from collections import Counter, defaultdict
from typing import Sequence, Optional, Dict, Any

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
wh_scores = db["wordhunt_scores"]

# Game state storage
wordhunt_games = {}
activity_timers = {}  # Store activity timers for wordhunt

# Load wordhunt word list
try:
    letter_list_location = os.path.join(os.path.dirname(os.path.abspath(__file__)), '8letters.txt')
    with open(letter_list_location, "r") as word_list:
        wordhunt_word_list = [line.rstrip('\n').lower() for line in word_list]
    logger.info(f"Loaded {len(wordhunt_word_list)} words for WordHunt")
except Exception as e:
    logger.error(f"Failed to load wordhunt word list: {e}")
    wordhunt_word_list = []

class WordHuntGame:
    """Class to represent a WordHunt game"""
    
    def __init__(self):
        global wordhunt_word_list
    
        self.line_list = [word for word in wordhunt_word_list if len(word) >= 3]
        self.ongoing_game = False
        self.letter_row = []
        self.score_words = []
        self.found_words = []
        self.player_scores = {}
        self.top_score_words = []
        self.player_words = {}
        self.last_activity_time = None

    def create_letter_row(self):
        vowels = ['a','e','i','o','u']
        non_vowels_common = ['b', 'c', 'd', 'f', 'g', 'h', 'k', 'l', 'm', 'n', 'p', 'r', 's', 't','w','y']
        non_vowels_rare = ['j', 'q', 'x', 'z','v']
        num_vowels = random.randint(2,3)
        self.letter_row = []
        for i in range(num_vowels):
            self.letter_row.append(random.choice(vowels))
        for j in range(7 - num_vowels):
            self.letter_row.append(random.choice(non_vowels_common))
        self.letter_row.append(random.choice(non_vowels_rare))
        random.shuffle(self.letter_row)

    async def create_score_words(self):
        """Find valid words that can be spelled with the letter row"""
        self.score_words = []
        for word in self.line_list:
            if self.can_spell(word):
                self.score_words.append(word)
        logger.info(f"Found {len(self.score_words)} valid words for current letter set")

    def can_spell(self, word):
        word_letters = list(word)
        available_letters = self.letter_row.copy()
        for letter in word_letters:
            if letter in available_letters:
                available_letters.remove(letter)
            else:
                return False
        return True

    async def start(self):
        """Start a new game with at least 35 possible words"""
        if not self.ongoing_game:
            self.ongoing_game = True
            self.last_activity_time = asyncio.get_event_loop().time()
            
            # Keep generating letter rows until we have enough valid words
            attempt_count = 0
            while len(self.score_words) < 35 and attempt_count < 10:
                self.create_letter_row()
                await self.create_score_words()
                attempt_count += 1
            
            self.top_score_words = sorted(self.score_words, key=len, reverse=True)[:5]
            return True
        return False

    def end_clear(self):
        self.letter_row = []
        self.score_words = []
        self.found_words = []
        self.player_scores = {}
        self.top_score_words = []
        self.player_words = {}
        self.last_activity_time = None

    def ongoing_game_false(self):
        self.ongoing_game = False

    def sort_player_words(self):
        for player in self.player_words:
            self.player_words[player] = sorted(self.player_words[player], key=len, reverse=True)

    def update_activity_time(self):
        self.last_activity_time = asyncio.get_event_loop().time()

async def update_wordhunt_score(group_id, player_name, score):
    """Update user score in MongoDB for WordHunt games"""
    try:
        wh_scores.update_one(
            {"group_id": group_id, "player_name": player_name},
            {"$inc": {"score": score}},
            upsert=True
        )
    except Exception as e:
        logger.error(f"Failed to update wordhunt score: {e}")

def upper_letters(letter_row):
    """Format letter row for display"""
    upper = ""
    for letter in letter_row:
        upper = upper + " " + letter.upper()
    return upper

async def wordhunt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a new WordHunt game"""
    global wordhunt_games
    global activity_timers
    
    chat_id = update.effective_chat.id
    
    # Check if there's an active WordHunt game
    if chat_id in wordhunt_games and wordhunt_games[chat_id].ongoing_game:
        # Check if force start is requested
        if context.args and context.args[0].lower() == 'force':
            # End the current game
            await end_wordhunt(update, context)
        else:
            await update.message.reply_text("A WordHunt game is already in progress. Use /wordhunt force to start a new game.")
            return
    
    await update.message.reply_html("Generating Letters")
    
    # Create new game instance
    if chat_id not in wordhunt_games:
        wordhunt_games[chat_id] = WordHuntGame()
    
    if not await wordhunt_games[chat_id].start():
        await update.message.reply_text("Failed to start game. Please try again.")
        return

    # Cancel any existing timer and start a new one
    if chat_id in activity_timers and activity_timers[chat_id] is not None:
        activity_timers[chat_id].schedule_removal()
    
    activity_timers[chat_id] = context.job_queue.run_repeating(
        check_activity, 5.0,
        chat_id=chat_id, data=update
    )
    
    await update.message.reply_html(upper_letters(wordhunt_games[chat_id].letter_row))

async def check_activity(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check if there has been any activity in WordHunt in the last 30 seconds"""
    job = context.job
    chat_id = job.chat_id
    update = job.data
    
    if chat_id not in wordhunt_games or not wordhunt_games[chat_id].ongoing_game:
        job.schedule_removal()
        return
    
    current_time = asyncio.get_event_loop().time()

    if current_time - wordhunt_games[chat_id].last_activity_time > 30:
        await end_wordhunt(update, context)
        job.schedule_removal()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle WordHunt words"""
    chat_id = update.effective_chat.id
    
    # Check if there's an active WordHunt game
    if chat_id in wordhunt_games and wordhunt_games[chat_id].ongoing_game:
        await scoring_wordhunt(update, context)

async def scoring_wordhunt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process a word submission for WordHunt"""
    chat_id = update.effective_chat.id
    if chat_id not in wordhunt_games or not wordhunt_games[chat_id].ongoing_game:
        return

    guess = update.message.text.lower().strip()
    player_name = update.effective_user.first_name or update.effective_user.username
    
    if len(guess) < 3:
        return
        
    game = wordhunt_games[chat_id]
    
    if guess in game.found_words:
        await update.message.reply_html(f"<b>{guess}</b> has already been found!")
        return
    
    if guess in game.score_words:
        game.update_activity_time()
        score = len(guess) * len(guess)
        
        # Update game state
        game.score_words.remove(guess)
        game.found_words.append(guess)
        
        if player_name not in game.player_scores:
            game.player_scores[player_name] = 0
        if player_name not in game.player_words:
            game.player_words[player_name] = []
            
        game.player_words[player_name].append(guess)
        game.player_scores[player_name] += score
        
        # Update database
        await update_wordhunt_score(chat_id, player_name, score)
        
        # Notify player
        notif = f"<i>{player_name}</i> found <b>{guess}</b> for {score} points!\n{upper_letters(game.letter_row)}"
        await update.message.reply_html(notif)
    else:
        await update.message.reply_html(f"<b>{guess}</b> is not a valid word!")

async def end_wordhunt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """End an active WordHunt game"""
    chat_id = update.effective_chat.id
    if chat_id not in wordhunt_games or not wordhunt_games[chat_id].ongoing_game:
        await update.message.reply_html("No active WordHunt game to end.")
        return
    
    wordhunt_games[chat_id].ongoing_game_false()
    await update.message.reply_html("<b>Game Ended!</b>")
    
    final_results = "🎉 SCORES: \n"
    for player, score in wordhunt_games[chat_id].player_scores.items():
        final_results = final_results + player + ": " + str(score) + "\n"
    if not bool(wordhunt_games[chat_id].player_scores): # player_scores dict is empty
        final_results = "No one played! \n"

    total_possible_words = len(wordhunt_games[chat_id].score_words) + len(wordhunt_games[chat_id].found_words)
    final_results += f"\n💡 BEST POSSIBLE WORDS ({total_possible_words} total): \n"
    for word in wordhunt_games[chat_id].top_score_words:
        final_results += word + "\n"
    
    wordhunt_games[chat_id].sort_player_words()
    final_results += "\n🔎 WORDS FOUND \n"
    for player in wordhunt_games[chat_id].player_words:
        final_results += f"<b>{player}({len(wordhunt_games[chat_id].player_words[player])})</b> \n"
        for word in wordhunt_games[chat_id].player_words[player]:
            final_results += word + " "
        final_results += "\n"
    
    await update.message.reply_html(final_results)
    wordhunt_games[chat_id].end_clear()

    global activity_timers
    if chat_id in activity_timers and activity_timers[chat_id] is not None:
        activity_timers[chat_id].schedule_removal()
        activity_timers[chat_id] = None

async def whleaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display WordHunt leaderboard for current group"""
    chat_id = update.effective_chat.id
    top_players = list(wh_scores.find({"group_id": chat_id}).sort("score", -1).limit(10))
    
    if not top_players:
        await update.message.reply_text("No leaderboard data found for this group.")
        return

    reply = "🏆 <b>WordHunt Group Leaderboard</b> 🏆\n"
    for idx, player in enumerate(top_players, 1):
        reply += f"{idx}. {player['player_name']} - {player['score']} pts\n"
    
    await update.message.reply_html(reply)

async def whglobal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display global WordHunt leaderboard"""
    pipeline = [
        {"$group": {"_id": "$player_name", "score": {"$sum": "$score"}}},
        {"$sort": {"score": -1}},
        {"$limit": 10}
    ]
    top_players = list(wh_scores.aggregate(pipeline))

    if not top_players:
        await update.message.reply_text("No global leaderboard data found.")
        return

    reply = "🌍 <b>WordHunt Global Leaderboard</b> 🌍\n"
    for idx, player in enumerate(top_players, 1):
        reply += f"{idx}. {player['_id']} - {player['score']} pts\n"

    await update.message.reply_html(reply)

def register_handlers(application: Application) -> list:
    """Register all WordHunt handlers with the application"""
    handlers = [
        CommandHandler("wordhunt", wordhunt),
        CommandHandler("end", end_wordhunt),
        CommandHandler("whleaderboard", whleaderboard),
        CommandHandler("whglobal", whglobal),
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
            handle_message
        )
    ]
    
    logger.info("WordHunt handlers registered successfully")
    return handlers
