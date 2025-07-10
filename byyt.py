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

class ZLibraryBot:
    def __init__(self, token: str):
        self.token = token
        self.lib = None
        self.current_results = None

    async def login_to_zlib(self):
        """Login to Z-Library"""
        if not self.lib:
            self.lib = zlibrary.AsyncZlib()
            try:
                await self.lib.login(ZLIB_EMAIL, ZLIB_PASSWORD)
                return True
            except Exception as e:
                print(f"Login failed: {e}")
                return False
        return True

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a welcome message when the command /start is issued."""
        await update.message.reply_text(
            "📚 Welcome to Z-Library Bot!\n\n"
            "🔍 Use /search to find books\n"
            "📥 Use /download to download books\n"
            "ℹ️ Use /opensource to view the source code"
        )

    async def opensource_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show information about the bot being open source."""
        await update.message.reply_text(
            f"🔓 This bot is open source!\n\n"
            f"💻 Check out the code at:\n{GITHUB_REPO}"
        )

    async def search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ask user for search query."""
        await update.message.reply_text("🔍 What book would you like to find?")
        return SEARCH_QUERY

    async def download_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Ask user for download query."""
        await update.message.reply_text("📥 What book would you like to download?")
        return DOWNLOAD_QUERY

    async def process_book_results(self, results):
        """Process raw book results into a consistent format."""
        processed = []
        for book in results:
            # Handle authors field
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
                'raw': book  # Keep original data for fetching
            })
        return processed

    async def handle_search_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the search query and display results."""
        query = update.message.text
        await update.message.reply_text(f"🔍 Searching for: {query}...")

        try:
            if not await self.login_to_zlib():
                await update.message.reply_text("❌ Failed to connect to Z-Library. Please try again later.")
                return ConversationHandler.END

            paginator = await self.lib.search(q=query, count=5)
            first_set = await paginator.next()
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
            await update.message.reply_text(f"❌ An error occurred during search: {str(e)}")
            return ConversationHandler.END

        return ConversationHandler.END

    async def handle_download_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the download query and display results."""
        query = update.message.text
        await update.message.reply_text(f"🔍 Searching for: {query}...")

        try:
            if not await self.login_to_zlib():
                await update.message.reply_text("❌ Failed to connect to Z-Library. Please try again later.")
                return ConversationHandler.END

            paginator = await self.lib.search(q=query, count=5)
            first_set = await paginator.next()
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
            await update.message.reply_text(f"❌ An error occurred during search: {str(e)}")
            return ConversationHandler.END

        return ConversationHandler.END

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks for book selection/download."""
        query = update.callback_query
        await query.answer()

        try:
            if not self.current_results:
                await query.message.reply_text("❌ Session expired. Please perform a new search.")
                return

            action, idx = query.data.split("_")
            idx = int(idx)
            book = self.current_results[idx]

            if action == "book":
                # Display book information
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
                # Handle download
                await query.message.reply_text(f"⏳ Preparing download for: {book['name']}...")
                
                try:
                    full_book = await book['raw'].fetch()
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
                    await query.message.reply_text(f"❌ Download failed: {str(e)}")

        except Exception as e:
            await query.message.reply_text(f"❌ An error occurred: {str(e)}")

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel the current operation."""
        await update.message.reply_text("❌ Operation cancelled.")
        return ConversationHandler.END

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors in the telegram bot."""
        error_msg = f"⚠️ Update {update} caused error {context.error}"
        print(error_msg)
        
        if update and hasattr(update, 'message'):
            await update.message.reply_text("❌ An unexpected error occurred. Please try again.")

    def run(self):
        """Run the bot."""
        application = Application.builder().token(self.token).build()

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
        print("🤖 Bot is running...")
        application.run_polling()

if __name__ == "__main__":
    bot = ZLibraryBot(BOT_TOKEN)
    bot.run()
