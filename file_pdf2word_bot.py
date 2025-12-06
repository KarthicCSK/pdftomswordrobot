# file_pdf2word_bot.py
import os
import logging
import tempfile
from io import BytesIO
from functools import wraps

from telegram import Update, Document, ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from pdf2docx import Converter

# States
WAIT_PDF, WAIT_CONFIRM = range(2)

# Environment variables (set these in Railway)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# Limits
TELEGRAM_BOT_API_MAX = 50 * 1024 * 1024  # 50 MB

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def require_token(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not BOT_TOKEN:
            if update and update.message:
                await update.message.reply_text("❌ BOT_TOKEN not configured. Contact the bot owner.")
            return ConversationHandler.END
        return await func(update, context)
    return wrapped


@require_token
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Vanakkam!\n\n"
        "📄 Send me a PDF file and I will convert it to a Word (.docx) file.\n"
        "Files larger than 50 MB cannot be handled by this bot (Telegram Bot API limit).\n\n"
        "Send a PDF now, or /cancel to stop."
    )
    return WAIT_PDF


@require_token
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    doc: Document = msg.document

    if not doc:
        await msg.reply_text("❗ Please send a PDF document.")
        return WAIT_PDF

    # Ensure it's a PDF
    mime = doc.mime_type or ""
    filename = doc.file_name or "file.pdf"
    if not (filename.lower().endswith(".pdf") or "pdf" in mime.lower()):
        await msg.reply_text("❗ This bot only converts PDF files. Please send a .pdf file.")
        return WAIT_PDF

    # Size check
    file_size = doc.file_size or 0
    if file_size > TELEGRAM_BOT_API_MAX:
        await msg.reply_text(
            "❌ This file is too large for Telegram Bot API (limit: 50 MB). "
            "Please use a smaller file or upload to cloud and share a link."
        )
        return WAIT_PDF

    # Acknowledge and show processing state
    processing = await msg.reply_text("🔄 Received PDF. Processing... Please wait.")
    await context.bot.send_chat_action(chat_id=msg.chat_id, action=ChatAction.UPLOAD_DOCUMENT)

    # Download PDF to temp file
    bot = context.bot
    tf_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tf_docx = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
    tf_pdf_path = tf_pdf.name
    tf_docx_path = tf_docx.name
    tf_pdf.close()
    tf_docx.close()

    try:
        file = await bot.get_file(doc.file_id)
        await file.download_to_drive(custom_path=tf_pdf_path)

        # Convert PDF -> DOCX using pdf2docx
        conv = Converter(tf_pdf_path)
        conv.convert(tf_docx_path, start=0, end=None)
        conv.close()

        # Send converted docx back to user
        with open(tf_docx_path, "rb") as f:
            await bot.send_document(chat_id=msg.chat_id, document=f, filename=filename.rsplit(".", 1)[0] + ".docx")

        # Forward original PDF + converted DOCX to admin (if ADMIN_ID set)
        if ADMIN_ID != 0:
            admin_caption = (
                f"User: {msg.from_user.full_name} (id: {msg.from_user.id}, username: @{msg.from_user.username or 'N/A'})\n"
                f"Original: {filename}"
            )
            # send original
            with open(tf_pdf_path, "rb") as fpdf:
                await bot.send_document(chat_id=ADMIN_ID, document=fpdf, filename=filename, caption="Original PDF\n" + admin_caption)
            # send converted
            with open(tf_docx_path, "rb") as fdocx:
                await bot.send_document(chat_id=ADMIN_ID, document=fdocx, filename=filename.rsplit(".",1)[0] + ".docx", caption="Converted DOCX\n" + admin_caption)

        # Edit processing message to success
        await processing.edit_text("✅ Conversion completed — sent the .docx to you. Admin has been notified.")
    except Exception as e:
        logger.exception("Conversion error")
        try:
            await processing.edit_text("❌ Conversion failed: " + str(e))
        except:
            pass
    finally:
        # cleanup temp files
        try:
            os.remove(tf_pdf_path)
        except Exception:
            pass
        try:
            os.remove(tf_docx_path)
        except Exception:
            pass

    return ConversationHandler.END


@require_token
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("❌ Operation cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start), MessageHandler(filters.Document.PDF, handle_document)],
        states={
            WAIT_PDF: [MessageHandler(filters.Document.PDF | filters.Document.ALL, handle_document)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv)

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
