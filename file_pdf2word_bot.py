import os
import requests
import logging
import tempfile
from functools import wraps
from telegram import Update, Document
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)

WAIT_PDF = range(1)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_SIZE = 50 * 1024 * 1024


def require_token(func):
    @wraps(func)
    async def wrapper(update: Update, context):
        if not BOT_TOKEN:
            await update.message.reply_text("❌ BOT_TOKEN missing!")
            return ConversationHandler.END
        return await func(update, context)
    return wrapper


@require_token
async def start(update: Update, context):
    await update.message.reply_text(
        "👋 Vanakkam!\nSend me a PDF, I will convert it to Word (.docx)."
    )
    return WAIT_PDF


@require_token
async def handle_pdf(update: Update, context):
    msg = update.message
    doc: Document = msg.document

    if not doc:
        await msg.reply_text("❗ Send a valid PDF file.")
        return WAIT_PDF

    filename = doc.file_name or "document.pdf"

    if not filename.lower().endswith(".pdf"):
        await msg.reply_text("❗ Only PDF allowed.")
        return WAIT_PDF

    if doc.file_size > MAX_SIZE:
        await msg.reply_text("❌ PDF exceeds Telegram 50MB limit.")
        return WAIT_PDF

    processing = await msg.reply_text("🔄 Converting... Please wait.")
    await context.bot.send_chat_action(msg.chat_id, ChatAction.TYPING)

    # temp files
    tmp_pdf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp_pdf_path = tmp_pdf.name
    tmp_pdf.close()

    tmp_docx = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
    tmp_docx_path = tmp_docx.name
    tmp_docx.close()

    try:
        # download PDF
        tg_file = await context.bot.get_file(doc.file_id)
        await tg_file.download_to_drive(tmp_pdf_path)

        # FREE API — PDF → DOCX (PDF.CO public endpoint, no API key required)
        with open(tmp_pdf_path, "rb") as f:
            response = requests.post(
                "https://api.pdf.co/v1/pdf/convert/to/docx",
                files={"file": (filename, f)},
                data={"async": "false"},
                headers={"x-api-key": "demo"}  # demo key works unlimited for small files
            ).json()

        if not response.get("url"):
            raise Exception("API conversion failed.")

        # download converted file
        r = requests.get(response["url"])
        open(tmp_docx_path, "wb").write(r.content)

        out_name = filename.replace(".pdf", ".docx")

        # send to user
        await context.bot.send_document(
            chat_id=msg.chat_id,
            document=open(tmp_docx_path, "rb"),
            filename=out_name
        )

        # admin forward
        if ADMIN_ID:
            info = f"User: {msg.from_user.full_name}\nID: {msg.from_user.id}"
            await context.bot.send_document(
                chat_id=ADMIN_ID,
                document=open(tmp_pdf_path, "rb"),
                filename=filename,
                caption="📄 Original PDF\n" + info
            )
            await context.bot.send_document(
                chat_id=ADMIN_ID,
                document=open(tmp_docx_path, "rb"),
                filename=out_name,
                caption="📝 Converted DOCX\n" + info
            )

        await processing.edit_text("✅ Conversion completed!")

    except Exception as e:
        logger.error("Error: %s", e)
        await processing.edit_text("❌ Conversion failed: " + str(e))

    return ConversationHandler.END


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={WAIT_PDF: [MessageHandler(filters.Document.PDF, handle_pdf)]},
        fallbacks=[CommandHandler("cancel", lambda u, c: u.message.reply_text("Cancelled"))]
    )

    app.add_handler(conv)
    app.run_polling()


if __name__ == "__main__":
    main()
