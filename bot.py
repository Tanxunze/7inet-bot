import asyncio
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
WAITING_USERNAME, WAITING_PASSWORD, WAITING_PROTOCOL, WAITING_INTERNAL_PORT, WAITING_EXTERNAL_PORT, WAITING_NEW_PASSWORD = range(
    6)

# Configuration
CONFIG = {
    "BASE_URL": "https://api.7inet.com.cn",
    "BOT_TOKEN": "7613902246:AAF8yHzFXibLc8pHS8u7M8ZH3UfXPHSlTP0",
    "ALLOWED_USER_IDS": [1880860457]
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
                # 处理运行状态
                status_font = card.find('font')
                if status_font:
                    system_info['运行状态'] = status_font.text.strip()

                # 获取所有文本内容
                content = card.get_text('\n').strip()
                lines = [line.strip() for line in content.split('\n') if line.strip()]

                for i, line in enumerate(lines):
                    # 处理内网IP
                    if line == '内网IP:' and i + 1 < len(lines):
                        system_info['内网IP'] = lines[i + 1].strip()

                    # 处理用户名
                    elif line.startswith('用户名:'):
                        system_info['用户名'] = line.replace('用户名:', '').strip()

                    # 处理内存使用
                    elif line == '内存使用:' and i + 2 < len(lines):
                        used = lines[i + 1].strip()
                        total = lines[i + 2].strip()
                        system_info['内存使用'] = f"{used} {total}"

                    # 处理硬盘使用
                    elif line == '硬盘使用:' and i + 2 < len(lines):
                        used = lines[i + 1].strip()
                        total = lines[i + 2].strip()
                        system_info['硬盘使用'] = f"{used} {total}"

                    # 处理流量使用
                    elif line.startswith('流量使用:'):
                        system_info['流量使用'] = line.replace('流量使用:', '').strip()

            # Extract port forwarding information
            ports = []
            table_div = soup.find('div', {'class': 'table-responsive', 'id': 'listtable'})
            if table_div:
                table = table_div.find('table')
                if table:
                    rows = table.find_all('tr')[1:]
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

    async def add_port_forward(self, token: str, instance_id: str, protocol: str, internal_port: str,
                               external_port: str) -> Dict:
        """Add a new port forwarding rule"""
        url = f"{CONFIG['BASE_URL']}/user/instance_control.do"
        params = {
            'token': token,
            'id': instance_id,
            '_senkinlxc_port': f"addport|{protocol}|{internal_port}|{external_port}"
        }

        try:
            response = requests.get(url, params=params, headers=self.headers)
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    async def delete_port_forward(self, token: str, instance_id: str, protocol: str, internal_port: str,
                                  external_port: str) -> Dict:
        """Delete a port forwarding rule"""
        url = f"{CONFIG['BASE_URL']}/user/instance_control.do"
        params = {
            'token': token,
            'id': instance_id,
            '_senkinlxc_port': f"delport|{protocol}|{internal_port}|{external_port}"
        }

        try:
            response = requests.get(url, params=params, headers=self.headers)
            return {'success': True}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    async def change_password(self, token: str, instance_id: str, new_password: str) -> Dict:
        """Change VPS password"""
        url = f"{CONFIG['BASE_URL']}/user/instance_control.do"
        params = {
            'token': token,
            'id': instance_id,
            '_senkinlxc_password': new_password
        }

        try:
            response = requests.get(url, params=params, headers=self.headers)
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

    async def receive_new_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle new password input"""
        user_id = update.effective_user.id
        new_password = update.message.text.strip()

        await update.message.delete()

        if len(new_password) < 6:  # FOR SAFETY :) - Mio
            await update.message.reply_text(
                "Password must be at least 6 characters long. Please try again:"
            )
            return WAITING_NEW_PASSWORD

        instance_id = self.user_sessions[user_id].get('selected_instance')
        result = await self.vps_manager.change_password(
            self.user_sessions[user_id]['token'],
            instance_id,
            new_password
        )

        if result['success']:
            keyboard = [[
                InlineKeyboardButton("Back to Details", callback_data=f"show_details_{instance_id}")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Password changed successfully!",
                reply_markup=reply_markup
            )
        else:
            keyboard = [[
                InlineKeyboardButton("Try Again", callback_data=f"passwd_{instance_id}"),
                InlineKeyboardButton("Back to Details", callback_data=f"show_details_{instance_id}")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"Failed to change password: {result.get('error')}",
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

        elif query.data.startswith("confirm_power_"):
            _, _, action, instance_id = query.data.split("_")
            result = await self.vps_manager.power_control(
                self.user_sessions[query.from_user.id]['token'],
                instance_id,
                action
            )
            if result['success']:
                await query.edit_message_text(
                    f"Power action {action} initiated successfully.\nPlease wait a moment...",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("Back to Details", callback_data=f"show_details_{instance_id}")
                    ]])
                )
            else:
                await query.edit_message_text(
                    f"Failed to execute power action: {result.get('error')}",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("Back to Details", callback_data=f"show_details_{instance_id}")
                    ]])
                )

        elif query.data.startswith("ports_"):
            instance_id = query.data.split("_")[1]
            result = await self.vps_manager.get_instance_details(
                self.user_sessions[query.from_user.id]['token'],
                instance_id
            )

            message = "🔹 Port Management\n\n"
            if result['success'] and result['ports']:
                message += "Current Port Forwards:\n"
                for port in result['ports']:
                    message += f"• {port['protocol'].upper()}: "
                    message += f"{port['internal_addr']} → {port['external_addr']}\n"
                message += "\nSelect an action:\n"
            else:
                message += "No port forwarding rules configured.\n\nSelect an action:\n"

            keyboard = [[InlineKeyboardButton("📌 Add Port Forward", callback_data=f"add_port_{instance_id}")]]

            if result['success'] and result['ports']:
                for port in result['ports']:
                    keyboard.append([
                        InlineKeyboardButton(
                            f"🗑️ Delete {port['protocol'].upper()} {port['internal_addr']} → {port['external_addr']}",
                            callback_data=f"del_port_{instance_id}_{port['protocol']}_{port['internal_addr'].split(':')[1]}_{port['external_addr'].split(':')[1]}"
                        )
                    ])

            keyboard.append([InlineKeyboardButton("⬅️ Back to Details", callback_data=f"show_details_{instance_id}")])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                message,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

        elif query.data.startswith("add_port_"):
            instance_id = query.data.split("_")[2]
            self.user_sessions[query.from_user.id]['port_forward'] = {
                'instance_id': instance_id,
                'stage': 'protocol'
            }
            keyboard = [
                [
                    InlineKeyboardButton("TCP", callback_data=f"port_protocol_tcp_{instance_id}"),
                    InlineKeyboardButton("UDP", callback_data=f"port_protocol_udp_{instance_id}")
                ],
                [InlineKeyboardButton("Cancel", callback_data=f"show_details_{instance_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "Please select protocol:",
                reply_markup=reply_markup
            )
        elif query.data.startswith("port_protocol_"):
            _, _, protocol, instance_id = query.data.split("_")
            self.user_sessions[query.from_user.id]['port_forward'].update({
                'protocol': protocol
            })
            await query.edit_message_text(
                f"Selected protocol: {protocol.upper()}\n"
                "Please enter internal port number (1-65535):"
            )
            return WAITING_INTERNAL_PORT

        elif query.data.startswith("del_port_"):
            _, _, instance_id, protocol, internal_port, external_port = query.data.split("_")
            keyboard = [
                [
                    InlineKeyboardButton("Confirm Delete",
                                         callback_data=f"confirm_del_port_{instance_id}_{protocol}_{internal_port}_{external_port}"),
                    InlineKeyboardButton("Cancel", callback_data=f"show_details_{instance_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"Are you sure you want to delete port forwarding rule?\n"
                f"Protocol: {protocol.upper()}\n"
                f"Internal Port: {internal_port}\n"
                f"External Port: {external_port}",
                reply_markup=reply_markup
            )

        elif query.data.startswith("confirm_del_port_"):
            _, _, _, instance_id, protocol, internal_port, external_port = query.data.split("_")
            result = await self.vps_manager.delete_port_forward(
                self.user_sessions[query.from_user.id]['token'],
                instance_id,
                protocol,
                internal_port,
                external_port
            )

            if result['success']:
                await query.edit_message_text(
                    "Port forwarding rule deleted successfully!\nRefreshing...",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("Please wait...", callback_data="dummy")
                    ]])
                )
            else:
                await query.edit_message_text(
                    f"Failed to delete port: {result.get('error')}",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("Back to Details", callback_data=f"show_details_{instance_id}")
                    ]])
                )

            if result['success']:
                await asyncio.sleep(1)
                await self.show_instance_details(query)

        elif query.data.startswith("passwd_"):
            instance_id = query.data.split("_")[1]
            await query.edit_message_text(
                "Please enter new password for your VPS:\n"
                "(Password must be at least 6 characters long)",
            )
            return WAITING_NEW_PASSWORD

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
                    message += f"#{port['id']}: {port['protocol'].upper()} "
                    message += f"{port['internal_addr']} → {port['external_addr']}\n"
            else:
                message += "No port forwarding rules configured\n"

            keyboard = [
                [
                    InlineKeyboardButton("▶️ Start", callback_data=f"boot_{instance_id}"),
                    InlineKeyboardButton("🔄 Restart", callback_data=f"reboot_{instance_id}"),
                    InlineKeyboardButton("⏹ Stop", callback_data=f"stop_{instance_id}")
                ],
                [
                    InlineKeyboardButton("Port Management", callback_data=f"ports_{instance_id}"),
                    InlineKeyboardButton("Change Password", callback_data=f"passwd_{instance_id}")
                ],
                [
                    InlineKeyboardButton("Reinstall System", callback_data=f"reinstall_{instance_id}"),
                    InlineKeyboardButton("Back to List", callback_data="list_instances")
                ]
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

    async def handle_password_change(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle password change initiation"""
        query = update.callback_query
        await query.answer()

        instance_id = query.data.split("_")[1]
        self.user_sessions[query.from_user.id]['selected_instance'] = instance_id

        await query.edit_message_text(
            "Please enter new password for your VPS:\n"
            "(Password must be at least 6 characters long)"
        )
        return WAITING_NEW_PASSWORD

    async def receive_internal_port(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        port = update.message.text.strip()

        try:
            port_num = int(port)
            if 1 <= port_num <= 65535:
                self.user_sessions[user_id]['port_forward']['internal_port'] = port
                await update.message.reply_text(
                    "Please enter external port number (40000-65500):"
                )
                return WAITING_EXTERNAL_PORT
            else:
                await update.message.reply_text(
                    "Invalid port number. Please enter a number between 1 and 65535:"
                )
                return WAITING_INTERNAL_PORT
        except ValueError:
            await update.message.reply_text(
                "Invalid input. Please enter a valid port number:"
            )
            return WAITING_INTERNAL_PORT

    async def handle_port_protocol(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle protocol selection for port forwarding"""
        query = update.callback_query
        await query.answer()

        _, _, protocol, instance_id = query.data.split("_")
        user_id = query.from_user.id

        # Initialize port_forward data
        if 'port_forward' not in self.user_sessions[user_id]:
            self.user_sessions[user_id]['port_forward'] = {}

        self.user_sessions[user_id]['port_forward'].update({
            'protocol': protocol,
            'instance_id': instance_id
        })

        await query.edit_message_text(
            f"Selected protocol: {protocol.upper()}\n"
            "Please enter internal port number (1-65535):"
        )
        return WAITING_INTERNAL_PORT

    async def receive_external_port(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        port = update.message.text.strip()

        try:
            port_num = int(port)
            if 40000 <= port_num <= 65500:
                port_data = self.user_sessions[user_id]['port_forward']
                result = await self.vps_manager.add_port_forward(
                    self.user_sessions[user_id]['token'],
                    port_data['instance_id'],
                    port_data['protocol'],
                    port_data['internal_port'],
                    port
                )

                keyboard = [[
                    InlineKeyboardButton(
                        "Back to Details",
                        callback_data=f"show_details_{port_data['instance_id']}"
                    )
                ]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                if result['success']:
                    await update.message.reply_text(
                        "Port forward rule added successfully!",
                        reply_markup=reply_markup
                    )
                else:
                    await update.message.reply_text(
                        f"Failed to add port forward: {result.get('error')}",
                        reply_markup=reply_markup
                    )

                return ConversationHandler.END
            else:
                await update.message.reply_text(
                    "Invalid port number. Please enter a number between 40000 and 65500:"
                )
                return WAITING_EXTERNAL_PORT
        except ValueError:
            await update.message.reply_text(
                "Invalid input. Please enter a valid port number:"
            )
            return WAITING_EXTERNAL_PORT

    def run(self):
        """Run the bot."""
        application = Application.builder().token(CONFIG["BOT_TOKEN"]).build()

        # Add conversation handler for login process
        conv_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(self.start_login, pattern="^start_login$"),
                CallbackQueryHandler(self.handle_port_protocol, pattern="^port_protocol_"),
                CallbackQueryHandler(self.handle_password_change, pattern="^passwd_")
            ],
            states={
                WAITING_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_username)],
                WAITING_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_password)],
                WAITING_INTERNAL_PORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_internal_port)],
                WAITING_EXTERNAL_PORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_external_port)],
                WAITING_NEW_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_new_password)]
            },
            fallbacks=[CommandHandler("cancel", self.cancel)],
        )

        # Add handlers
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("vps", self.select_instance))
        application.add_handler(conv_handler)
        application.add_handler(CallbackQueryHandler(self.button_handler))

        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    bot = TelegramBot()
    bot.run()
