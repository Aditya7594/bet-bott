import logging
import random
import json
import os
from datetime import datetime
from typing import List, Dict, Tuple, Set, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
)

from pymongo import MongoClient

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

PLAYING = 1

PREFIX_LETTER = "letter_"
PREFIX_RESET = "reset"
PREFIX_HINT = "hint"
PREFIX_QUIT = "quit"
PREFIX_NEXT = "next"
PREFIX_COLLECT = "collect"

client = MongoClient('mongodb+srv://Joybot:Joybot123@joybot.toar6.mongodb.net/?retryWrites=true&w=majority&appName=Joybot')
db = client['telegram_bot']
user_collection = db["users"]

levels_file = "levels.json"
rewards_file = "rewards.json"

with open(levels_file, "r", encoding='utf-8') as f:
    levels = json.load(f)

with open(rewards_file, "r", encoding='utf-8') as f:
    rewards = json.load(f)

STYLE_GREEN = '🟢'
STYLE_BLUE = '🔵'
STYLE_WHITE = '⚪'

def get_user_game_state(user_id: int) -> Dict:
    user_data = user_collection.find_one({"_id": user_id})
    if not user_data:
        user_collection.insert_one({
            "_id": user_id,
            "level": 1,
            "score": 0,
            "storage": {
                "items": [],
                "rare_items": [],
                "special_items": []
            },
            "current_level_start": None,
            "words_found": 0,
            "hints_used": 0,
            "levels_completed": 0
        })
        return {
            "level": 1,
            "score": 0,
            "storage": {
                "items": [],
                "rare_items": [],
                "special_items": []
            },
            "current_level_start": None,
            "words_found": 0,
            "hints_used": 0,
            "levels_completed": 0
        }
    
    storage = user_data.get("storage", {})
    if isinstance(storage, list):
        storage = {
            "items": storage,
            "rare_items": [],
            "special_items": []
        }
    
    return {
        "level": user_data.get("level", 1),
        "score": user_data.get("score", 0),
        "storage": storage,
        "current_level_start": user_data.get("current_level_start", None),
        "words_found": user_data.get("words_found", 0),
        "hints_used": user_data.get("hints_used", 0),
        "levels_completed": user_data.get("levels_completed", 0)
    }

def update_user_data(user_id: int, update_data: Dict):
    user_collection.update_one(
        {"_id": user_id},
        {"$set": update_data},
        upsert=True
    )

def get_words_for_level(level: int) -> List[str]:
    level_key = f"level_{level}"
    level_words = levels.get(level_key)
    if not level_words:
        logger.warning(f"No words found for {level_key} in levels.json. Using fallback words.")
        return ["FALLBACK", "WORD", "LIST"]
    return level_words.copy()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    user_id = user.id
    game_state = get_user_game_state(user_id)
    
    if update.effective_chat.type != "private":
        await update.message.reply_text(
            f"Hello {user.first_name}! This game can only be played in private chat. "
            f"Please message me directly to play!"
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        f"🎮 *WORD FINDER GAME* 🎮\n\n"
        f"Welcome {user.first_name}! Let's find some hidden words!\n\n"
        f"{STYLE_GREEN} = Found letters\n"
        f"{STYLE_BLUE} = Selected letters\n"
        f"{STYLE_WHITE} = Unselected letters\n\n"
        f"Words can be: horizontal, vertical, diagonal, L-shaped, or zig-zag\n"
        f"Find all words to complete the level and earn rewards!",
        parse_mode="Markdown"
    )
    
    game_state["current_level_start"] = datetime.now().isoformat()
    update_user_data(user_id, {"current_level_start": game_state["current_level_start"]})
    
    await start_level(update, context)
    
    return PLAYING

async def start_level(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    game_state = get_user_game_state(user_id)
    level = game_state["level"]
    
    is_callback = hasattr(update, 'callback_query') and update.callback_query is not None
    
    words = get_words_for_level(level)
    if not words:
        logger.error(f"No words available for level {level}")
        words = ["FALLBACK", "WORD", "LIST"]
    
    rows, columns = 7, 7
    
    grid, word_positions = generate_grid(words, rows, columns)
    
    context.user_data["grid"] = grid
    context.user_data["words"] = words
    context.user_data["word_positions"] = word_positions
    context.user_data["found_words"] = []
    context.user_data["selected_positions"] = []
    context.user_data["found_positions"] = set()
    context.user_data["selection_pattern"] = None
    
    keyboard = create_grid_keyboard(grid)
    
    successfully_placed_words = list(word_positions.keys())
    not_placed_words = [w for w in words if w not in successfully_placed_words]
    
    if not_placed_words:
        logger.warning(f"Some words couldn't be placed: {not_placed_words}")
    
    words_text = ", ".join([f"*{word}*" for word in words])
    message_text = (
        f"🎮 *Level {level}* 🎮\n\n"
        f"Find: {words_text}\n\n"
        f"(horizontal, vertical, diagonal, L-shaped, zig-zag)"
    )
    
    if is_callback:
        await update.callback_query.message.reply_text(
            message_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            message_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )

def generate_grid(words: List[str], rows: int, columns: int) -> Tuple[List[List[str]], Dict[str, List[Tuple[int, int]]]]:
    grid = [['' for _ in range(columns)] for _ in range(rows)]
    word_positions: Dict[str, List[Tuple[int, int]]] = {}

    words_to_place = sorted(words, key=len, reverse=True)
    
    pattern_success = {"straight": 0, "l_shape": 0, "zig_zag": 0, "multi_turn": 0}
    pattern_attempts = {"straight": 0, "l_shape": 0, "zig_zag": 0, "multi_turn": 0}

    for word in words_to_place:
        placed = False
        attempts = 0
        max_attempts = 150
        word_length = len(word)
        
        available_patterns = []
        
        # Try straight placement for all words
        if word_length <= max(rows, columns):
            available_patterns.append("straight")
        
        # Try L-shape for medium words
        if 4 <= word_length <= rows + columns - 1:
            available_patterns.append("l_shape")
        
        # Try zig-zag for longer words
        if word_length >= 4 and word_length <= min(rows * 2, columns * 2):
            available_patterns.append("zig_zag")
        
        # Try multi-turn for very long words
        if word_length > max(rows, columns) and word_length <= rows * columns // 2:
            available_patterns.append("multi_turn")
        
        if not available_patterns:
            logger.warning(f"Word '{word}' is too long ({word_length}) for grid size ({rows}x{columns})")
            continue
        
        pattern_rotation = available_patterns.copy()
        
        while not placed and attempts < max_attempts:
            if not pattern_rotation:
                pattern_rotation = available_patterns.copy()
            pattern_type = pattern_rotation.pop(0) if pattern_rotation else random.choice(available_patterns)
            
            pattern_attempts[pattern_type] = pattern_attempts.get(pattern_type, 0) + 1
            positions: List[Tuple[int, int]] = []

            if pattern_type == "straight":
                direction = random.randint(0, 3)
                if direction == 0:  # horizontal
                    max_x = columns - word_length
                    if max_x >= 0:
                        x = random.randint(0, max_x)
                        y = random.randint(0, rows - 1)
                        positions = [(x + i, y) for i in range(word_length)]
                elif direction == 1:  # vertical
                    max_y = rows - word_length
                    if max_y >= 0:
                        x = random.randint(0, columns - 1)
                        y = random.randint(0, max_y)
                        positions = [(x, y + i) for i in range(word_length)]
                elif direction == 2:  # diagonal down-right
                    max_x = columns - word_length
                    max_y = rows - word_length
                    if max_x >= 0 and max_y >= 0:
                        x = random.randint(0, max_x)
                        y = random.randint(0, max_y)
                        positions = [(x + i, y + i) for i in range(word_length)]
                else:  # diagonal up-right
                    max_x = columns - word_length
                    min_y = word_length - 1
                    if max_x >= 0 and min_y < rows:
                        x = random.randint(0, max_x)
                        y = random.randint(min_y, rows - 1)
                        positions = [(x + i, y - i) for i in range(word_length)]

            elif pattern_type == "l_shape" and word_length >= 4:
                positions = generate_l_shape_positions(word_length, rows, columns)
                if not positions:
                    continue
            
            elif pattern_type == "zig_zag" and word_length >= 4:
                primary = random.choice(["horizontal", "vertical"])
                
                if primary == "horizontal":
                    max_horiz_span = min(columns, word_length)
                    if max_horiz_span < 4 or rows < 3:
                        continue
                    
                    x = random.randint(0, columns - max_horiz_span)
                    y = random.randint(1, rows - 2)
                    
                    current_x, current_y = x, y
                    up = random.choice([True, False])
                    positions = []
                    
                    for i in range(word_length):
                        if current_x >= columns or current_y < 0 or current_y >= rows:
                            break
                        positions.append((current_x, current_y))
                        current_x += 1
                        if i < word_length - 1:
                            current_y += -1 if up else 1
                            up = not up
                
                else:
                    max_vert_span = min(rows, word_length)
                    if max_vert_span < 4 or columns < 3:
                        continue
                    
                    x = random.randint(1, columns - 2)
                    y = random.randint(0, rows - max_vert_span)
                    
                    current_x, current_y = x, y
                    left = random.choice([True, False])
                    positions = []
                    
                    for i in range(word_length):
                        if current_y >= rows or current_x < 0 or current_x >= columns:
                            break
                        positions.append((current_x, current_y))
                        current_y += 1
                        if i < word_length - 1:
                            current_x += -1 if left else 1
                            left = not left
                
                if len(positions) < word_length:
                    positions = []
            
            elif pattern_type == "multi_turn" and word_length > 4:
                x = random.randint(0, columns - 1)
                y = random.randint(0, rows - 1)
                
                positions = [(x, y)]
                current_x, current_y = x, y
                
                directions = [(1, 0), (0, 1), (-1, 0), (0, -1)]
                previous_direction = None
                
                for _ in range(word_length - 1):
                    random.shuffle(directions)
                    placed_next = False
                    
                    for dx, dy in directions:
                        next_x, next_y = current_x + dx, current_y + dy
                        
                        if (0 <= next_x < columns and 
                            0 <= next_y < rows and 
                            (next_x, next_y) not in positions):
                            
                            positions.append((next_x, next_y))
                            current_x, current_y = next_x, next_y
                            previous_direction = (dx, dy)
                            placed_next = True
                            break
                    
                    if not placed_next:
                        positions = []
                        break

            if positions and len(positions) == word_length:
                valid = True
                for px, py in positions:
                    if not (0 <= px < columns and 0 <= py < rows):
                        valid = False
                        break
                    cell_content = grid[py][px]
                    if cell_content and cell_content != word[positions.index((px, py))]:
                        valid = False
                        break

                if valid:
                    for idx, (px, py) in enumerate(positions):
                        grid[py][px] = word[idx]
                    word_positions[word] = positions
                    placed = True
                    pattern_success[pattern_type] = pattern_success.get(pattern_type, 0) + 1

            attempts += 1

        if not placed:
            logger.warning(f"Failed to place word: '{word}' after {max_attempts} attempts")

    for y in range(rows):
        for x in range(columns):
            if not grid[y][x]:
                grid[y][x] = chr(random.randint(65, 90))

    total_words = len(words_to_place)
    placed_words = len(word_positions)
    logger.info(f"Placed {placed_words}/{total_words} words ({placed_words/total_words*100:.1f}%)")
    for pattern in pattern_success:
        attempts = pattern_attempts.get(pattern, 0)
        success = pattern_success.get(pattern, 0)
        if attempts > 0:
            success_rate = success / attempts * 100
            logger.info(f"{pattern}: {success}/{attempts} ({success_rate:.1f}%)")

    return grid, word_positions

def generate_l_shape_positions(word_length, rows, columns):
    split = random.randint(2, word_length - 2)
    first_len, second_len = split, word_length - split
    orientations = ['right_down', 'right_up', 'down_right', 'down_left', 'left_up', 'left_down', 'up_right', 'up_left']
    for _ in range(50):
        orient = random.choice(orientations)
        x, y = random.randint(0, columns - 1), random.randint(0, rows - 1)
        
        if orient == 'right_down':
            seg1 = [(x+i, y) for i in range(first_len)]
            seg2 = [(seg1[-1][0], seg1[-1][1]+j) for j in range(1, second_len+1)]
        elif orient == 'right_up':
            seg1 = [(x+i, y) for i in range(first_len)]
            seg2 = [(seg1[-1][0], seg1[-1][1]-j) for j in range(1, second_len+1)]
        elif orient == 'left_down':
            seg1 = [(x-i, y) for i in range(first_len)]
            seg2 = [(seg1[-1][0], seg1[-1][1]+j) for j in range(1, second_len+1)]
        elif orient == 'left_up':
            seg1 = [(x-i, y) for i in range(first_len)]
            seg2 = [(seg1[-1][0], seg1[-1][1]-j) for j in range(1, second_len+1)]
        elif orient == 'down_right':
            seg1 = [(x, y+i) for i in range(first_len)]
            seg2 = [(seg1[-1][0]+j, seg1[-1][1]) for j in range(1, second_len+1)]
        elif orient == 'down_left':
            seg1 = [(x, y+i) for i in range(first_len)]
            seg2 = [(seg1[-1][0]-j, seg1[-1][1]) for j in range(1, second_len+1)]
        elif orient == 'up_right':
            seg1 = [(x, y-i) for i in range(first_len)]
            seg2 = [(seg1[-1][0]+j, seg1[-1][1]) for j in range(1, second_len+1)]
        elif orient == 'up_left':
            seg1 = [(x, y-i) for i in range(first_len)]
            seg2 = [(seg1[-1][0]-j, seg1[-1][1]) for j in range(1, second_len+1)]
        else:
            continue
        
        positions = seg1 + seg2
        if all(0 <= px < columns and 0 <= py < rows for px, py in positions):
            return positions
    return []

def create_grid_keyboard(grid: List[List[str]], selected_positions: List[Tuple[int, int]] = None, found_positions: Set[Tuple[int, int]] = None) -> InlineKeyboardMarkup:
    if selected_positions is None:
        selected_positions = []
    if found_positions is None:
        found_positions = set()
    
    keyboard = []
    for y, row in enumerate(grid):
        keyboard_row = []
        for x, letter in enumerate(row):
            callback_data = f"{PREFIX_LETTER}{x},{y}"
            
            if (x, y) in selected_positions:
                display_text = f"{letter} {STYLE_BLUE}"
            elif (x, y) in found_positions:
                display_text = f"{letter} {STYLE_GREEN}"
            else:
                display_text = f"{letter} {STYLE_WHITE}"
                
            keyboard_row.append(InlineKeyboardButton(display_text, callback_data=callback_data))
        keyboard.append(keyboard_row)
    
    control_row = [
        InlineKeyboardButton("🔄 Reset", callback_data=PREFIX_RESET),
        InlineKeyboardButton("💡 Hint", callback_data=PREFIX_HINT),
        InlineKeyboardButton("❌ Quit", callback_data=PREFIX_QUIT)
    ]
    keyboard.append(control_row)
    
    return InlineKeyboardMarkup(keyboard)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    user_id = user.id
    game_state = get_user_game_state(user_id)
    
    if query.data.startswith(PREFIX_LETTER):
        return await handle_letter_press(update, context)
    
    elif query.data == PREFIX_RESET:
        context.user_data["selected_positions"] = []
        context.user_data["selection_pattern"] = None
        grid = context.user_data["grid"]
        found_positions = context.user_data["found_positions"]
        keyboard = create_grid_keyboard(grid, [], found_positions)
        await query.edit_message_reply_markup(reply_markup=keyboard)
        
    elif query.data == PREFIX_HINT:
        game_state["hints_used"] += 1
        update_user_data(user_id, {"hints_used": game_state["hints_used"]})
        return await provide_hint(update, context)
    
    elif query.data == PREFIX_QUIT:
        await query.edit_message_text("Game ended. Type /finder to play again!")
        return ConversationHandler.END
    
    elif query.data == PREFIX_NEXT:
        game_state["level"] += 1
        game_state["levels_completed"] += 1
        update_user_data(user_id, {
            "level": game_state["level"],
            "levels_completed": game_state["levels_completed"]
        })
        await query.edit_message_text(f"✨ Loading level {game_state['level']}...")
        await start_level(update, context)
    
    elif query.data == PREFIX_COLLECT:
        await collect_reward(update, context)
    
    return PLAYING

def get_pattern_type(positions: List[Tuple[int, int]]) -> str:
    if len(positions) < 2:
        return 'unknown'
    
    dirs = []
    for (x1, y1), (x2, y2) in zip(positions, positions[1:]):
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy > 0:
            dirs.append('down')
        elif dx == 0 and dy < 0:
            dirs.append('up')
        elif dy == 0 and dx > 0:
            dirs.append('right')
        elif dy == 0 and dx < 0:
            dirs.append('left')
        else:
            dirs.append('other')
    
    changes = sum(1 for i in range(1, len(dirs)) if dirs[i] != dirs[i-1])
    
    if changes == 0:
        return 'straight'
    if changes == 1:
        return 'l_shape'
    if all(dirs[i] != dirs[i+1] for i in range(len(dirs)-1)):
        return 'zig_zag'
    return 'complex'

def is_valid_selection(selected_positions: List[Tuple[int, int]], new_pos: Tuple[int, int]) -> bool:
    if not selected_positions:
        return True
    
    last_pos = selected_positions[-1]
    
    if max(abs(new_pos[0] - last_pos[0]), abs(new_pos[1] - last_pos[1])) > 1:
        return False
    
    if new_pos in selected_positions:
        return False
    
    return True

async def handle_letter_press(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user = query.from_user
    user_id = user.id
    
    _, pos_str = query.data.split("_")
    x, y = map(int, pos_str.split(","))
    
    grid = context.user_data["grid"]
    selected_positions = context.user_data["selected_positions"]
    found_positions = context.user_data["found_positions"]
    word_positions = context.user_data["word_positions"]
    words = context.user_data["words"]
    found_words = context.user_data["found_words"]
    
    current_pos = (x, y)
    
    previous_selected = selected_positions.copy()
    
    if not selected_positions:
        selected_positions.append(current_pos)
        
    elif current_pos == selected_positions[-1]:
        selected_positions.pop()
        
    elif current_pos not in selected_positions:
        if is_valid_selection(selected_positions, current_pos):
            selected_positions.append(current_pos)
            pattern_type = get_pattern_type(selected_positions)
            context.user_data["selection_pattern"] = pattern_type
        else:
            await query.answer("⚠️ Selection must follow a valid pattern!")
            return PLAYING
    
    if not selected_positions:
        context.user_data["selection_pattern"] = None
    
    if len(selected_positions) >= 2:
        selected_word = ''.join([grid[y][x] for x, y in selected_positions])
        
        for word in words:
            if word not in found_words and len(word) == len(selected_positions):
                word_pos = word_positions.get(word, [])
                
                positions_match = False
                if word_pos == selected_positions:
                    positions_match = True
                elif word_pos == selected_positions[::-1]:
                    positions_match = True
                elif set(word_pos) == set(selected_positions) and selected_word == word:
                    positions_match = True
                
                if positions_match and selected_word == word:
                    found_words.append(word)
                    game_state = get_user_game_state(user_id)
                    game_state["words_found"] += 1
                    update_user_data(user_id, {"words_found": game_state["words_found"]})
                    
                    for pos in selected_positions:
                        found_positions.add(pos)
                    
                    selected_positions.clear()
                    context.user_data["selection_pattern"] = None
                    
                    if len(found_words) == len(words):
                        game_state = get_user_game_state(user_id)
                        level_complete_score = calculate_score(game_state)
                        game_state["score"] += level_complete_score
                        update_user_data(user_id, {"score": game_state["score"]})
                        
                        next_keyboard = InlineKeyboardMarkup([
                            [
                                InlineKeyboardButton("🎮 Next Level", callback_data=PREFIX_NEXT),
                                InlineKeyboardButton("🎁 Collect Reward", callback_data=PREFIX_COLLECT)
                            ]
                        ])
                        
                        formatted_found_words = ", ".join([f"✅ *{w}*" for w in found_words])
                        
                        await query.edit_message_text(
                            f"🏆 *Level {game_state['level']} completed!* 🏆\n\n"
                            f"Words found:\n{formatted_found_words}\n\n"
                            f"⭐ Score: {level_complete_score} points\n"
                            f"⏱️ Time: {calculate_level_time(game_state)} seconds",
                            reply_markup=next_keyboard,
                            parse_mode="Markdown"
                        )
                        return PLAYING
                    words_to_find = [w for w in words if w not in found_words]
                    words_text = ", ".join([f"*{w}*" for w in words_to_find])
                    
                    await query.edit_message_text(
                        f"🎮 *Level {game_state['level']}* 🎮\n\n"
                        f"✅ Word found: *{word}*!\n\n"
                        f"Still to find: {words_text}",
                        reply_markup=create_grid_keyboard(grid, selected_positions, found_positions),
                        parse_mode="Markdown"
                    )
                    return PLAYING
    
    if previous_selected != selected_positions:
        keyboard = create_grid_keyboard(grid, selected_positions, found_positions)
        await query.edit_message_reply_markup(reply_markup=keyboard)
    
    return PLAYING

async def provide_hint(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    
    words = context.user_data["words"]
    found_words = context.user_data["found_words"]
    word_positions = context.user_data["word_positions"]
    grid = context.user_data["grid"]
    
    unfound_words = [w for w in words if w not in found_words]
    if not unfound_words:
        await query.answer("You've found all words!")
        return PLAYING
    
    hint_word = random.choice(unfound_words)
    
    if hint_word not in word_positions:
        await query.answer(f"Hint not available for '{hint_word}'. Try again!")
        return PLAYING
    
    first_pos = word_positions[hint_word][0]
    hint_letter = grid[first_pos[1]][first_pos[0]]
    
    pattern = "unknown"
    if len(word_positions[hint_word]) >= 3:
        pattern = get_pattern_type(word_positions[hint_word])
    
    row_position = first_pos[1] + 1  
    col_position = first_pos[0] + 1
    
    if pattern == "l_shape":
        await query.answer(f"Look for '{hint_word}', starting with '{hint_letter}' at position ({col_position},{row_position}). It follows an L-shape!")
    elif pattern == "zig_zag":
        await query.answer(f"Look for '{hint_word}', starting with '{hint_letter}' at position ({col_position},{row_position}). It follows a zig-zag pattern!")
    elif pattern == "multi_turn":
        await query.answer(f"Look for '{hint_word}', starting with '{hint_letter}' at position ({col_position},{row_position}). It has multiple turns!")
    else:
        direction = "unknown"
        if len(word_positions[hint_word]) >= 2:
            first_pos = word_positions[hint_word][0]
            second_pos = word_positions[hint_word][1]
            
            if first_pos[0] == second_pos[0]:  
                direction = "vertical"
            elif first_pos[1] == second_pos[1]:  
                direction = "horizontal"
            elif first_pos[0] < second_pos[0] and first_pos[1] < second_pos[1]:  
                direction = "diagonal down"
            elif first_pos[0] < second_pos[0] and first_pos[1] > second_pos[1]:  
                direction = "diagonal up"
        
        await query.answer(f"Look for '{hint_word}', starting with '{hint_letter}' at position ({col_position},{row_position}) going {direction}!")
    
    return PLAYING

def calculate_score(game_state):
    level = game_state["level"]
    base_score = level * 100
    time_taken = calculate_level_time(game_state)
    time_bonus = max(0, 300 - int(time_taken / 3))  
    hint_penalty = game_state["hints_used"] * 25
    return max(0, base_score + time_bonus - hint_penalty)

def calculate_level_time(game_state):
    if not game_state["current_level_start"]:
        return 0
    start_time = datetime.fromisoformat(game_state["current_level_start"])
    end_time = datetime.now()
    return (end_time - start_time).total_seconds()


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    game_state = get_user_game_state(user_id)
    
    level = game_state["level"]
    score = game_state["score"]
    words_found = game_state["words_found"]
    hints_used = game_state["hints_used"]
    levels_completed = game_state["levels_completed"]
    
    avg_time = "No data"
    if game_state["current_level_start"] and levels_completed > 0:
        start_time = datetime.fromisoformat(game_state["current_level_start"])
        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()
        avg_time = f"{total_time/levels_completed:.1f} seconds"
    
    storage = game_state["storage"]
    total_items = len(storage.get("items", [])) + len(storage.get("rare_items", [])) + len(storage.get("special_items", []))
    
    await update.message.reply_text(
        f"📊 *YOUR STATUS* 📊\n\n"
        f"🎮 Current Level: *{level}*\n"
        f"🏆 Total Score: *{score}*\n"
        f"✅ Words Found: *{words_found}*\n"
        f"⭐ Levels Completed: *{levels_completed}*\n"
        f"💡 Hints Used: *{hints_used}*\n"
        f"⏱️ Avg. Time per Level: *{avg_time}*\n"
        f"🎁 Collected Items: *{total_items}*\n\n"
        f"Type /finder to play!",
        parse_mode="Markdown"
    )

async def storage_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    game_state = get_user_game_state(user_id)
    storage = game_state["storage"]
    
    if not storage or (not storage.get("items") and not storage.get("rare_items") and not storage.get("special_items")):
        await update.message.reply_text(
            f"📦 *YOUR STORAGE* 📦\n\n"
            "Your storage is empty. Complete levels to collect rewards!\n"
            "Use /finder to play and find treasures!",
            parse_mode="Markdown"
        )
    else:
        message = f"📦 *YOUR STORAGE* 📦\n\n"
        
        if storage.get("items"):
            message += "*Common Items:*\n"
            for item in storage["items"]:
                message += f"• {item}\n"
            message += "\n"
        
        if storage.get("rare_items"):
            message += f"*Rare Items:*\n"
            for item in storage["rare_items"]:
                message += f"• {item}\n"
            message += "\n"
        
        if storage.get("special_items"):
            message += f"*Special Items:*\n"
            for item in storage["special_items"]:
                message += f"• {item}\n"
            message += "\n"
        
        message += "Type /finder to collect more rewards!"
        
        await update.message.reply_text(
            message,
            parse_mode="Markdown"
        )

async def collect_reward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    is_callback = hasattr(update, 'callback_query') and update.callback_query is not None
    
    if is_callback:
        query = update.callback_query
        user = query.from_user
        user_id = user.id
        message_method = query.edit_message_text
    else:
        user = update.effective_user
        user_id = user.id
        message_method = update.message.reply_text
    
    game_state = get_user_game_state(user_id)
    
    chance = random.random()
    
    if chance < 0.5:  
        category_chance = random.random()
        
        if category_chance < 0.7:  
            category = "items"
        elif category_chance < 0.95:   
            category = "rare_items"
        else:  
            category = "special_items"
        
        if category in rewards:
            reward_item = random.choice(rewards[category])
            
            if category not in game_state["storage"]:
                game_state["storage"][category] = []
            
            game_state["storage"][category].append(reward_item)
            update_user_data(user_id, {"storage": game_state["storage"]})
            
            await message_method(
                f"🎉 *TREASURE FOUND!* 🎉\n\n"
                f"You received: {reward_item}\n\n"
                f"Check your storage with /storage",
                parse_mode="Markdown"
            )
        else:
            await message_method("Reward list is empty!")
    else:
        await message_method(
            f"🔍 You searched but found nothing this time.\n\n"
            f"Complete more levels to increase your chances!",
            parse_mode="Markdown"
        )


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Fetch users with score >= 0, sorted by score descending
    users = user_collection.find({"score": {"$gte": 0}}).sort("score", -1)

    leaderboard_lines = ["🏆 *GLOBAL LEADERBOARD* 🏆", ""]

    for idx, user in enumerate(users):
        if idx >= 10:
            break

        user_id = user.get("_id")
        name = user.get("first_name")  # Try to get from database
        if not name:  # If not available, fetch from Telegram
            try:
                chat = await context.bot.get_chat(user_id)
                name = chat.first_name
            except Exception as e:
                logger.error(f"Error fetching user name: {e}")
                name = "Player"

        level = user.get("level", 1)
        score = user.get("score", 0)
        words = user.get("words_found", 0)

        # Simple numeric rank
        prefix = f"{idx + 1}."

        leaderboard_lines.append(
            f"{prefix} *{name}* — Level *{level}* | Score *{score}* | Words *{words}*"
        )

    leaderboard_lines.append("")
    leaderboard_lines.append("✨ Complete more levels to climb the leaderboard! ✨")

    await update.message.reply_text(
        "\n".join(leaderboard_lines),
        parse_mode="Markdown"
    )
    
def get_finder_handlers(application: Application) -> list:
    """Register all command and message handlers for the game"""
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("finder", start)],
        states={PLAYING: [CallbackQueryHandler(button_handler)]},
        fallbacks=[CommandHandler("finder", start)],
    )
    
    handlers = [
        conv_handler,
        CommandHandler("status", status_command),
        CommandHandler("storage", storage_command),
        CommandHandler("finderleaderboard", leaderboard_command)
    ]
    
    logger.info("All game handlers registered successfully")
    return handlers
