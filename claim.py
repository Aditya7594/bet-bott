
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CallbackContext
from datetime import datetime
from pymongo import MongoClient

# MongoDB client setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
users_collection = db['users']

# Handle the claim button click
async def claim_credits(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    claim_amount = int(update.callback_query.data.split("_")[1])  # Extract credit amount from callback data

    # Update user's credits in the database
    users_collection.update_one({"user_id": user_id}, {"$inc": {"credits": claim_amount}})
    
    # Fetch updated user data
    updated_user_data = users_collection.find_one({"user_id": user_id})
    await update.callback_query.answer(f"🎉 You've claimed {claim_amount} credits! Your new balance is {updated_user_data['credits']} credits.")

# Random claim button sender
async def random_claim(update: Update, context: CallbackContext) -> None:
    # Random credits between 100 and 1000
    random_credits = random.randint(100, 1000)
    
    # Create a claim button
    claim_button = InlineKeyboardButton(f"Claim {random_credits} credits!", callback_data=f"claim_{random_credits}")
    keyboard = [[claim_button]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send message with claim button
    await update.message.reply_text("🎉 A random claim is available! Click below to claim your credits!", reply_markup=reply_markup)

# Randomly send the claim button at intervals
async def send_random_claim(context: CallbackContext) -> None:
    # Choose a random interval between 1 and 2 hours (3600 seconds to 7200 seconds)
    interval = random.randint(3600, 7200)
    
    # Wait for the random interval before sending a claim
    await context.bot.send_message(
        chat_id=context.job.context.chat_id,
        text="🎉 A random claim is available! Click below to claim your credits!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Claim Credits", callback_data="random_claim")]]))
    
    # Re-schedule the next random claim after the interval
    context.job_queue.run_once(send_random_claim, interval, context=context.job.context)

# Daily reward function
async def daily(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    
    # Check if the user has already claimed today
    now = datetime.utcnow() + timedelta(hours=5, minutes=30)  # Convert to IST (UTC +5:30)
    today_4am = now.replace(hour=4, minute=0, second=0, microsecond=0)
    
    last_claimed = db.get('last_claimed', {})
    if user_id in last_claimed:
        last_claim_time = last_claimed[user_id]
        # If last claim was before today's 4 AM IST
        if last_claim_time >= today_4am:
            await update.message.reply_text("You have already claimed your daily reward today!")
            return
    
    # Give the user 1,000 credits
    if user_id not in db:
        db[user_id] = {'credits': 0}
    
    db[user_id]['credits'] += 1000
    last_claimed[user_id] = now

    await update.message.reply_text(f"🎉 You've claimed your daily reward of 1,000 credits! You now have {db[user_id]['credits']} credits.")

