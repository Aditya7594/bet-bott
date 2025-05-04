import random, os
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

games = {}
activity_timers = {}  # Store our activity timers

THIS_FOLDER = os.path.dirname(os.path.abspath(__file__))
letter_list_location = os.path.join(THIS_FOLDER, '8letters.txt')

with open(letter_list_location, "r") as word_list:
    line_list = [line.rstrip('\n').lower() for line in word_list]

class GameObject:
    
    def __init__(self):
        global line_list
        self.line_list = line_list
        self.ongoing_game = False
        self.letter_row = []
        self.score_words = []
        self.found_words = []
        self.player_scores = {}
        self.top_score_words = []
        self.player_words = {}
        self.last_activity_time = None  # Track the time of last activity

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
            if(self.can_spell(word)):
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
            while(len(self.score_words) < 125):
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


def upper_letters(letter_row):
    upper = ""
    for letter in letter_row:
        upper = upper + " " + letter.upper()
    return upper


async def play(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global games
    global activity_timers
    chat_id = update.effective_chat.id
    await update.message.reply_html("Generating Letters")
    if chat_id not in games:
        games[chat_id] = GameObject()
    games[chat_id].start()

    # Cancel any existing timer
    if chat_id in activity_timers and activity_timers[chat_id] is not None:
        activity_timers[chat_id].schedule_removal()
    
    # Create a new inactivity timer (30 seconds)
    activity_timers[chat_id] = context.job_queue.run_repeating(
        check_activity, 5.0,  # Check activity every 5 seconds
        chat_id=chat_id, data=update
    )
    
    await update.message.reply_html(upper_letters(games[chat_id].letter_row))


async def check_activity(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check if there has been any activity in the last 30 seconds"""
    job = context.job
    chat_id = job.chat_id
    update = job.data
    
    if chat_id not in games or not games[chat_id].ongoing_game:
        # No active game, remove the timer
        job.schedule_removal()
        return
    
    current_time = asyncio.get_event_loop().time()
    # If no activity for 30 seconds, end the game
    if current_time - games[chat_id].last_activity_time > 30:
        await end_game(update, context)
        job.schedule_removal()


async def scoring(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if chat_id not in games or not games[chat_id].ongoing_game:
        return
    
    guess = update.message.text
    username = update.effective_user.username or update.effective_user.first_name
    
    guess = guess.lower()
    print(f"User {username} guessed: {guess}")
    
    if guess in games[chat_id].found_words:
        found_notif = f"<b>{guess}</b> has already been found!"
        await update.message.reply_html(found_notif)
    elif guess in games[chat_id].score_words:
        # Valid word found - update activity time
        games[chat_id].update_activity_time()
        
        score = len(guess) * len(guess)
        notif = f"<i>{username}</i> found <b>{guess}</b> for {score} points! \n{upper_letters(games[chat_id].letter_row)}"
        games[chat_id].score_words.remove(guess)
        games[chat_id].found_words.append(guess)
        if username not in games[chat_id].player_scores:
            games[chat_id].player_scores[username] = 0
        if username not in games[chat_id].player_words:
            games[chat_id].player_words[username] = []
        games[chat_id].player_words[username].append(guess)
        games[chat_id].player_scores[username] += score
        await update.message.reply_html(notif)


async def end_game_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    chat_id = job.chat_id
    update = job.data
    
    if chat_id in games and games[chat_id].ongoing_game:
        await end_game(update, context)


async def end_game(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if chat_id not in games or not games[chat_id].ongoing_game:
        await update.message.reply_html("No active game to end.")
        return
    
    games[chat_id].ongoing_game_false()
    await update.message.reply_html("<b>Game Ended!</b>")
    
    final_results = "🎉 SCORES: \n"
    for player, score in games[chat_id].player_scores.items():
        final_results = final_results + player + ": " + str(score) + "\n"
    if not bool(games[chat_id].player_scores): # player_scores dict is empty
        final_results = "No one played! \n"
    
    # Best Possible Words
    total_possible_words = len(games[chat_id].score_words) + len(games[chat_id].found_words)
    final_results += f"\n💡 BEST POSSIBLE WORDS ({total_possible_words} total): \n"
    for word in games[chat_id].top_score_words:
        final_results += word + "\n"
    
    # Player Scoring Words
    games[chat_id].sort_player_words()
    final_results += "\n🔎 WORDS FOUND \n"
    for player in games[chat_id].player_words:
        final_results += f"<b>{player}({len(games[chat_id].player_words[player])})</b> \n"
        for word in games[chat_id].player_words[player]:
            final_results += word + " "
        final_results += "\n"
    
    await update.message.reply_html(final_results)
    games[chat_id].end_clear()
    
    # Clean up the timer
    global activity_timers
    if chat_id in activity_timers and activity_timers[chat_id] is not None:
        activity_timers[chat_id].schedule_removal()
        activity_timers[chat_id] = None


def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("wordhunt", play))
    application.add_handler(CommandHandler("end", end_game))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, scoring))
