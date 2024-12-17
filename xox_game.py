from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler
from pymongo import MongoClient
import uuid

# MongoDB setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
games_collection = db['xox_games']

def check_winner(board):
    for row in board:
        if row.count(row[0]) == 3 and row[0] != "":
            return True
    for col in range(3):
        if board[0][col] == board[1][col] == board[2][col] and board[0][col] != "":
            return True
    if board[0][0] == board[1][1] == board[2][2] and board[0][0] != "":
        return True
    if board[0][2] == board[1][1] == board[2][0] and board[0][2] != "":
        return True
    return False

def generate_board_buttons(board, game_id):
    keyboard = []
    for i in range(3):
        row = []
        for j in range(3):
            cell = board[i][j]
            text = cell if cell else " "
            row.append(InlineKeyboardButton(text, callback_data=f"{game_id}:{i}_{j}"))
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

async def xox(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)
    game_id = str(uuid.uuid4())
    new_game = {
        "_id": game_id,
        "player1": user_id,
        "player2": None,
        "turn": user_id,
        "board": [["", "", ""] for _ in range(3)],
        "active": True,
    }
    games_collection.insert_one(new_game)
    await update.message.reply_text(
        "🎮 *Tic-Tac-Toe (XOX) Game Started!* 🎮\n\n"
        f"Player 1: {user.mention_html()} 🟢\n"
        "Waiting for Player 2 to click a button to join!",
        reply_markup=generate_board_buttons(new_game["board"], game_id),
        parse_mode="HTML"
    )

async def handle_xox_click(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user = update.effective_user
    user_id = str(user.id)
    await query.answer()
    try:
        game_id, cell_data = query.data.split(":")
        row, col = map(int, cell_data.split("_"))
    except ValueError:
        await query.answer("Invalid move data!")
        return
    game = games_collection.find_one({"_id": game_id, "active": True})
    if not game:
        await query.edit_message_text("This game is no longer active or doesn't exist.")
        return
    if game["player2"] is None and user_id != game["player1"]:
        game["player2"] = user_id
        games_collection.update_one({"_id": game_id}, {"$set": {"player2": user_id}})
    if user_id not in [game["player1"], game["player2"]]:
        await query.answer("You're not part of this game!")
        return
    if game["turn"] != user_id:
        await query.answer("It's not your turn!")
        return
    if game["board"][row][col]:
        await query.answer("This cell is already taken!")
        return
    symbol = "❌" if user_id == game["player1"] else "⭕"
    game["board"][row][col] = symbol
    if check_winner(game["board"]):
        winner = "Player 1" if user_id == game["player1"] else "Player 2"
        games_collection.update_one({"_id": game_id}, {"$set": {"active": False}})
        await query.edit_message_text(
            f"🎉 *{winner} ({symbol}) wins!* 🎉\n\nGame Over.",
            parse_mode="Markdown"
        )
        return
    if all(cell for row in game["board"] for cell in row):
        games_collection.update_one({"_id": game_id}, {"$set": {"active": False}})
        await query.edit_message_text("It's a draw! 🤝", parse_mode="Markdown")
        return
    next_turn = game["player2"] if user_id == game["player1"] else game["player1"]
    games_collection.update_one({"_id": game_id}, {"$set": {"board": game["board"], "turn": next_turn}})
    await query.edit_message_reply_markup(reply_markup=generate_board_buttons(game["board"], game_id))

def get_xox_handlers():
    return [
        CommandHandler("xox", xox),
        CallbackQueryHandler(handle_xox_click)
    ]
