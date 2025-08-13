"""
Full Telegram bot template for selling LEGAL digital goods.

Features:
- Category / item browsing (user-facing)
- Admin panel (admin user id restricted)
  - Add / Edit / Delete categories
  - Add / Edit / Delete items
- Local JSON persistence (categories.json, items.json)
- Blockonomics integration (new address & balance check) for BTC payments
- Back navigation and slick inline keyboard UI
- Works in polling mode (local) or webhook mode when deployed (Render)
- Replace example items with lawful digital goods only

Before running:
- pip install python-telegram-bot==20.* requests python-dotenv
- Create a .env with BLOCKONOMICS_API_KEY if using payments
- Replace TELEGRAM_TOKEN with your bot token or set TELEGRAM_TOKEN in env
- Ensure the files in item["file_path"] exist (for file delivery)
"""

import os
import json
import asyncio
import requests
from pathlib import Path
from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
    ConversationHandler, MessageHandler, filters
)

load_dotenv()

# ---------- CONFIG ----------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or "8132539541:AAFTibgRmTRfUZJhDFkbHzzXD8yG1KHs8Dg"
BLOCKONOMICS_API_KEY = os.getenv("BLOCKONOMICS_API_KEY")  # set in .env
VIDEO_URL = "https://ik.imagekit.io/myrnjevjk/game%20over.mp4?updatedAt=1754980438031"  # example
ADMIN_USER_ID = 7260656020  # admin Telegram user id (unchanged per your request)

CATEGORIES_FILE = "categories.json"
ITEMS_FILE = "items.json"

# ---------- STATE NAMES (clear, count must match) ----------
(
    ADMIN_MENU,
    CATEGORY_MENU,
    CATEGORY_ADD,
    CATEGORY_EDIT_KEY,
    CATEGORY_EDIT_NAME,
    CATEGORY_DELETE_CONFIRM,

    ITEM_MENU,
    ITEM_ADD_KEY,
    ITEM_ADD_NAME,
    ITEM_ADD_PRICE,
    ITEM_ADD_PATH,
    ITEM_ADD_CATEGORY,
    ITEM_EDIT_SELECT,
    ITEM_EDIT_FIELD_SELECT,
    ITEM_EDIT_FIELD_VALUE,
    ITEM_DELETE_CONFIRM
) = range(16)

# ---------- Persistence helpers ----------
def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ---------- Default safe example data (legal items) ----------
DEFAULT_ITEMS = {
    "ebook_python": {
        "name": "Python Basics eBook",
        "price_btc": 0.00005,
        "file_path": "items/python_basics.pdf"
    },
    "video_git": {
        "name": "Git & GitHub Tutorial (MP4)",
        "price_btc": 0.00008,
        "file_path": "items/git_tutorial.mp4"
    },
    "template_resume": {
        "name": "Professional Resume Template",
        "price_btc": 0.00002,
        "file_path": "items/resume_template.docx"
    }
}

DEFAULT_CATEGORIES = {
    "ebooks": ["ebook_python"],
    "videos": ["video_git"],
    "templates": ["template_resume"]
}

# Load or initialize data
ITEMS = load_json(ITEMS_FILE, DEFAULT_ITEMS.copy())
CATEGORIES = load_json(CATEGORIES_FILE, DEFAULT_CATEGORIES.copy())

# ---------- Utility helpers ----------
def is_admin_user(update: Update) -> bool:
    user = update.effective_user
    return user and user.id == ADMIN_USER_ID

def build_main_categories_keyboard():
    keyboard = []
    for key in CATEGORIES.keys():
        display = key.replace("_", " ").title()
        keyboard.append([InlineKeyboardButton(display, callback_data=f"cat:{key}")])
    keyboard.append([InlineKeyboardButton("🛠️ Admin Panel", callback_data="admin:open")])
    return InlineKeyboardMarkup(keyboard)

def build_items_keyboard(category_key: str):
    keyboard = []
    items = CATEGORIES.get(category_key, [])
    for item_key in items:
        item = ITEMS.get(item_key, {"name": item_key})
        keyboard.append([InlineKeyboardButton(item["name"], callback_data=f"item:{category_key}:{item_key}")])
    keyboard.append([InlineKeyboardButton("⬅️ Back to categories", callback_data="nav:categories")])
    return InlineKeyboardMarkup(keyboard)

def build_item_actions_keyboard(category_key: str, item_key: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Buy", callback_data=f"buy:{category_key}:{item_key}")],
        [InlineKeyboardButton("⬅️ Back to items", callback_data=f"cat:{category_key}")]
    ])

# ---------- User-facing handlers ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome — browse categories below:",
        reply_markup=build_main_categories_keyboard()
    )

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dispatches callback_data to appropriate handlers."""
    query = update.callback_query
    await query.answer()
    data = query.data

    # navigation
    if data == "nav:categories":
        await query.edit_message_text("Choose a category:", reply_markup=build_main_categories_keyboard())
        return

    # open admin panel
    if data == "admin:open":
        if not is_admin_user(update):
            await query.edit_message_text("⛔ Not authorized.")
            return
        return await admin_panel_start(update, context)

    # category clicked e.g., cat:ebooks
    if data.startswith("cat:"):
        _, cat_key = data.split(":", 1)
        if cat_key not in CATEGORIES:
            await query.edit_message_text("Category not found.")
            return
        await query.edit_message_text(f"Items in {cat_key.title()}:", reply_markup=build_items_keyboard(cat_key))
        return

    # item clicked e.g., item:ebooks:ebook_python
    if data.startswith("item:"):
        _, cat_key, item_key = data.split(":", 2)
        item = ITEMS.get(item_key)
        if not item:
            await query.edit_message_text("Item not found.")
            return
        text = f"*{item['name']}*\nPrice: {item['price_btc']} BTC\n\nClick Buy to get payment address."
        await query.edit_message_text(text, reply_markup=build_item_actions_keyboard(cat_key, item_key), parse_mode="Markdown")
        return

    # buy clicked e.g., buy:ebooks:ebook_python
    if data.startswith("buy:"):
        _, cat_key, item_key = data.split(":", 2)
        return await handle_buy_request(update, context, cat_key, item_key)

    # admin callbacks - starting with admin:
    if data.startswith("admin:"):
        # forward to admin handler
        return await admin_callback_router(update, context, data)

    # fallback
    await query.edit_message_text("Unknown action.")

# ---------- Payment handlers (Blockonomics) ----------
def blockonomics_new_address():
    """Request a new receiving address from Blockonomics.
    Returns address string on success, raises requests.HTTPError on failure."""
    if not BLOCKONOMICS_API_KEY:
        raise RuntimeError("BLOCKONOMICS_API_KEY not set")

    headers = {'Authorization': BLOCKONOMICS_API_KEY}
    resp = requests.post("https://www.blockonomics.co/api/new_address", headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    # The JSON format: {"address": "...", ...}
    return data.get("address")

def blockonomics_check_balance(address):
    """Check balance for an address. Returns confirmed BTC float."""
    if not BLOCKONOMICS_API_KEY:
        raise RuntimeError("BLOCKONOMICS_API_KEY not set")

    headers = {'Authorization': BLOCKONOMICS_API_KEY}
    # balance endpoint expects POST with json {'addr': [address]}
    resp = requests.post("https://www.blockonomics.co/api/balance", json={'addr': [address]}, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    # Expected format: {"data": [{"addr": "...", "confirmed": <satoshis>, ...}, ...]}
    if "data" in data and len(data["data"]) > 0:
        confirmed_sats = int(data["data"][0].get("confirmed", 0))
        return confirmed_sats / 1e8
    return 0.0

async def handle_buy_request(update: Update, context: ContextTypes.DEFAULT_TYPE, cat_key: str, item_key: str):
    query = update.callback_query
    item = ITEMS.get(item_key)
    if not item:
        await query.edit_message_text("Item not found.")
        return

    try:
        addr = blockonomics_new_address()
    except Exception as e:
        await query.edit_message_text(f"Failed to create payment address: {e}")
        return

    # Save pending payment in user_data
    context.user_data['pending_payment'] = {
        'item_key': item_key,
        'address': addr,
        'amount': item['price_btc']
    }

    await query.edit_message_text(
        f"Send *{item['price_btc']}* BTC to address:\n`{addr}`\n\n"
        "When you have sent the payment, run /confirm to check and receive the file.",
        parse_mode="Markdown"
    )

# /confirm handler
async def cmd_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.user_data.get('pending_payment')
    if not pending:
        await update.message.reply_text("You have no pending payment.")
        return

    try:
        received = blockonomics_check_balance(pending['address'])
    except Exception as e:
        await update.message.reply_text(f"Payment check failed: {e}")
        return

    if received >= pending['amount'] - 1e-12:  # tiny tolerance
        item = ITEMS.get(pending['item_key'])
        if not item:
            await update.message.reply_text("Item not found. Contact admin.")
            return
        file_path = item.get('file_path')
        if not file_path or not os.path.exists(file_path):
            await update.message.reply_text("File missing on server. Contact admin.")
            return
        # send file
        try:
            with open(file_path, "rb") as f:
                await update.message.reply_document(document=InputFile(f), caption=f"Here is your {item['name']}. Thank you.")
            # clear pending
            del context.user_data['pending_payment']
        except Exception as e:
            await update.message.reply_text(f"Failed to send file: {e}")
    else:
        await update.message.reply_text(f"Payment not detected/confirmed. Received: {received} BTC. Waiting for {pending['amount']} BTC.")

# ---------- ADMIN PANEL (full flows) ----------
async def admin_panel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        text_target = query
    else:
        text_target = update.message

    keyboard = [
        [InlineKeyboardButton("📂 Manage Categories", callback_data="admin:categories")],
        [InlineKeyboardButton("📦 Manage Items", callback_data="admin:items")],
        [InlineKeyboardButton("⬅️ Back to store", callback_data="nav:categories")]
    ]
    await text_target.edit_message_text("Admin Panel — choose:", reply_markup=InlineKeyboardMarkup(keyboard)) if hasattr(text_target, "edit_message_text") else await text_target.reply_text("Admin Panel — choose:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_MENU

async def admin_callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
    """Router for admin-prefixed callbacks."""
    # callback_data starts with admin:
    # possible: admin:categories, admin:items, admin:add_cat, admin:edit_cat:<key>, admin:del_cat:<key>
    query = update.callback_query
    await query.answer()
    _, action, *rest = callback_data.split(":")

    if action == "categories":
        return await admin_show_categories(update, context)

    if action == "items":
        return await admin_show_items(update, context)

    # further admin actions will be handled by the show menus via their callback patterns
    # if unknown, show main admin menu
    return await admin_panel_start(update, context)

# --- Admin: Categories ---
async def admin_show_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # build rows: "Category ✏️" and delete button
    keyboard = []
    for key in CATEGORIES.keys():
        display = key.replace("_", " ").title()
        keyboard.append([
            InlineKeyboardButton(f"{display} ✏️", callback_data=f"admin:cat:edit:{key}"),
            InlineKeyboardButton("🗑️", callback_data=f"admin:cat:del:{key}")
        ])
    keyboard.append([InlineKeyboardButton("➕ Add Category", callback_data="admin:cat:add")])
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="admin:open")])
    await query.edit_message_text("Manage Categories:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CATEGORY_MENU

async def admin_cat_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Send new category key (lowercase, letters/numbers, no spaces).")
    return CATEGORY_ADD

async def admin_cat_add_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    if not text.isalnum():
        await update.message.reply_text("Invalid key — use only letters and numbers, no spaces. Try again or /cancel.")
        return CATEGORY_ADD
    if text in CATEGORIES:
        await update.message.reply_text("Category already exists. Choose another key or /cancel.")
        return CATEGORY_ADD
    CATEGORIES[text] = []
    save_json(CATEGORIES_FILE, CATEGORIES)
    await update.message.reply_text(f"Category '{text}' created.")
    # go back to admin categories view
    # simulate callback to update message
    fake_query = update
    class Q: pass
    q = Q()
    q.data = "admin:categories"
    q.edit_message_text = update.message.reply_text  # safe fallback
    await admin_show_categories(q, context)
    return CATEGORY_MENU

async def admin_cat_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # callback like admin:cat:edit:<key>
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    if len(parts) < 4:
        await query.edit_message_text("Malformed callback.")
        return CATEGORY_MENU
    key = parts[3]
    if key not in CATEGORIES:
        await query.edit_message_text("Category not found.")
        return CATEGORY_MENU
    context.user_data['admin_edit_category_key'] = key
    await query.edit_message_text(f"Send new key (lowercase, letters/numbers, no spaces) to rename category '{key}', or /cancel.")
    return CATEGORY_EDIT_KEY

async def admin_cat_edit_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_key = update.message.text.strip().lower()
    old_key = context.user_data.get('admin_edit_category_key')
    if not old_key or old_key not in CATEGORIES:
        await update.message.reply_text("No category selected or it no longer exists.")
        return await admin_show_categories(update, context)
    if not new_key.isalnum():
        await update.message.reply_text("Invalid key format.")
        return CATEGORY_EDIT_KEY
    if new_key in CATEGORIES:
        await update.message.reply_text("That key already exists.")
        return CATEGORY_EDIT_KEY
    # Move category data under new key
    CATEGORIES[new_key] = CATEGORIES.pop(old_key)
    save_json(CATEGORIES_FILE, CATEGORIES)
    await update.message.reply_text(f"Category renamed {old_key} -> {new_key}")
    return await admin_show_categories(update, context)

async def admin_cat_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    key = parts[3] if len(parts) >= 4 else None
    if not key or key not in CATEGORIES:
        await query.edit_message_text("Category not found.")
        return await admin_show_categories(update, context)
    context.user_data['admin_delete_category_key'] = key
    keyboard = [
        [InlineKeyboardButton("Yes, delete", callback_data="admin:cat:confirm_del")],
        [InlineKeyboardButton("No, go back", callback_data="admin:cat:back")]
    ]
    await query.edit_message_text(f"Confirm delete category '{key}'? This will not delete item files.", reply_markup=InlineKeyboardMarkup(keyboard))
    return CATEGORY_DELETE_CONFIRM

async def admin_cat_delete_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = context.user_data.get('admin_delete_category_key')
    if not key:
        await query.edit_message_text("No category selected.")
        return await admin_show_categories(update, context)
    # Remove the category; items remain in ITEMS but orphaned (admin can reassign/delete items)
    CATEGORIES.pop(key, None)
    save_json(CATEGORIES_FILE, CATEGORIES)
    await query.edit_message_text(f"Category '{key}' deleted.")
    return await admin_show_categories(update, context)

# --- Admin: Items ---
async def admin_show_items(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = []
    for item_key, item in ITEMS.items():
        keyboard.append([
            InlineKeyboardButton(f"{item['name']} ✏️", callback_data=f"admin:item:edit:{item_key}"),
            InlineKeyboardButton("🗑️", callback_data=f"admin:item:del:{item_key}")
        ])
    keyboard.append([InlineKeyboardButton("➕ Add Item", callback_data="admin:item:add")])
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="admin:open")])
    await query.edit_message_text("Manage Items:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ITEM_MENU

async def admin_item_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Send new item key (id, no spaces, alpha-numeric).")
    return ITEM_ADD_KEY

async def admin_item_add_key_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = update.message.text.strip().lower()
    if not key.isalnum():
        await update.message.reply_text("Invalid key. Use letters/numbers, no spaces.")
        return ITEM_ADD_KEY
    if key in ITEMS:
        await update.message.reply_text("Key exists. Choose another.")
        return ITEM_ADD_KEY
    context.user_data['new_item_key'] = key
    await update.message.reply_text("Send item display name (title).")
    return ITEM_ADD_NAME

async def admin_item_add_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_item_name'] = update.message.text.strip()
    await update.message.reply_text("Send price in BTC (e.g. 0.0001).")
    return ITEM_ADD_PRICE

async def admin_item_add_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip())
        if price <= 0:
            raise ValueError
    except Exception:
        await update.message.reply_text("Invalid price. Send a positive number.")
        return ITEM_ADD_PRICE
    context.user_data['new_item_price'] = price
    await update.message.reply_text("Send file path relative to bot folder (file must exist).")
    return ITEM_ADD_PATH

async def admin_item_add_path_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    path = update.message.text.strip()
    if not os.path.exists(path):
        await update.message.reply_text("File does not exist at that path. Upload file to server and retry.")
        return ITEM_ADD_PATH
    context.user_data['new_item_path'] = path
    # Ask which category to assign
    keyboard = [[InlineKeyboardButton(k.title(), callback_data=f"admin:assign_cat:{k}")] for k in CATEGORIES.keys()]
    keyboard.append([InlineKeyboardButton("Create new category", callback_data="admin:cat:add")])
    await update.message.reply_text("Choose a category for this item:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ITEM_ADD_CATEGORY

async def admin_item_add_category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "admin:cat:add":
        # switch to category add flow
        return await admin_cat_add_start(update, context)
    _, _, cat = data.split(":", 2)
    key = context.user_data.get('new_item_key')
    name = context.user_data.get('new_item_name')
    price = context.user_data.get('new_item_price')
    path = context.user_data.get('new_item_path')
    if not all([key, name, price, path]):
        await query.edit_message_text("Missing data. Aborting.")
        return await admin_show_items(update, context)
    # save item
    ITEMS[key] = {"name": name, "price_btc": price, "file_path": path}
    CATEGORIES.setdefault(cat, []).append(key)
    save_json(ITEMS_FILE, ITEMS)
    save_json(CATEGORIES_FILE, CATEGORIES)
    await query.edit_message_text(f"Item '{name}' added to category '{cat}'.")
    return await admin_show_items(update, context)

async def admin_item_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    if len(parts) < 4:
        await query.edit_message_text("Malformed callback.")
        return await admin_show_items(update, context)
    item_key = parts[3]
    if item_key not in ITEMS:
        await query.edit_message_text("Item not found.")
        return await admin_show_items(update, context)
    context.user_data['admin_edit_item_key'] = item_key
    keyboard = [
        [InlineKeyboardButton("Edit Name", callback_data="admin:item:field:name")],
        [InlineKeyboardButton("Edit Price (BTC)", callback_data="admin:item:field:price_btc")],
        [InlineKeyboardButton("Edit File Path", callback_data="admin:item:field:file_path")],
        [InlineKeyboardButton("Move Category", callback_data="admin:item:field:category")],
        [InlineKeyboardButton("⬅️ Back", callback_data="admin:items")]
    ]
    item = ITEMS[item_key]
    text = f"Editing item *{item_key}*:\nName: {item['name']}\nPrice: {item['price_btc']}\nPath: {item['file_path']}"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return ITEM_EDIT_SELECT

async def admin_item_field_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    field = parts[-1]
    context.user_data['admin_edit_field'] = field
    if field == "category":
        # show categories to pick
        keyboard = [[InlineKeyboardButton(k.title(), callback_data=f"admin:item:move:{k}")] for k in CATEGORIES.keys()]
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="admin:items")])
        await query.edit_message_text("Choose new category:", reply_markup=InlineKeyboardMarkup(keyboard))
        return ITEM_EDIT_FIELD_SELECT
    else:
        await query.edit_message_text(f"Send new value for *{field}* (or /cancel):", parse_mode="Markdown")
        return ITEM_EDIT_FIELD_SELECT

async def admin_item_field_value_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item_key = context.user_data.get('admin_edit_item_key')
    field = context.user_data.get('admin_edit_field')
    if not item_key or not field:
        await update.message.reply_text("No item/field selected.")
        return await admin_show_items(update, context)
    text = update.message.text.strip()
    if field == "price_btc":
        try:
            val = float(text)
            if val <= 0:
                raise ValueError
        except Exception:
            await update.message.reply_text("Invalid price. Try again.")
            return ITEM_EDIT_FIELD_VALUE
        ITEMS[item_key][field] = val
    elif field == "file_path":
        if not os.path.exists(text):
            await update.message.reply_text("Path does not exist on server. Upload file first.")
            return ITEM_EDIT_FIELD_VALUE
        ITEMS[item_key][field] = text
    else:
        ITEMS[item_key][field] = text
    save_json(ITEMS_FILE, ITEMS)
    await update.message.reply_text(f"Updated {field} for {item_key}.")
    return await admin_show_items(update, context)

async def admin_item_move_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    new_cat = parts[-1]
    item_key = context.user_data.get('admin_edit_item_key')
    # remove from old category
    for cat, items in CATEGORIES.items():
        if item_key in items:
            items.remove(item_key)
    # add to new
    CATEGORIES.setdefault(new_cat, []).append(item_key)
    save_json(CATEGORIES_FILE, CATEGORIES)
    await query.edit_message_text(f"Moved item {item_key} to category {new_cat}.")
    return await admin_show_items(update, context)

async def admin_item_delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    item_key = parts[3] if len(parts) >= 4 else None
    if not item_key or item_key not in ITEMS:
        await query.edit_message_text("Item not found.")
        return await admin_show_items(update, context)
    context.user_data['admin_delete_item_key'] = item_key
    keyboard = [
        [InlineKeyboardButton("Yes, delete", callback_data="admin:item:confirm_del")],
        [InlineKeyboardButton("No, back", callback_data="admin:items")]
    ]
    await query.edit_message_text(f"Confirm delete item '{item_key}'?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ITEM_DELETE_CONFIRM

async def admin_item_delete_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    item_key = context.user_data.get('admin_delete_item_key')
    if not item_key or item_key not in ITEMS:
        await query.edit_message_text("Item not found.")
        return await admin_show_items(update, context)
    # remove from ITEMS and from categories
    ITEMS.pop(item_key, None)
    for items in CATEGORIES.values():
        if item_key in items:
            items.remove(item_key)
    save_json(ITEMS_FILE, ITEMS)
    save_json(CATEGORIES_FILE, CATEGORIES)
    await query.edit_message_text(f"Item '{item_key}' deleted.")
    return await admin_show_items(update, context)

# ---------- Small helper to wire admin callbacks ----------
async def generic_admin_callback_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Central dispatch for admin:... callback_data values. Called from the main callback router."""
    query = update.callback_query
    data = query.data  # e.g., admin:cat:add, admin:cat:edit:news
    if data == "admin:cat:add":
        return await admin_cat_add_start(update, context)
    if data.startswith("admin:cat:edit:"):
        return await admin_cat_edit_start(update, context)
    if data.startswith("admin:cat:del:"):
        return await admin_cat_delete_confirm(update, context)
    if data == "admin:cat:confirm_del":
        return await admin_cat_delete_execute(update, context)
    if data == "admin:cat:back":
        return await admin_show_categories(update, context)

    if data == "admin:item:add":
        return await admin_item_add_start(update, context)
    if data.startswith("admin:item:edit:"):
        return await admin_item_edit_start(update, context)
    if data.startswith("admin:item:del:"):
        return await admin_item_delete_confirm(update, context)
    if data == "admin:item:confirm_del":
        return await admin_item_delete_execute(update, context)

    if data.startswith("admin:item:field:"):
        return await admin_item_field_select(update, context)
    if data.startswith("admin:item:move:"):
        return await admin_item_move_category(update, context)

    if data == "admin:categories" or data == "admin:open":
        return await admin_show_categories(update, context)
    if data == "admin:items":
        return await admin_show_items(update, context)

    # fallback: show admin panel
    return await admin_panel_start(update, context)

# ---------- Application setup ----------
def build_application():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # start command
    app.add_handler(CommandHandler("start", cmd_start))
    # confirm command for checking payment
    app.add_handler(CommandHandler("confirm", cmd_confirm))

    # main callback router
    app.add_handler(CallbackQueryHandler(callback_router))

    # admin text input flows (category add, item add, edit flows)
    # Message handlers for non-callback text during admin flows:
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_handler))

    # Map specific flows (we'll use ConversationHandler to manage states)
    conv = ConversationHandler(
        entry_points=[CommandHandler("admin", lambda u, c: admin_panel_start(u, c) if is_admin_user(u) else u.message.reply_text("Not authorized."))],
        states={
            # Category flows
            CATEGORY_ADD: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_cat_add_receive)],
            CATEGORY_EDIT_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_cat_edit_receive)],
            # Item add flows
            ITEM_ADD_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_item_add_key_received)],
            ITEM_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_item_add_name_received)],
            ITEM_ADD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_item_add_price_received)],
            ITEM_ADD_PATH: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_item_add_path_received)],
            # Item edit value
            ITEM_EDIT_FIELD_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_item_field_value_received)],
            # fallback cancel
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: u.message.reply_text("Cancelled."))],
        allow_reentry=True
    )
    app.add_handler(conv)

    # CallbackQuery map for admin-specific callback_data patterns:
    # We route in the general callback router which calls generic_admin_callback_dispatch when needed.
    # But we can also add a specific handler to catch admin:... data quickly:
    app.add_handler(CallbackQueryHandler(generic_admin_callback_dispatch, pattern="^admin:"))

    return app

# Helper message handler used in conjunction with conversation states
async def admin_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """This tries to route text messages to the relevant step based on user_data flags."""
    # If we're currently in an admin flow that expects text, let ConversationHandler handle it.
    # Otherwise, ignore — this simple handler ensures messages don't fall through.
    # We don't implement a full dispatcher here to avoid duplicating the ConversationHandler logic.
    # So this handler will be a no-op; the ConversationHandler handles the actual admin input states above.
    return

# ---------- Run ----------
if __name__ == "__main__":
    # ensure data files exist
    save_json(ITEMS_FILE, ITEMS)
    save_json(CATEGORIES_FILE, CATEGORIES)

    app = build_application()
    if os.environ.get("RENDER"):  # simple Render detection
        port = int(os.environ.get("PORT", 5000))
        webhook_url = f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}/{TELEGRAM_TOKEN}"
        app.run_webhook(listen="0.0.0.0", port=port, url_path=TELEGRAM_TOKEN, webhook_url=webhook_url)
    else:
        print("Starting bot (polling)...")
        app.run_polling()
