import os
import fitz  # PyMuPDF
import logging
import tempfile
from docx import Document as DocxDocument
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
        "👋 Vanakkam!\nSend me a PDF → I will convert it to a Word (.docx)."
    )
    return WAIT_PDF


@require_token
async def handle_pdf(update: Update, context):
    msg = update.message
    doc: Document = msg.document

    if not doc:
        await msg.reply_text("❗ Send a valid PDF.")
        return WAIT_PDF

    filename = doc.file_name or "document.pdf"

    if not filename.lower().endswith(".pdf"):
        await msg.reply_text("❗ Only PDF files allowed.")
        return WAIT_PDF

    if doc.file_size > MAX_SIZE:
        await msg.reply_text("❌ PDF exceeds Telegram's 50MB limit.")
        return WAIT_PDF

    processing = await msg.reply_text("🔄 Extracting text & converting... Please wait.")
    await context.bot.send_chat_action(msg.chat_id, ChatAction.TYPING)

    # Create temporary files
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

        # READ PDF using PyMuPDF
        pdf = fitz.open(tmp_pdf_path)

        # CREATE DOCX using python-docx
        word = DocxDocument()

        for i, page in enumerate(pdf):
            text = page.get_text("text")
            word.add_heading(f"Page {i+1}", level=2)
            word.add_paragraph(text)
            word.add_page_break()

        word.save(tmp_docx_path)
        pdf.close()

        out_name = filename.replace(".pdf", ".docx")

        # send to user
        await context.bot.send_document(
            chat_id=msg.chat_id,
            document=open(tmp_docx_path, "rb"),
            filename=out_name
        )

        # send to admin
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
        logger.error(str(e))
        await processing.edit_text("❌ Conversion failed: " + str(e))

    return ConversationHandler.END


def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={WAIT_PDF: [MessageHandler(filters.Document.PDF, handle_pdf)]},
        fallbacks=[CommandHandler("cancel", lambda u, c: u.message.reply_text("Cancelled."))]
    )

    app.add_handler(conv)
    app.run_polling()


if __name__ == "__main__":
    main()
