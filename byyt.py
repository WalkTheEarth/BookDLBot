import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler
)
import zlibrary
from httpx import ReadTimeout
from telegram.error import TimedOut, NetworkError

# ===== Configuration =====
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
ZLIB_EMAIL = "your_email@example.com"
ZLIB_PASSWORD = "your_password"
GITHUB_REPO = "github.com/WalkTheEarth/BookDLBot"
REQUEST_TIMEOUT = 30  # seconds

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot states
SEARCH_QUERY, DOWNLOAD_QUERY = range(2)

class ZLibraryBot:
    def __init__(self, token: str):
        self.token = token
        self.lib = None
        self.current_results = None
        self.retry_count = 0
        self.max_retries = 3

    async def safe_zlib_request(self, func, *args, **kwargs):
        """Wrapper for Z-Library requests with retry logic"""
        last_error = None
        for attempt in range(self.max_retries):
            try:
                if not self.lib:
                    await self.login_to_zlib()
                return await func(*args, **kwargs)
            except (ReadTimeout, NetworkError, TimedOut) as e:
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                last_error = e
                await asyncio.sleep(2)  # Wait before retrying
            except Exception as e:
                logger.error(f"Unexpected error: {str(e)}")
                last_error = e
                break
        
        raise last_error if last_error else Exception("Max retries reached")

    async def login_to_zlib(self):
        """Login to Z-Library with retry logic"""
        self.lib = zlibrary.AsyncZlib()
        try:
            await self.safe_zlib_request(self.lib.login, ZLIB_EMAIL, ZLIB_PASSWORD)
            return True
        except Exception as e:
            logger.error(f"Login failed: {str(e)}")
            self.lib = None
            return False

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a welcome message"""
        try:
            await update.message.reply_text(
                "📚 Welcome to Z-Library Bot!\n\n"
                "🔍 Use /search to find books\n"
                "📥 Use /download to download books\n"
                "ℹ️ Use /opensource to view the source code"
                "ℹ️ You need to log into the z-library before starting. 'z-library.sk'"
            )
        except Exception as e:
            logger.error(f"Error in start: {str(e)}")

    async def opensource_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show open source info"""
        try:
            await update.message.reply_text(
                f"🔓 This bot is open source!\n\n"
                f"💻 Check out the code at:\n{GITHUB_REPO}"
            )
        except Exception as e:
            logger.error(f"Error in opensource: {str(e)}")

    async def search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ask for search query"""
        try:
            await update.message.reply_text("🔍 What book would you like to find?")
            return SEARCH_QUERY
        except Exception as e:
            logger.error(f"Error in search_command: {str(e)}")
            return ConversationHandler.END

    async def download_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ask for download query"""
        try:
            await update.message.reply_text("📥 What book would you like to download?")
            return DOWNLOAD_QUERY
        except Exception as e:
            logger.error(f"Error in download_command: {str(e)}")
            return ConversationHandler.END

    async def process_book_results(self, results):
        """Process raw book results into consistent format"""
        processed = []
        for book in results:
            try:
                authors = ""
                if 'authors' in book:
                    if isinstance(book['authors'], list):
                        if book['authors'] and isinstance(book['authors'][0], dict):
                            authors = ", ".join([a.get('author', '') for a in book['authors']])
                        else:
                            authors = ", ".join(book['authors'])
                    elif isinstance(book['authors'], str):
                        authors = book['authors']
                
                processed.append({
                    'id': book.get('id', ''),
                    'name': book.get('name', 'Unknown Title'),
                    'authors': authors,
                    'year': book.get('year', 'Unknown Year'),
                    'language': book.get('language', 'Unknown'),
                    'extension': book.get('extension', ''),
                    'size': book.get('size', ''),
                    'rating': book.get('rating', 'N/A'),
                    'url': book.get('url', ''),
                    'cover': book.get('cover', None),
                    'raw': book
                })
            except Exception as e:
                logger.error(f"Error processing book: {str(e)}")
                continue
        return processed

    async def handle_search_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle search query"""
        try:
            query = update.message.text
            await update.message.reply_text(f"🔍 Searching for: {query}...")

            if not await self.login_to_zlib():
                await update.message.reply_text("❌ Failed to connect to Z-Library. Please try again later.")
                return ConversationHandler.END

            paginator = await self.safe_zlib_request(self.lib.search, q=query, count=5)
            first_set = await self.safe_zlib_request(paginator.next)
            raw_results = paginator.result
            self.current_results = await self.process_book_results(raw_results)

            if not self.current_results:
                await update.message.reply_text("❌ No results found. Try a different search term.")
                return ConversationHandler.END

            keyboard = []
            for idx, book in enumerate(self.current_results):
                btn_text = f"{idx+1}. {book['name']}"
                if book['year'] != 'Unknown Year':
                    btn_text += f" ({book['year']})"
                keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"book_{idx}")])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"📚 Found {len(self.current_results)} results:",
                reply_markup=reply_markup
            )

        except Exception as e:
            logger.error(f"Error in handle_search_query: {str(e)}")
            await update.message.reply_text("❌ Search failed due to a timeout. Please try again.")
            return ConversationHandler.END

        return ConversationHandler.END

    async def handle_download_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle download query"""
        try:
            query = update.message.text
            await update.message.reply_text(f"🔍 Searching for: {query}...")

            if not await self.login_to_zlib():
                await update.message.reply_text("❌ Failed to connect to Z-Library. Please try again later.")
                return ConversationHandler.END

            paginator = await self.safe_zlib_request(self.lib.search, q=query, count=5)
            first_set = await self.safe_zlib_request(paginator.next)
            raw_results = paginator.result
            self.current_results = await self.process_book_results(raw_results)

            if not self.current_results:
                await update.message.reply_text("❌ No results found. Try a different search term.")
                return ConversationHandler.END

            keyboard = []
            for idx, book in enumerate(self.current_results):
                btn_text = f"📥 {book['name']}"
                if book['year'] != 'Unknown Year':
                    btn_text += f" ({book['year']})"
                keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"dl_{idx}")])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"📚 Found {len(self.current_results)} results. Click to download:",
                reply_markup=reply_markup
            )

        except Exception as e:
            logger.error(f"Error in handle_download_query: {str(e)}")
            await update.message.reply_text("❌ Search failed due to a timeout. Please try again.")
            return ConversationHandler.END

        return ConversationHandler.END

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        try:
            query = update.callback_query
            await query.answer()

            if not self.current_results:
                await query.message.reply_text("❌ Session expired. Please perform a new search.")
                return

            action, idx = query.data.split("_")
            idx = int(idx)
            book = self.current_results[idx]

            if action == "book":
                message = (
                    f"📚 <b>{book['name']}</b>\n"
                    f"👤 <i>{book['authors']}</i>\n"
                    f"📅 {book['year']} | {book['language']} | {book['extension']}\n"
                    f"📏 {book['size']}\n"
                    f"⭐ {book['rating']}\n"
                    f"🔗 <a href='{book['url']}'>View on Z-Library</a>"
                )
                
                if book['cover']:
                    await query.message.reply_photo(
                        photo=book['cover'],
                        caption=message,
                        parse_mode='HTML'
                    )
                else:
                    await query.message.reply_text(message, parse_mode='HTML')

            elif action == "dl":
                await query.message.reply_text(f"⏳ Preparing download for: {book['name']}...")
                
                try:
                    full_book = await self.safe_zlib_request(book['raw'].fetch)
                    download_url = full_book.get('download_url', '')
                    
                    if download_url:
                        await query.message.reply_text(
                            f"📥 <b>{book['name']}</b>\n"
                            f"🔗 <a href='{download_url}'>Click to download</a>\n"
                            f"💾 Format: {book['extension']} | Size: {book['size']}",
                            parse_mode='HTML'
                        )
                    else:
                        await query.message.reply_text("❌ Could not retrieve download link. The book may not be available.")
                except Exception as e:
                    logger.error(f"Download failed: {str(e)}")
                    await query.message.reply_text("❌ Download failed due to a timeout. Please try again.")

        except Exception as e:
            logger.error(f"Error in button_callback: {str(e)}")
            try:
                await query.message.reply_text("❌ An error occurred. Please try again.")
            except:
                pass

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel current operation"""
        try:
            await update.message.reply_text("❌ Operation cancelled.")
        except Exception as e:
            logger.error(f"Error in cancel: {str(e)}")
        return ConversationHandler.END

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors in the telegram bot"""
        error = context.error
        logger.error(f"Update {update} caused error {error}", exc_info=error)
        
        if isinstance(error, (TimedOut, ReadTimeout, NetworkError)):
            error_msg = "⌛ The operation timed out. Please try again."
        else:
            error_msg = "❌ An unexpected error occurred. Please try again."

        try:
            if update and hasattr(update, 'message'):
                await update.message.reply_text(error_msg)
        except Exception as e:
            logger.error(f"Error in error_handler while sending message: {str(e)}")

    def run(self):
        """Run the bot with proper timeout settings"""
        application = Application.builder() \
            .token(self.token) \
            .read_timeout(REQUEST_TIMEOUT) \
            .write_timeout(REQUEST_TIMEOUT) \
            .pool_timeout(REQUEST_TIMEOUT) \
            .connect_timeout(REQUEST_TIMEOUT) \
            .build()

        # Add error handler first
        application.add_error_handler(self.error_handler)

        # Conversation handlers
        search_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("search", self.search_command)],
            states={
                SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_search_query)]
            },
            fallbacks=[CommandHandler("cancel", self.cancel)]
        )

        download_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("download", self.download_command)],
            states={
                DOWNLOAD_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_download_query)]
            },
            fallbacks=[CommandHandler("cancel", self.cancel)]
        )

        # Add handlers
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("opensource", self.opensource_command))
        application.add_handler(search_conv_handler)
        application.add_handler(download_conv_handler)
        application.add_handler(CallbackQueryHandler(self.button_callback))

        # Run the bot
        logger.info("🤖 Bot is running with improved timeout handling...")
        application.run_polling()

if __name__ == "__main__":
    bot = ZLibraryBot(BOT_TOKEN)
    bot.run()
