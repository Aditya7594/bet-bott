from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from telegram.constants import ParseMode
import random
import logging

# --- Setup Logging ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- Globals ---
games = {}
timers = {}

# --- Game Object ---
class GameObject:
    def __init__(self):
        self.line_list = self.load_words()
        self.ongoing_game = False
        self.letter_row = []
        self.score_words = []
        self.found_words = []
        self.player_scores = {}
        self.top_score_words = []
        self.player_words = {}

    def load_words(self):
        try:
            with open("8letters.txt") as f:
                return [line.strip().lower() for line in f if line.strip()]
        except Exception as e:
            print("Error loading word list:", e)
            return []

    def create_letter_row(self):
        vowels = ['a', 'e', 'i', 'o', 'u']
        non_vowels_common = ['b', 'c', 'd', 'f', 'g', 'h', 'k', 'l', 'm', 'n', 'p', 'r', 's', 't', 'w', 'y']
        non_vowels_rare = ['j', 'q', 'x', 'z', 'v']
        num_vowels = random.randint(2, 3)

        self.letter_row = random.sample(vowels, num_vowels)
        self.letter_row += random.choices(non_vowels_common, k=7 - num_vowels)
        self.letter_row += [random.choice(non_vowels_rare)]
        random.shuffle(self.letter_row)

    def can_spell(self, word):
        temp_letters = self.letter_row.copy()
        for letter in word:
            if letter in temp_letters:
                temp_letters.remove(letter)
            else:
                return False
        return True

    def create_score_words(self):
        # Allow ANY word that can be formed from the letters (not limited to exact length)
        self.score_words = [word for word in self.line_list if self.can_spell(word)]

    def start(self):
        if not self.ongoing_game:
            self.ongoing_game = True
            attempts = 0
            while len(self.score_words) < 125 and attempts < 100:
                self.create_letter_row()
                self.create_score_words()
                attempts += 1
            self.top_score_words = sorted(self.score_words, key=len, reverse=True)[:5]

    def end_clear(self):
        self.letter_row = []
        self.score_words = []
        self.found_words = []
        self.player_scores = {}
        self.top_score_words = []
        self.player_words = {}

    def sort_player_words(self):
        for player in self.player_words:
            self.player_words[player] = sorted(self.player_words[player], key=len, reverse=True)

# --- Utilities ---
def upper_letters(letters):
    return ' '.join(letter.upper() for letter in letters)

# --- Command Handlers ---
async def wordhunt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # 🔒 Prevent starting if game is already running
    if chat_id in games and games[chat_id].ongoing_game:
        await update.message.reply_text("⛔ A game is already in progress. Please wait for it to finish.")
        return

    games[chat_id] = GameObject()
    game = games[chat_id]
    game.start()

    # ⏱️ Increased game duration to 90 seconds
    timers[chat_id] = context.job_queue.run_once(end_game, 90, chat_id=chat_id)
    await context.bot.send_message(chat_id=chat_id, text="🧠 Generating Letters...")
    await context.bot.send_message(chat_id=chat_id, text=upper_letters(game.letter_row))

async def scoring(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in games or not games[chat_id].ongoing_game:
        return

    guess = update.message.text.lower()
    username = update.effective_user.username or f"User_{update.effective_user.id}"
    game = games[chat_id]

    if guess in game.found_words:
        await update.message.reply_text(f"<b>{guess}</b> has already been found!", parse_mode=ParseMode.HTML)
        return

    if guess in game.score_words:
        score = len(guess) ** 2
        game.score_words.remove(guess)
        game.found_words.append(guess)

        game.player_scores.setdefault(username, 0)
        game.player_words.setdefault(username, [])
        game.player_scores[username] += score
        game.player_words[username].append(guess)

        await update.message.reply_text(
            f"<i>{username}</i> found <b>{guess}</b> for {score} points!\n{upper_letters(game.letter_row)}",
            parse_mode=ParseMode.HTML
        )

        # ✅ End early if all words are found
        if len(game.found_words) == len(game.score_words) + len(game.found_words):
            job = timers.get(chat_id)
            if job:
                job.schedule_removal()
            await end_game(context)

async def end_game(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id = job.chat_id

    if chat_id not in games or not games[chat_id].ongoing_game:
        return

    game = games[chat_id]
    game.ongoing_game = False
    game.sort_player_words()

    final_results = "<b>🎉 GAME ENDED!</b>\n\n<b>SCORES:</b>\n"
    if game.player_scores:
        for player, score in game.player_scores.items():
            final_results += f"{player}: {score}\n"
    else:
        final_results += "No one played!\n"

    final_results += "\n<b>💡 BEST POSSIBLE WORDS:</b>\n"
    final_results += '\n'.join(game.top_score_words) + "\n"

    final_results += "\n<b>🔎 WORDS FOUND:</b>\n"
    for player, words in game.player_words.items():
        final_results += f"<b>{player}</b> ({len(words)}):\n" + ' '.join(words) + "\n"

    await context.bot.send_message(chat_id=chat_id, text=final_results, parse_mode=ParseMode.HTML)

    game.end_clear()
    del games[chat_id]
    if chat_id in timers:
        del timers[chat_id]

async def manual_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    job = timers.get(chat_id)
    if job:
        job.schedule_removal()
    await end_game(context)

# --- Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Update {update} caused error {context.error}")

# --- Setup Function ---
def get_wordhunt_handlers():
    return [
        CommandHandler('wordhunt', wordhunt),
        CommandHandler('end', manual_end),
        MessageHandler(filters.TEXT & ~filters.COMMAND, scoring)
    ]
