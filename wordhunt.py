from __future__ import annotations

import os
import random
import asyncio
from collections import defaultdict
from typing import Dict, Any
import nltk
from nltk.corpus import words

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes,
    filters
)
from pymongo import MongoClient

# Download nltk word corpus if not already present
try:
    nltk.data.find('corpora/words')
except LookupError:
    nltk.download('words')

# MongoDB setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
wh_scores = db["wordhunt_scores"]

# Game constants
MAX_TRIALS = 25

# Load word list from nltk
wordhunt_word_list = [word.upper() for word in words.words() if len(word) >= 3 and word.isalpha()]

# Game state storage
wordhunt_games = {}
activity_timers = {}  # Store activity timers for wordhunt

class WordHuntGame:
    """Class to represent a WordHunt game"""
    
    def __init__(self):
        self.line_list = wordhunt_word_list.copy()
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
        letter_counts = defaultdict(int)
        for letter in self.letter_row:
            letter_counts[letter.lower()] += 1
            
        for word in self.line_list:
            word_lower = word.lower()
            temp_counts = letter_counts.copy()
            valid = True
            
            for letter in word_lower:
                if temp_counts[letter] <= 0:
                    valid = False
                    break
                temp_counts[letter] -= 1
                
            if valid:
                self.score_words.append(word)

    def can_spell(self, word):
        """Check if a word can be spelled with the current letters"""
        word_letters = list(word.lower())
        available_letters = [letter.lower() for letter in self.letter_row]
        
        letter_counts = defaultdict(int)
        for letter in available_letters:
            letter_counts[letter] += 1
            
        for letter in word_letters:
            if letter_counts[letter] <= 0:
                return False
            letter_counts[letter] -= 1
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
            
            if len(self.score_words) < 35:
                return False
                
            self.top_score_words = sorted(self.score_words, key=len, reverse=True)[:5]
            return True
        return False

    # ... (rest of the WordHuntGame class remains the same)

async def handle_guess(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process a word submission for WordHunt"""
    chat_id = update.effective_chat.id
    if chat_id not in wordhunt_games or not wordhunt_games[chat_id].ongoing_game:
        return

    guess = update.message.text.strip().lower()
    player_name = update.effective_user.first_name or update.effective_user.username
    
    if len(guess) < 3:
        return
        
    game = wordhunt_games[chat_id]
    
    # Check if word has already been found
    if guess in game.found_words:
        await update.message.reply_html(f"<b>{guess}</b> has already been found!")
        return
    
    # Check if word is valid English word and can be formed from letters
    if game.can_spell(guess) and guess.upper() in wordhunt_word_list:
        game.update_activity_time()
        score = len(guess) * len(guess)
        
        # Update game state
        if guess.upper() in game.score_words:
            game.score_words.remove(guess.upper())
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

# ... (rest of the code remains the same)

async def end_hunt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    
    handlers = [
        CommandHandler("wordhunt", wordhunt),
        CommandHandler("endhunt", end_hunt),
        CommandHandler("whleaderboard", whleaderboard),
        CommandHandler("whglobal", whglobal),
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
            handle_guess
        )
    ]
    
    return handlers
