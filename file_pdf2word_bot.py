Skip to content
Navigation Menu
KarthicCSK
pdftomswordrobot

Type / to search
Code
Issues
Pull requests
Actions
Projects
Wiki
Security
Insights
Settings
Files
Go to file
t
.gitignore
Procfile
file_pdf2word_bot.py
requirements.txt
pdftomswordrobot
/
file_pdf2word_bot.py
in
main

Edit

Preview
Indent mode

Spaces
Indent size

4
Line wrap mode

No wrap
Editing file_pdf2word_bot.py file contents
1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50
51
52
53
54
55
56
57
58
59
import os
import fitz  # PyMuPDF
import logging
import tempfile
from docx import Document as DocxDocument
from functools import wraps
from telegram import Update, Document, ReplyKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)

# States
WAIT_MODE, WAIT_PDF = range(2)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_SIZE = 50 * 1024 * 1024  # Telegram bot limit


def require_token(func):
    @wraps(func)
    async def wrapper(update: Update, context):
        if not BOT_TOKEN:
            await update.message.reply_text("❌ BOT_TOKEN missing!")
            return ConversationHandler.END
        return await func(update, context)
    return wrapper


# ==========================
# START → Show Menu
# ==========================
@require_token
async def start(update: Update, context):
    keyboard = [
        ["📄 PDF → Word"],
        ["🖼 PDF → Images"],
        ["📚 Merge PDFs", "✂ Split PDF"]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "👋 Vanakkam!\nஒரு செயல்பாட்டைத் தேர்ந்தெடுக்கவும்:",
        reply_markup=reply_markup
    )

    return WAIT_MODE


# ==========================
# ME

Use Control + Shift + m to toggle the tab key moving focus. Alternatively, use esc then tab to move to the next interactive element on the page.
