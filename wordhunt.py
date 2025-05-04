from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, filters, CallbackContext
from telegram.constants import ParseMode


games = {}
timers = {}

class GameObject:
    
    def __init__(self):
        self.line_list = []
        self.ongoing_game = False
        self.letter_row = []
        self.score_words = []
        self.found_words = []
        self.player_scores = {}
        self.top_score_words = []
        self.player_words = {}

    def create_letter_row(self):
        vowels = ['a','e','i','o','u']
        non_vowels_common = ['b', 'c', 'd', 'f', 'g', 'h', 'k', 'l', 'm', 'n', 'p', 'r', 's', 't','w','y']
        non_vowels_rare = ['j', 'q', 'x', 'z','v']
        num_vowels = random.randint(2,3)
        self.letter_row = []
        for _ in range(num_vowels):
            self.letter_row.append(random.choice(vowels))
        for _ in range(7 - num_vowels):
            self.letter_row.append(random.choice(non_vowels_common))
        self.letter_row.append(random.choice(non_vowels_rare))
        random.shuffle(self.letter_row)

    def create_score_words(self):
        self.score_words = []
        for word in self.line_list:
            if self.can_spell(word):
                self.score_words.append(word)

    def can_spell(self, word):
        word = list(word)
        for letter in self.letter_row:
            if letter in word:
                word.remove(letter)
            if not word:
                return True
        return False

    def start(self):
        if not self.ongoing_game:
            self.ongoing_game = True
            while len(self.score_words) < 125:
                self.create_letter_row()
                self.create_score_words()
            self.top_score_words = sorted(self.score_words, key=len, reverse=True)[:5]

    def end_clear(self):
        self.letter_row = []
        self.score_words = []
        self.found_words = []
        self.player_scores = {}
        self.top_score_words = []
        self.player_words = {}

    def ongoing_game_false(self):
        self.ongoing_game = False

    def sort_player_words(self):
        for player in self.player_words:
            self.player_words[player] = sorted(self.player_words[player], key=len, reverse=True)

def upper_letters(letter_row):
    return ' '.join(letter.upper() for letter in letter_row)

async def wordhunt(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    if chat_id not in games:
        games[chat_id] = GameObject()
    games[chat_id].start()

    # Timer control
    timers[chat_id] = context.job_queue.run_once(end_game, 45, chat_id=chat_id)
    
    await context.bot.send_message(chat_id=chat_id, text="Generating Letters...")
    await context.bot.send_message(chat_id=chat_id, text=upper_letters(games[chat_id].letter_row))

async def scoring(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    if chat_id not in games or not games[chat_id].ongoing_game:
        return

    guess = update.message.text.lower()
    username = update.effective_user.username or f"User_{update.effective_user.id}"

    if guess in games[chat_id].found_words:
        await update.message.reply_text(f"<b>{guess}</b> has already been found!", parse_mode=ParseMode.HTML)
        return

    if guess in games[chat_id].score_words:
        score = len(guess) ** 2
        games[chat_id].score_words.remove(guess)
        games[chat_id].found_words.append(guess)

        if username not in games[chat_id].player_scores:
            games[chat_id].player_scores[username] = 0
            games[chat_id].player_words[username] = []
        
        games[chat_id].player_words[username].append(guess)
        games[chat_id].player_scores[username] += score

        await update.message.reply_text(
            f"<i>{username}</i> found <b>{guess}</b> for {score} points! \n{upper_letters(games[chat_id].letter_row)}",
            parse_mode=ParseMode.HTML
        )

async def end_game(context: CallbackContext):
    job = context.job
    chat_id = job.chat_id
    if chat_id not in games or not games[chat_id].ongoing_game:
        return

    games[chat_id].ongoing_game = False
    await context.bot.send_message(chat_id=chat_id, text="<b>Game Ended!</b>", parse_mode=ParseMode.HTML)

    final_results = "🎉 SCORES: \n"
    for player, score in games[chat_id].player_scores.items():
        final_results += f"{player}: {score}\n"
    
    if not games[chat_id].player_scores:
        final_results = "No one played! \n"
    
    final_results += "\n💡 BEST POSSIBLE WORDS: \n"
    for word in games[chat_id].top_score_words:
        final_results += f"{word}\n"
    
    games[chat_id].sort_player_words()
    final_results += "\n🔎 WORDS FOUND \n"
    for player in games[chat_id].player_words:
        final_results += f"<b>{player}</b> ({len(games[chat_id].player_words[player])})\n"
        final_results += ' '.join(games[chat_id].player_words[player]) + "\n"
    
    await context.bot.send_message(chat_id=chat_id, text=final_results, parse_mode=ParseMode.HTML)
    games[chat_id].end_clear()

def get_wordhunt_handlers():
    return [
        CommandHandler('wordhunt', wordhunt),
        CommandHandler('end', end_game),
        MessageHandler(filters.TEXT & ~filters.COMMAND, scoring)
    ]
