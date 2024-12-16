import random
from telegram import Update, Message
from telegram.ext import CommandHandler, CallbackContext
from datetime import datetime
import asyncio
from pymongo import MongoClient

# MongoDB Setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
users_collection = db['users']

# Function to get user data from MongoDB
def get_user_by_id(user_id):
    return users_collection.find_one({"user_id": user_id})

# Function to update user credits in MongoDB
def update_user_credits(user_id, new_credits):
    users_collection.update_one({"user_id": user_id}, {"$set": {"credits": new_credits}})

# Roll the dice and send dice emoji
async def roll_dice(update: Update, context: CallbackContext) -> list:
    dice_results = []
    for _ in range(3):
        message: Message = await update.message.reply_dice(emoji="🎲")
        await asyncio.sleep(2)  # Wait for animation to complete
        dice_results.append(message.dice.value)
    return dice_results

# /bdice command
async def bdice(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)

    # Check if user entered the correct arguments
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /bdice <bet_amount> <guess_total>")
        return

    try:
        bet_amount = int(context.args[0])  # Bet amount
        user_guess = int(context.args[1])  # User's guessed outcome
    except ValueError:
        await update.message.reply_text("Invalid input! Please enter numbers for bet amount and guess.")
        return

    # Validate inputs
    if bet_amount <= 0 or not (3 <= user_guess <= 18):
        await update.message.reply_text("Invalid input! Bet must be positive, and the guess must be between 3 and 18.")
        return

    # Retrieve user data
    user_data = get_user_by_id(user_id)

    if not user_data:
        await update.message.reply_text("You are not registered yet. Start with /start.")
        return

    # Check if user has enough credits
    if user_data["credits"] < bet_amount:
        await update.message.reply_text("You don't have enough credits to place this bet.")
        return

    # Roll the dice and send emojis
    await update.message.reply_text("🎲 Rolling the dice...")
    dice_rolls = await roll_dice(update, context)
    outcome = sum(dice_rolls)

    # Determine reward multiplier based on the difference
    diff = abs(outcome - user_guess)
    if diff == 0:
        multiplier = 5  # Exact match
        message = "🎉 Exact match! You won 5x your bet!"
    elif diff == 1:
        multiplier = 3  # Off by 1
        message = "🥳 So close! You won 3x your bet!"
    elif diff == 2:
        multiplier = 1.5  # Off by 2
        message = "😊 Nice try! You won 1.5x your bet!"
    elif diff == 3:
        multiplier = 0.5  # Off by 3
        message = "😅 Not too bad! You won 0.5x your bet!"
    else:
        multiplier = 0  # Loss
        message = "😢 Better luck next time! You lost your bet."

    # Calculate total reward
    reward = int(bet_amount * multiplier)

    # Update user credits
    new_credits = user_data["credits"] - bet_amount + reward
    update_user_credits(user_id, new_credits)

    # Send result message
    await update.message.reply_text(
        f"🎲 You rolled: {dice_rolls[0]}, {dice_rolls[1]}, {dice_rolls[2]} (Total: {outcome})\n"
        f"🧮 Your guess: {user_guess}\n"
        f"{message}\n\n"
        f"💰 Bet: {bet_amount} credits\n"
        f"🏆 Reward: {reward} credits\n"
        f"🔹 New Balance: {new_credits} credits"
    )

# Register the handler
application.add_handler(CommandHandler("bdice", bdice))
