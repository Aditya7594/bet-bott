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
wordle_col = db["leaderboard"]
wh_scores = db["wordhunt_scores"]

# Game constants
ABSENT, PRESENT, CORRECT = 0, 1, 2
BLOCKS = {0: "🟥", 1: "🟨", 2: "🟩"}
MAX_TRIALS = 25  # Standard Wordle is 6 trials

# Load word lists
WORD_LIST, CRICKET_WORD_LIST = [], []
EASY_WORD_LIST = []  # First 17000 words (easier words)
THIS_FOLDER = os.path.dirname(os.path.abspath(__file__))

# Game state storage
wordle_games: Dict[int, Dict[str, Any]] = {}
wordhunt_games = {}
activity_timers = {}  # Store activity timers for wordhunt

###############################
# SHARED FUNCTIONS
###############################

def load_word_lists():
    global WORD_LIST, CRICKET_WORD_LIST, EASY_WORD_LIST
    if not WORD_LIST or not CRICKET_WORD_LIST:
        try:
            logger.info(f"Loading word lists from {THIS_FOLDER}")
            with open(os.path.join(THIS_FOLDER, 'word_list.txt'), "r") as f:
                all_words = [line.strip().lower() for line in f if line.strip()]
                WORD_LIST = all_words
                # Take only the first 17000 words (easier words)
                EASY_WORD_LIST = all_words[:17000]
                logger.info(f"Loaded {len(WORD_LIST)} total words and {len(EASY_WORD_LIST)} easy words")
                
            with open(os.path.join(THIS_FOLDER, 'cricket_word_list.txt'), "r") as f:
                CRICKET_WORD_LIST = [line.strip().lower() for line in f if line.strip()]
            logger.info(f"Loaded {len(CRICKET_WORD_LIST)} cricket words")
        except Exception as e:
            logger.error(f"Failed to load word lists: {e}")

# Load wordhunt word list
try:
    letter_list_location = os.path.join(THIS_FOLDER, '8letters.txt')
    with open(letter_list_location, "r") as word_list:
        wordhunt_word_list = [line.rstrip('\n').lower() for line in word_list]
    logger.info(f"Loaded {len(wordhunt_word_list)} words for WordHunt")
except Exception as e:
    logger.error(f"Failed to load wordhunt word list: {e}")
    wordhunt_word_list = []

###############################
# WORDLE FUNCTIONS
###############################

def verify_solution(guess: str, solution: str) -> Sequence[int]:
    """
    Verifies a wordle guess against the solution.
    Returns a list where each element indicates:
    - CORRECT (2): Letter is correct and in correct position
    - PRESENT (1): Letter is in the word but in wrong position
    - ABSENT (0): Letter is not in the word
    """
    if len(guess) != len(solution):
        return []
    
    result = [-1] * len(solution)
    counter = Counter(solution)
    
    # First pass: Mark correct positions
    for i, letter in enumerate(solution):
        if i < len(guess) and guess[i] == letter:
            result[i] = CORRECT
            counter[letter] -= 1
    
    # Second pass: Mark present letters
    for i, letter in enumerate(guess):
        if i < len(result) and result[i] == -1:
            if counter.get(letter, 0) > 0:
                result[i] = PRESENT
                counter[letter] -= 1
            else:
                result[i] = ABSENT
    
    return result

def adjust_score(user_id, name, chat_id, points):
    """Update user score in MongoDB for Wordle games"""
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

def get_random_wordle_word():
    """Get a random word from the EASY_WORD_LIST between 4-8 letters"""
    # Filter words that are between 4 and 8 letters long
    eligible_words = [word for word in EASY_WORD_LIST if 4 <= len(word) <= 8]
    return random.choice(eligible_words)

async def wordle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a new Wordle game"""
    load_word_lists()
    logger.info("Wordle command received")
    
    if not EASY_WORD_LIST:
        await update.message.reply_text("Word list is missing.")
        return
    
    chat_id = update.effective_chat.id
    if chat_id in wordle_games and wordle_games[chat_id]['game_active']:
        await update.message.reply_text("Wordle game already in progress.")
        return

    word = get_random_wordle_word()
    logger.info(f"Selected word: {word}")
    
    wordle_games[chat_id] = {
        'game_active': True,
        'solution': word,
        'attempts': 0,
        'mode': "wordle",
        'guesses': [],
        'last_message_id': None
    }

    await update.message.reply_text(f"WORDLE started! Guess the {len(word)}-letter word. You have {MAX_TRIALS} trials.")

async def cricketwordle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a new Cricket Wordle game"""
    load_word_lists()
    logger.info("Cricket Wordle command received")
    
    if not CRICKET_WORD_LIST:
        await update.message.reply_text("Cricket word list is missing.")
        return
    
    chat_id = update.effective_chat.id
    if chat_id in wordle_games and wordle_games[chat_id]['game_active']:
        await update.message.reply_text("Game already in progress.")
        return

    # Filter cricket words to match 4-8 length requirement
    eligible_cricket_words = [word for word in CRICKET_WORD_LIST if 4 <= len(word) <= 8]
    if not eligible_cricket_words:
        await update.message.reply_text("No suitable cricket words found.")
        return
        
    word = random.choice(eligible_cricket_words)
    logger.info(f"Selected cricket word: {word}")
    
    wordle_games[chat_id] = {
        'game_active': True,
        'solution': word,
        'attempts': 0,
        'mode': "cricketwordle",
        'guesses': [],
        'last_message_id': None
    }

    await update.message.reply_text(f"CRICKETWORDLE started! Guess the {len(word)}-letter cricket-related word. You have {MAX_TRIALS} trials.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle both Wordle guesses and WordHunt words"""
    chat_id = update.effective_chat.id
    message_text = update.message.text.strip().lower()
    
    # First check if there's an active Wordle game
    if chat_id in wordle_games and wordle_games[chat_id]['game_active']:
        await handle_wordle_guess(update, context)
    
    # Then check if there's an active WordHunt game
    elif chat_id in wordhunt_games and wordhunt_games[chat_id].ongoing_game:
        await scoring_wordhunt(update, context)

async def handle_wordle_guess(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process a guess for an active Wordle game"""
    chat_id = update.effective_chat.id
    if chat_id not in wordle_games or not wordle_games[chat_id]['game_active']:
        return

    game = wordle_games[chat_id]
    user = update.effective_user
    guess = update.message.text.strip().lower()
    solution = game['solution']
    
    logger.info(f"Processing wordle guess: {guess}, solution: {solution}")
    
    # Choose the appropriate word list for validating guesses
    # Note: We validate against the ENTIRE word list, not just the easy words
    word_list = CRICKET_WORD_LIST if game['mode'] == 'cricketwordle' else WORD_LIST

    # Check for duplicate guesses
    previous_guess_words = [entry.split()[-1].lower() for entry in game['guesses']]
    if guess in previous_guess_words:
        logger.info(f"Duplicate guess: {guess}")
        await update.message.reply_text("You already tried that word!")
        return

    # Check if guess has correct length
    if len(guess) != len(solution):
        logger.info(f"Wrong length: {len(guess)} vs {len(solution)}")
        await update.message.reply_text(f"Word must be {len(solution)} letters.")
        return
    
    # Check if guess is in the word list
    if word_list and guess not in word_list:
        logger.info(f"Word not in list: {guess}")
        await update.message.reply_text("Word not in list.")
        return

    # Process valid guess
    game['attempts'] += 1
    result = verify_solution(guess, solution)
    result_blocks = "".join(BLOCKS[r] for r in result)

    game['guesses'].append(f"{result_blocks}   {guess.upper()}")
    
    # Award points for attempt
    adjust_score(user.id, user.first_name, chat_id, 1)

    board_display = "\n".join(game['guesses'])

    # Check win condition
    if guess == solution:
        board_display += f"\n🎉 You won in {game['attempts']} tries!"
        # Award bonus points for winning
        points_award = MAX_TRIALS - game['attempts'] + 1
        adjust_score(user.id, user.first_name, chat_id, 10 + points_award)
        wordle_games[chat_id]['game_active'] = False
        logger.info("Game won!")
    elif game['attempts'] >= MAX_TRIALS:
        board_display += f"\n❌ Out of tries ({MAX_TRIALS}). The word was: {solution.upper()}"
        wordle_games[chat_id]['game_active'] = False
        logger.info("Game lost - out of tries")

    await update.message.reply_text(board_display)

async def wordleaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display Wordle leaderboard for current group"""
    chat_id = str(update.effective_chat.id)
    pipeline = [
        {"$project": {"name": {"$ifNull": ["$name", "Anonymous"]}, "points": {"$ifNull": [f"$group_points.{chat_id}", 0]}}},
        {"$match": {"points": {"$gt": 0}}},
        {"$sort": {"points": -1}},
        {"$limit": 10}
    ]
    top = list(wordle_col.aggregate(pipeline))
    msg = "🏅 Group Word Leaderboard:\n\n"
    for i, user in enumerate(top, 1):
        msg += f"{i}. {user['name']} - {user.get('points', 0)} pts\n"
    await update.message.reply_text(msg.strip() or "No leaderboard data.")

async def wordglobal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display global Wordle leaderboard"""
    top = list(wordle_col.find().sort("points", -1).limit(10))
    msg = "🌍 Global Word Leaderboard:\n\n"
    for i, user in enumerate(top, 1):
        msg += f"{i}. {user.get('name', 'Anonymous')} - {user.get('points', 0)} pts\n"
    await update.message.reply_text(msg.strip() or "No leaderboard data.")
    
async def end_wordle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """End an active Wordle game"""
    chat_id = update.effective_chat.id
    
    if chat_id not in wordle_games or not wordle_games[chat_id]['game_active']:
        await update.message.reply_text("No active Wordle game to end.")
        return
    
    solution = wordle_games[chat_id]['solution']
    wordle_games[chat_id]['game_active'] = False
    

    await update.message.reply_text(f"Game ended! The word was: {solution.upper()}")
    

    logger.info(f"Wordle game ended in chat {chat_id}. Solution was: {solution}")
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

    def create_score_words(self):
        self.score_words = []
        for word in self.line_list:
            if self.can_spell(word):
                self.score_words.append(word)

    def can_spell(self, word):
        word_letters = list(word)
        available_letters = self.letter_row.copy()
        for letter in word_letters:
            if letter in available_letters:
                available_letters.remove(letter)
            else:
                return False
        return True

    def start(self):
        if self.ongoing_game == False:
            self.ongoing_game = True
            self.last_activity_time = asyncio.get_event_loop().time()  # Set initial activity time
            while(len(self.score_words) < 35):
                self.create_letter_row()
                self.create_score_words()
            self.top_score_words = sorted(self.score_words, key=len, reverse=True)[0:5]

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

def update_wordhunt_score(group_id, player_name, score):
    """Update user score in MongoDB for WordHunt games"""
    wh_scores.update_one(
        {"group_id": group_id, "player_name": player_name},
        {"$inc": {"score": score}},
        upsert=True
    )

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
    

    if chat_id in wordle_games and wordle_games[chat_id]['game_active']:
        await update.message.reply_text("There's already an active Wordle game. Please finish it first.")
        return
    
    await update.message.reply_html("Generating Letters")
    if chat_id not in wordhunt_games:
        wordhunt_games[chat_id] = WordHuntGame()
    wordhunt_games[chat_id].start()

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

async def scoring_wordhunt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process a word submission for WordHunt"""
    chat_id = update.effective_chat.id
    if chat_id not in wordhunt_games or not wordhunt_games[chat_id].ongoing_game:
        return

    guess = update.message.text.lower()
    player_name = update.effective_user.first_name or update.effective_user.username

    if len(guess) < 3:

        return
        
    if guess in wordhunt_games[chat_id].found_words:
        await update.message.reply_html(f"<b>{guess}</b> has already been found!")
    elif guess in wordhunt_games[chat_id].score_words:
        wordhunt_games[chat_id].update_activity_time()
        score = len(guess) * len(guess)
        notif = f"<i>{player_name}</i> found <b>{guess}</b> for {score} points!\n{upper_letters(wordhunt_games[chat_id].letter_row)}"
        wordhunt_games[chat_id].score_words.remove(guess)
        wordhunt_games[chat_id].found_words.append(guess)

        if player_name not in wordhunt_games[chat_id].player_scores:
            wordhunt_games[chat_id].player_scores[player_name] = 0
        if player_name not in wordhunt_games[chat_id].player_words:
            wordhunt_games[chat_id].player_words[player_name] = []
        wordhunt_games[chat_id].player_words[player_name].append(guess)
        wordhunt_games[chat_id].player_scores[player_name] += score
        update_wordhunt_score(chat_id, player_name, score)

        await update.message.reply_html(notif)

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


def register_handlers(application: Application) -> None:
    """Register all command and message handlers"""

    load_word_lists()
    

    application.add_handler(CommandHandler("wordle", wordle))
    application.add_handler(CommandHandler("cricketwordle", cricketwordle))
    application.add_handler(CommandHandler("wordleaderboard", wordleaderboard))
    application.add_handler(CommandHandler("wordglobal", wordglobal))
    application.add_handler(CommandHandler("endwordle", end_wordle))
    
    application.add_handler(CommandHandler("wordhunt", wordhunt))
    application.add_handler(CommandHandler("end", end_wordhunt))
    application.add_handler(CommandHandler("whleaderboard", whleaderboard))
    application.add_handler(CommandHandler("whglobal", whglobal))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("All game handlers registered successfully")
