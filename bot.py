import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, \
    MessageHandler, filters
import requests
import json
from datetime import datetime
import os
from bs4 import BeautifulSoup
from typing import Dict, List

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# States for ConversationHandler
WAITING_USERNAME, WAITING_PASSWORD = range(2)

# Configuration
CONFIG = {
    "BASE_URL": "https://api.7inet.com.cn",
    "BOT_TOKEN": "7613902246:AAF8yHzFXibLc8pHS8u7M8ZH3UfXPHSlTP0",
    "ALLOWED_USER_IDS": [1880860457]  # Add your Telegram user ID here
}


class VPSManager:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': 'https://api.7inet.com.cn/'
        }

    async def login(self, username: str, password: str) -> Dict:
        """Login to 7iNet and return token"""
        login_url = f"{CONFIG['BASE_URL']}/user/oauth.do"
        login_params = {
            'code': '',
            'method': 'login.chk',
            'u': username,
            'p': password
        }

        try:
            response = requests.get(login_url, params=login_params, headers=self.headers)
            data = response.json()
            if data.get('code') == 200 and 'token' in data:
                return {'success': True, 'token': data['token']}
            return {'success': False, 'error': 'Login failed'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    async def get_instances(self, token: str) -> Dict:
        """Get VPS instances list"""
        instance_url = f"{CONFIG['BASE_URL']}/user/instance_manager.page"
        instance_params = {
            'token': token,
            'showexpired': 'false'
        }

        try:
            response = requests.get(instance_url, params=instance_params, headers=self.headers)
            soup = BeautifulSoup(response.text, 'html.parser')

            instances = []
            table = soup.find('table')
            if table:
                rows = table.find_all('tr')[1:]  # Skip header row
                for row in rows:
                    cols = row.find_all(['td'])
                    if len(cols) >= 8:
                        instance = {
                            'id': cols[0].text.strip(),
                            'name': cols[1].find('span').text.strip(),
                            'status': cols[2].find('font').text.strip(),
                            'start_time': cols[3].text.strip(),
                            'end_time': cols[4].text.strip(),
                            'username': cols[5].find('span').text.strip(),
                            'password': cols[6].find('span').text.strip()
                        }
                        instances.append(instance)
                return {'success': True, 'instances': instances}
            return {'success': False, 'error': 'No instances found'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    async def get_instance_details(self, token: str, instance_id: str) -> Dict:
        """Get detailed information about a specific VPS instance"""
        details_url = f"{CONFIG['BASE_URL']}/user/instance_control.do"
        details_params = {
            'token': token,
            'id': instance_id
        }

        try:
            response = requests.get(details_url, params=details_params, headers=self.headers)
            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract basic information
            basic_info = {}
            descriptions = soup.find_all('el-descriptions-item')
            for item in descriptions:
                label = item.get('label', '').strip()
                value = item.text.strip()
                if label and value:
                    basic_info[label] = value

            # Extract system information
            system_info = {}
            card = soup.find('el-card', {'class': 'box-card'})
            if card:
                info_text = card.text.strip()
                for line in info_text.split('\n'):
                    line = line.strip()
                    if ':' in line:
                        key, value = line.split(':', 1)
                        system_info[key.strip()] = value.strip()

            # Extract port forwarding information
            ports = []
            port_table = soup.find('table', {'class': 'table table-bordered table-hover'})
            if port_table:
                rows = port_table.find_all('tr')[1:]  # Skip header row
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 4:
                        port = {
                            'id': cols[0].text.strip(),
                            'protocol': cols[1].text.strip(),
                            'internal_addr': cols[2].text.strip(),
                            'external_addr': cols[3].text.strip()
                        }
                        ports.append(port)

            return {
                'success': True,
                'basic_info': basic_info,
                'system_info': system_info,
                'ports': ports
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    async def power_control(self, token: str, instance_id: str, action: str) -> Dict:
        """Control VPS power state (boot/stop/reboot)"""
        power_url = f"{CONFIG['BASE_URL']}/user/instance_control.do"
        power_params = {
            'token': token,
            'id': instance_id,
            '_senkinlxc_powermgmt': action
        }

        try:
            response = requests.get(power_url, params=power_params, headers=self.headers)
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}
class TelegramBot:
    def __init__(self):
        self.vps_manager = VPSManager()
        self.user_sessions: Dict[int, Dict] = {}
        self.temp_credentials: Dict[int, Dict] = {}  # Store temporary credentials during login

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send start message when the command /start is issued."""
        if update.effective_user.id not in CONFIG["ALLOWED_USER_IDS"]:
            await update.message.reply_text("You are not authorized to use this bot.")
            return

        keyboard = [
            [InlineKeyboardButton("Login", callback_data="start_login")],
            [InlineKeyboardButton("Help", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Welcome to 7iNet VPS Manager! Please choose an option:",
            reply_markup=reply_markup
        )
        return ConversationHandler.END

    async def start_login(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start the login process."""
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("Please enter your 7iNet username:")
        return WAITING_USERNAME

    async def receive_username(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Receive username and ask for password."""
        user_id = update.effective_user.id
        username = update.message.text

        # Store username temporarily
        self.temp_credentials[user_id] = {'username': username}

        # Delete the message containing the username for security
        await update.message.delete()

        await update.message.reply_text("Please enter your 7iNet password:")
        return WAITING_PASSWORD

    async def receive_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Receive password and attempt login."""
        user_id = update.effective_user.id
        password = update.message.text

        # Delete the message containing the password for security
        await update.message.delete()

        if user_id not in self.temp_credentials:
            await update.message.reply_text("Login process expired. Please start again.")
            return ConversationHandler.END

        username = self.temp_credentials[user_id]['username']

        # Attempt login
        result = await self.vps_manager.login(username, password)

        # Clean up temporary credentials
        del self.temp_credentials[user_id]

        if result['success']:
            self.user_sessions[user_id] = {'token': result['token']}
            keyboard = [
                [InlineKeyboardButton("List Instances", callback_data="list_instances")],
                [InlineKeyboardButton("Logout", callback_data="logout")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Login successful! What would you like to do?",
                reply_markup=reply_markup
            )
        else:
            keyboard = [[InlineKeyboardButton("Try Again", callback_data="start_login")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"Login failed: {result.get('error')}",
                reply_markup=reply_markup
            )

        return ConversationHandler.END

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel the conversation."""
        user_id = update.effective_user.id
        if user_id in self.temp_credentials:
            del self.temp_credentials[user_id]

        await update.message.reply_text("Login process cancelled. Type /start to begin again.")
        return ConversationHandler.END

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle button presses."""
        query = update.callback_query
        await query.answer()

        if query.data == "list_instances":
            await self.show_instances(query)
        elif query.data == "logout":
            user_id = query.from_user.id
            if user_id in self.user_sessions:
                del self.user_sessions[user_id]
            keyboard = [[InlineKeyboardButton("Login Again", callback_data="start_login")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("Logged out successfully!", reply_markup=reply_markup)
        elif query.data == "help":
            help_text = """
Available commands:
/start - Start the bot
/cancel - Cancel current operation
/vps <name> - Show details of specific VPS
/help - Show this help message

For support, contact @YourUsername
"""
            await query.edit_message_text(help_text)
        elif query.data.startswith("show_details_"):
            instance_id = query.data.split("_")[2]
            self.user_sessions[query.from_user.id]['selected_instance'] = instance_id
            await self.show_instance_details(query)

        elif query.data.startswith(("boot_", "stop_", "reboot_")):
            action, instance_id = query.data.split("_")
            await self.handle_power_action(query, action, instance_id)

    async def show_instances(self, query) -> None:
        """Show VPS instances list."""
        user_id = query.from_user.id
        if user_id not in self.user_sessions:
            await query.edit_message_text("Please login first!")
            return

        result = await self.vps_manager.get_instances(self.user_sessions[user_id]['token'])
        if result['success']:
            message = "Your VPS Instances:\n\n"
            keyboard = []
            for instance in result['instances']:
                message += f"📌 Name: {instance['name']}\n"
                message += f"Status: {instance['status']}\n"
                message += f"Username: `{instance['username']}`\n"
                message += f"Password: `{instance['password']}`\n"
                message += f"Expires: {instance['end_time']}\n"
                message += "───────────────\n"
                keyboard.append([InlineKeyboardButton(
                    f"Details: {instance['name']}",
                    callback_data=f"show_details_{instance['id']}"
                )])

            keyboard.append([InlineKeyboardButton("Refresh", callback_data="list_instances")])
            keyboard.append([InlineKeyboardButton("Logout", callback_data="logout")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await query.edit_message_text(f"Failed to get instances: {result.get('error')}")

    async def show_instance_details(self, query) -> None:
        """Show detailed information about a specific VPS instance."""
        user_id = query.from_user.id
        if user_id not in self.user_sessions:
            await query.edit_message_text("Please login first!")
            return

        instance_id = self.user_sessions[user_id].get('selected_instance')
        if not instance_id:
            await query.edit_message_text("Please select an instance first!")
            return

        result = await self.vps_manager.get_instance_details(
            self.user_sessions[user_id]['token'],
            instance_id
        )

        if result['success']:
            message = "📌 VPS Details\n\n"

            message += "🔹 Basic Information:\n"
            for key, value in result['basic_info'].items():
                message += f"{key}: `{value}`\n"
            message += "\n"

            message += "🔹 System Status:\n"
            for key, value in result['system_info'].items():
                if key not in ['用户名']:
                    message += f"{key}: `{value}`\n"
            message += "\n"

            message += "🔹 Port Forwarding:\n"
            if result['ports']:
                for port in result['ports']:
                    message += f"Port {port['id']}: {port['protocol'].upper()} "
                    message += f"{port['internal_addr']} → {port['external_addr']}\n"
            else:
                message += "No port forwarding rules configured\n"

            keyboard = [
                [
                    InlineKeyboardButton("Power Management", callback_data=f"power_{instance_id}"),
                    InlineKeyboardButton("Port Management", callback_data=f"ports_{instance_id}")
                ],
                [
                    InlineKeyboardButton("Change Password", callback_data=f"passwd_{instance_id}"),
                    InlineKeyboardButton("Reinstall System", callback_data=f"reinstall_{instance_id}")
                ],
                [InlineKeyboardButton("Back to List", callback_data="list_instances")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(f"Failed to get instance details: {result.get('error')}")

    async def select_instance(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /vps command to select an instance by name."""
        if len(context.args) == 0:
            await update.message.reply_text("Please provide a VPS instance name!\nUsage: /vps <instance_name>")
            return

        instance_name = context.args[0]
        user_id = update.effective_user.id

        if user_id not in self.user_sessions:
            await update.message.reply_text("Please login first!")
            return

        # Get all instances and find the matching one
        result = await self.vps_manager.get_instances(self.user_sessions[user_id]['token'])
        if result['success']:
            matching_instance = None
            for instance in result['instances']:
                if instance['name'].lower() == instance_name.lower():
                    matching_instance = instance
                    break

            if matching_instance:
                self.user_sessions[user_id]['selected_instance'] = matching_instance['id']
                keyboard = [
                    [InlineKeyboardButton("Show Details", callback_data=f"show_details_{matching_instance['id']}")],
                    [InlineKeyboardButton("Back to List", callback_data="list_instances")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"Found VPS: {matching_instance['name']}\nStatus: {matching_instance['status']}",
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(f"No VPS instance found with name: {instance_name}")
        else:
            await update.message.reply_text(f"Failed to get instances: {result.get('error')}")

    async def handle_power_action(self, query, action: str, instance_id: str) -> None:
        """Handle power management actions"""
        user_id = query.from_user.id
        if user_id not in self.user_sessions:
            await query.edit_message_text("Please login first!")
            return

        # Show confirmation message
        action_text = {"boot": "start", "stop": "shutdown", "reboot": "restart"}[action]
        keyboard = [
            [
                InlineKeyboardButton("Confirm", callback_data=f"confirm_power_{action}_{instance_id}"),
                InlineKeyboardButton("Cancel", callback_data=f"show_details_{instance_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"Are you sure you want to {action_text} this VPS?",
            reply_markup=reply_markup
        )

    def run(self):
        """Run the bot."""
        application = Application.builder().token(CONFIG["BOT_TOKEN"]).build()

        # Add conversation handler for login process
        conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_login, pattern="^start_login$")],
            states={
                WAITING_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_username)],
                WAITING_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_password)],
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
        )

        # Add handlers
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("vps", self.select_instance))
        application.add_handler(conv_handler)
        application.add_handler(CallbackQueryHandler(self.button_handler))

        # Start the bot
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    bot = TelegramBot()
    bot.run()