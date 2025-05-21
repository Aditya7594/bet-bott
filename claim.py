import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, CallbackContext, CommandHandler
from datetime import datetime, timedelta
from pymongo import MongoClient
import asyncio

# MongoDB client setup
client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
users_collection = db['users']

# Handle the claim button click
async def claim_credits(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    claim_amount = int(update.callback_query.data.split("_")[1])  # Extract credit amount from callback data

    # Check if the user is the one who initiated the claim
    if user_id != context.user_data.get('claim_user_id'):
        await update.callback_query.answer("This claim is not for you!")
        return

    # Update user's credits in the database
    users_collection.update_one({"user_id": user_id}, {"$inc": {"credits": claim_amount}})
    
    # Fetch updated user data
    updated_user_data = users_collection.find_one({"user_id": user_id})
    await update.callback_query.answer(f"🎉 You've claimed {claim_amount} credits! Your new balance is {updated_user_data['credits']} credits.")
    
    # Delete the claim button message after it is clicked
    await update.callback_query.message.delete()

# Random claim button sender
async def random_claim(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    
    # Check for cooldown (15 minutes)
    now = datetime.utcnow()
    last_claim_time = context.user_data.get('last_random_claim_time')
    if last_claim_time:
        elapsed_time = (now - last_claim_time).total_seconds()
        if elapsed_time < 900:  # 15 minutes = 900 seconds
            remaining_time = 900 - elapsed_time
            minutes = int(remaining_time // 60)
            seconds = int(remaining_time % 60)
            await update.message.reply_text(f"⏳ Please wait {minutes} minutes and {seconds} seconds before using /claim again.")
            return
    
    # Random credits between 100 and 1000
    random_credits = random.randint(100, 1000)
    
    # Create a claim button
    claim_button = InlineKeyboardButton(f"Claim {random_credits} credits!", callback_data=f"claim_{random_credits}")
    keyboard = [[claim_button]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send message with claim button
    sent_message = await update.message.reply_text("🎉 A random claim is available! Click below to claim your credits!", reply_markup=reply_markup)
    
    # Store the message ID for later deletion and the user ID who initiated the claim
    context.user_data['claim_message_id'] = sent_message.message_id
    context.user_data['last_random_claim_time'] = now
    context.user_data['claim_user_id'] = user_id

# Randomly send the claim button at intervals
async def send_random_claim(context: CallbackContext) -> None:
    # Choose a random interval between 1 and 2 hours (3600 seconds to 7200 seconds)
    interval = random.randint(3600, 7200)
    
    # Wait for the random interval before sending a claim
    sent_message = await context.bot.send_message(
        chat_id=context.job.context.chat_id,
        text="🎉 A random claim is available! Click below to claim your credits!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Claim Credits", callback_data="random_claim")]]))
    
    # Delete the message after 10 seconds
    await asyncio.sleep(10)
    await sent_message.delete()
    
    # Re-schedule the next random claim after the interval
    context.job_queue.run_once(send_random_claim, interval, context=context.job.context)

def get_random_claim_handlers():
    return [
        CommandHandler("randomclaim", random_claim),
    ]

# Daily reward function
async def daily(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    
    # Check if the user has already claimed today
    now = datetime.utcnow() + timedelta(hours=5, minutes=30)  # Convert to IST (UTC +5:30)
    today_4am = now.replace(hour=4, minute=0, second=0, microsecond=0)
    
    # Fetch last claim time from user's data in the database
    user_data = users_collection.find_one({"user_id": user_id})
    
    if user_data:
        last_claimed = user_data.get('last_claimed')
        if last_claimed and last_claimed >= today_4am:
            await update.message.reply_text("You have already claimed your daily reward today!")
            return

    # Check if the user is in the main group chat
    main_group_id = -1002341708195
    user_member = await context.bot.get_chat_member(main_group_id, user_id)
    is_in_main_group = user_member.status in ['member', 'administrator', 'creator']

    # Check if the user has the bot's username in their bio
    user_info = await context.bot.get_chat(user_id)
    bot_username = "@Joyfunbot"
    has_bot_in_bio = bot_username in user_info.bio if user_info.bio else False

    # Calculate the reward multiplier
    reward_multiplier = 1.0
    if is_in_main_group:
        reward_multiplier = 2.0
    if has_bot_in_bio:
        reward_multiplier += 0.5

    # Give the user credits based on the multiplier
    reward_amount = int(1000 * reward_multiplier)

    # Add credits to the user
    users_collection.update_one({"user_id": user_id}, {"$inc": {"credits": reward_amount}, "$set": {"last_claimed": now}})

    updated_user_data = users_collection.find_one({"user_id": user_id})
    await update.message.reply_text(f"🎉 You've claimed your daily reward of {reward_amount} credits! You now have {updated_user_data['credits']} credits.")
    
    # Delete the claim message after 10 seconds
    await asyncio.sleep(10)
    await update.message.delete()

# New feature for free credits
async def bonus(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    
    # Check for cooldown (30 minutes)
    now = datetime.utcnow()
    last_bonus_claim_time = context.user_data.get('last_bonus_claim_time')
    if last_bonus_claim_time:
        elapsed_time = (now - last_bonus_claim_time).total_seconds()
        if elapsed_time < 1800:  # 30 minutes = 1800 seconds
            remaining_time = 1800 - elapsed_time
            minutes = int(remaining_time // 60)
            seconds = int(remaining_time % 60)
            await update.message.reply_text(f"⏳ Please wait {minutes} minutes and {seconds} seconds before using /bonus again.")
            return
    
    # Check if the user is in the main group chat
    main_group_id = -1002341708195
    user_member = await context.bot.get_chat_member(main_group_id, user_id)
    is_in_main_group = user_member.status in ['member', 'administrator', 'creator']

    # Check if the user has the bot's username in their bio
    user_info = await context.bot.get_chat(user_id)
    bot_username = "@Joyfunbot"
    has_bot_in_bio = bot_username in user_info.bio if user_info.bio else False

    # Calculate the reward multiplier
    reward_multiplier = 1.0
    if is_in_main_group:
        reward_multiplier = 2.0
    if has_bot_in_bio:
        reward_multiplier += 0.5

    # Give the user credits based on the multiplier
    reward_amount = int(500 * reward_multiplier)

    # Add credits to the user
    users_collection.update_one({"user_id": user_id}, {"$inc": {"credits": reward_amount}})

    updated_user_data = users_collection.find_one({"user_id": user_id})
    await update.message.reply_text(f"🎉 You've claimed your bonus of {reward_amount} credits! You now have {updated_user_data['credits']} credits.")
    
    # Store the last bonus claim time
    context.user_data['last_bonus_claim_time'] = now

def get_claim_handlers():
    return [
        CommandHandler("daily", daily),
        CommandHandler("claim", random_claim),  # Changed from randomclaim to claim
        CommandHandler("bonus", bonus),  # Renamed from freecredits to bonus
        CallbackQueryHandler(claim_credits, pattern=r"^claim_\d+$"),
        CallbackQueryHandler(claim_credits, pattern=r"^random_claim$"),
        *get_random_claim_handlers(),
    ]
