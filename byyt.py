import asyncio
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

# ===== Configuration Variables =====
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
ZLIB_EMAIL = "your_email@example.com"
ZLIB_PASSWORD = "your_password"
GITHUB_REPO = "github.com/WalkTheEarth/BookDLBot"

# Bot states
SEARCH_QUERY, DOWNLOAD_QUERY = range(2)

# ===== Bot Implementation =====
class ZLibraryBot:
    def __init__(self, token: str):
        self.token = token
        self.lib = None
        self.current_results = None

    async def login_to_zlib(self):
        """Login to Z-Library"""
        self.lib = zlibrary.AsyncZlib()
        await self.lib.login(ZLIB_EMAIL, ZLIB_PASSWORD)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a welcome message when the command /start is issued."""
        await update.message.reply_text(
            "Welcome to Z-Library Bot!\n"
            "Use /search to find books or /download to download them.\n"
            "This bot is open source! Use /OpenSource to learn more."
        )

    async def opensource_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show information about the bot being open source."""
        await update.message.reply_text(
            f"This bot is FOSS! Check out the code at {GITHUB_REPO}"
        )

    async def search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ask user for search query."""
        await update.message.reply_text("What book would you like to find?")
        return SEARCH_QUERY

    async def download_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ask user for download query."""
        await update.message.reply_text("What book would you like to download?")
        return DOWNLOAD_QUERY

    async def handle_search_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the search query and display results."""
        query = update.message.text
        await update.message.reply_text(f"Searching for: {query}...")

        try:
            if not self.lib:
                await self.login_to_zlib()

            paginator = await self.lib.search(q=query, count=5)
            first_set = await paginator.next()
            self.current_results = paginator.result

            if not self.current_results:
                await update.message.reply_text("No results found.")
                return ConversationHandler.END

            # Display results with inline buttons
            keyboard = []
            for idx, book in enumerate(self.current_results):
                keyboard.append([
                    InlineKeyboardButton(
                        f"{idx+1}. {book['name']} ({book['year']})",
                        callback_data=f"book_{idx}"
                    )
                ])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"Found {len(self.current_results)} results:",
                reply_markup=reply_markup
            )

        except Exception as e:
            await update.message.reply_text(f"An error occurred: {str(e)}")
            return ConversationHandler.END

        return ConversationHandler.END

    async def handle_download_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the download query and display results."""
        query = update.message.text
        await update.message.reply_text(f"Searching for: {query}...")

        try:
            if not self.lib:
                await self.login_to_zlib()

            paginator = await self.lib.search(q=query, count=5)
            first_set = await paginator.next()
            self.current_results = paginator.result

            if not self.current_results:
                await update.message.reply_text("No results found.")
                return ConversationHandler.END

            # Display results with download buttons
            keyboard = []
            for idx, book in enumerate(self.current_results):
                keyboard.append([
                    InlineKeyboardButton(
                        f"📥 {book['name']} ({book['year']})",
                        callback_data=f"dl_{idx}"
                    )
                ])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"Found {len(self.current_results)} results. Click to download:",
                reply_markup=reply_markup
            )

        except Exception as e:
            await update.message.reply_text(f"An error occurred: {str(e)}")
            return ConversationHandler.END

        return ConversationHandler.END

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks for book selection/download."""
        query = update.callback_query
        await query.answer()

        if query.data.startswith("book_"):
            # Handle book info display
            idx = int(query.data.split("_")[1])
            book = self.current_results[idx]
            
            authors = ", ".join([author['author'] for author in book['authors']])
            message = (
                f"📚 <b>{book['name']}</b>\n"
                f"👤 <i>{authors}</i>\n"
                f"📅 {book['year']} | {book['language']} | {book['extension']}\n"
                f"📏 {book['size']}\n"
                f"⭐ {book['rating']}\n"
                f"🔗 <a href='{book['url']}'>View on Z-Library</a>"
            )
            
            # Send cover if available
            if book.get('cover'):
                await query.message.reply_photo(
                    photo=book['cover'],
                    caption=message,
                    parse_mode='HTML'
                )
            else:
                await query.message.reply_text(message, parse_mode='HTML')

        elif query.data.startswith("dl_"):
            # Handle download
            idx = int(query.data.split("_")[1])
            book = self.current_results[idx]
            
            await query.message.reply_text(f"Preparing download for: {book['name']}...")
            
            try:
                # Fetch full book details to get download URL
                full_book = await book.fetch()
                download_url = full_book['download_url']
                
                await query.message.reply_text(
                    f"📥 <b>{book['name']}</b>\n"
                    f"🔗 <a href='{download_url}'>Click to download</a>\n"
                    f"💾 Format: {book['extension']} | Size: {book['size']}",
                    parse_mode='HTML'
                )
            except Exception as e:
                await query.message.reply_text(f"Failed to get download link: {str(e)}")

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel the current operation."""
        await update.message.reply_text("Operation cancelled.")
        return ConversationHandler.END

    def run(self):
        """Run the bot."""
        application = Application.builder().token(self.token).build()

        # Conversation handler for search
        search_conv_handler = ConversationHandler(
            entry_points=[CommandHandler("search", self.search_command)],
            states={
                SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_search_query)]
            },
            fallbacks=[CommandHandler("cancel", self.cancel)]
        )

        # Conversation handler for download
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
        application.run_polling()


if __name__ == "__main__":
    bot = ZLibraryBot(BOT_TOKEN)
    bot.run()