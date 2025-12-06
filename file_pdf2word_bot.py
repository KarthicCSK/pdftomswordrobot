import os
import logging
import tempfile
import subprocess
from functools import wraps
from telegram import Update, Document
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters
)
from telegram.constants import ChatAction  # FIXED IMPORT

# States
WAIT_PDF = range(1)

# Env Vars
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_SIZE = 50 * 1024 * 1024  # 50MB Telegram Bot API Limit


def require_token(fn):
    @wraps(fn)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not BOT_TOKEN:
            await update.message.reply_text("❌ BOT_TOKEN missing. Configure in Railway.")
            return ConversationHandler.END
        return await fn(update, context)
    return wrapper


@require_token
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Vanakkam!\n\n📄 Send a PDF file.\n"
        "I will convert it into Word (.docx).\n\n"
        "❌ /cancel to stop."
    )
    return WAIT_PDF


@require_token
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    doc: Document = message.document

    if not doc:
        await message.reply_text("❗ Please send a valid PDF file.")
        return WAIT_PDF

    filename = doc.file_name
    mime = doc.mime_type or ""

    # Must be PDF
    if "pdf" not in mime.lower() and not filename.lower().endswith(".pdf"):
        await message.reply_text("⚠ This bot only converts PDF files.")
        return WAIT_PDF

    # Size Check
    if doc.file_size > MAX_SIZE:
        await message.reply_text("❌ File exceeds Telegram Bot API 50MB limit.")
        return WAIT_PDF

    # Processing message
    processing_msg = await message.reply_text("🔄 Converting... Please wait.")
    await context.bot.send_chat_action(message.chat_id, ChatAction.TYPING)

    bot = context.bot

    # Temp files
    tmp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp_outdir = tempfile.mkdtemp()
    tmp_pdf.close()

    pdf_path = tmp_pdf.name
    word_path = os.path.join(tmp_outdir, filename.replace(".pdf", ".docx"))

    try:
        # Download PDF
        telegram_file = await bot.get_file(doc.file_id)
        await telegram_file.download_to_drive(custom_path=pdf_path)

        # Run LibreOffice Conversion
        subprocess.run(
            [
                "soffice", "--headless", "--convert-to", "docx",
                pdf_path, "--outdir", tmp_outdir
            ],
            check=True
        )

        # Send converted file to user
        await bot.send_document(
            chat_id=message.chat_id,
            document=open(word_path, "rb"),
            filename=os.path.basename(word_path)
        )

        # Send to Admin
        if ADMIN_ID != 0:
            caption = f"📨 Converted PDF from {message.from_user.full_name}\nUser ID: {message.from_user.id}"
            await bot.send_document(
                chat_id=ADMIN_ID, document=open(pdf_path, "rb"),
                filename=filename, caption="📄 Original PDF\n" + caption
            )
            await bot.send_document(
                chat_id=ADMIN_ID, document=open(word_path, "rb"),
                filename=os.path.basename(word_path), caption="📝 Converted DOCX\n" + caption
            )

        await processing_msg.edit_text("✅ Conversion Completed!")

    except Exception as e:
        logger.exception("Conversion failed")
        await processing_msg.edit_text("❌ Conversion failed: " + str(e))

    return ConversationHandler.END


@require_token
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAIT_PDF: [
                MessageHandler(filters.Document.PDF | filters.Document.ALL, handle_pdf)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    app.add_handler(conv)
    app.run_polling()


if __name__ == "__main__":
    main()
