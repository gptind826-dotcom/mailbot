#!/usr/bin/env python3
import requests
import json
import re
import sqlite3
import os
import threading
import time
import asyncio
import logging
from datetime import datetime
from flask import Flask, jsonify
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Setup logging so Render captures errors in logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PORT = int(os.environ.get("PORT", 8080))
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_IDS = [8379062893, 8287805904]

app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return jsonify({
        "status": "active",
        "bot": "EXRMAIL Bot",
        "uptime": time.strftime("%Y-%m-%d %H:%M:%S"),
        "version": "2.0"
    })

@app_flask.route('/health')
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

def init_db():
    conn = sqlite3.connect('whitelist.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS whitelist 
                 (user_id INTEGER PRIMARY KEY, 
                  username TEXT, 
                  added_by INTEGER, 
                  added_date TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

def is_whitelisted(user_id):
    conn = sqlite3.connect('whitelist.db')
    c = conn.cursor()
    c.execute("SELECT 1 FROM whitelist WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def add_to_whitelist(user_id, username, admin_id):
    conn = sqlite3.connect('whitelist.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO whitelist VALUES (?, ?, ?, ?)", 
              (user_id, username, admin_id, datetime.now()))
    conn.commit()
    conn.close()

def remove_from_whitelist(user_id):
    conn = sqlite3.connect('whitelist.db')
    c = conn.cursor()
    c.execute("DELETE FROM whitelist WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_whitelist():
    conn = sqlite3.connect('whitelist.db')
    c = conn.cursor()
    c.execute("SELECT user_id, username, added_date FROM whitelist")
    result = c.fetchall()
    conn.close()
    return result

def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_greeting():
    hour = datetime.now().hour
    if hour < 12:
        return "𝐆𝐨𝐨𝐝 𝐌𝐨𝐫𝐧𝐢𝐧𝐠"
    elif hour < 17:
        return "𝐆𝐨𝐨𝐝 𝐀𝐟𝐭𝐞𝐫𝐧𝐨𝐨𝐧"
    elif hour < 20:
        return "𝐆𝐨𝐨𝐝 𝐄𝐯𝐞𝐧𝐢𝐧𝐠"
    else:
        return "𝐆𝐨𝐨𝐝 𝐍𝐢𝐠𝐡𝐭"

def extract_eat_token(input_text):
    input_text = input_text.strip()
    brace_pattern = r'\{(.+?)\}'
    brace_match = re.search(brace_pattern, input_text)
    if brace_match:
        return brace_match.group(1)
    eat_pattern = r'[?&]eat=([^&]+)'
    eat_match = re.search(eat_pattern, input_text)
    if eat_match:
        extracted = eat_match.group(1)
        return extracted.strip('{}')
    eat_token_pattern = r'[?&]eat_token=([^&]+)'
    eat_token_match = re.search(eat_token_pattern, input_text)
    if eat_token_match:
        extracted = eat_token_match.group(1)
        return extracted.strip('{}')
    if re.match(r'^[a-fA-F0-9]+$', input_text) and len(input_text) > 50:
        return input_text
    return input_text

def check_bind_info_api(access_token):
    try:
        url = "https://bind-info-rouge.vercel.app/bind_info?access_token=" + access_token
        response = requests.get(url, timeout=30)
        return response.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}

def eat_to_access_api(eat_token):
    try:
        clean_token = extract_eat_token(eat_token)
        url = "https://eat-one-eta.vercel.app/Eat?eat_token=" + clean_token
        response = requests.get(url, timeout=30)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def revoke_token_api(access_token):
    try:
        url = "https://revoke-delta.vercel.app/logout?access_token=" + access_token
        response = requests.get(url, timeout=30)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def generate_jwt_api(access_token):
    try:
        url = "https://jwt-liart.vercel.app/rizer?access_token=" + access_token
        response = requests.get(url, timeout=30)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def change_bind_email_api(access_token, old_email, new_email, otp_old, otp_new):
    headers = {
        'User-Agent': 'GarenaMSDK/4.0.30',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
    }
    
    url_send = 'https://100067.connect.garena.com/game/account_security/bind:send_otp'
    data = {'email': old_email, 'locale': 'en_PK', 'region': 'PK', 'app_id': '100067', 'access_token': access_token}
    
    try:
        r = requests.post(url_send, headers=headers, data=data, timeout=30)
        if r.status_code != 200 or r.json().get('result') != 0:
            return {"error": "Failed to send OTP to old email"}
    except:
        return {"error": "Failed to send OTP to old email"}
    
    url_verify = 'https://100067.connect.garena.com/game/account_security/bind:verify_identity'
    data = {'email': old_email, 'app_id': '100067', 'access_token': access_token, 'otp': otp_old}
    
    try:
        r = requests.post(url_verify, headers=headers, data=data, timeout=30)
        res = r.json()
        identity_token = res.get('identity_token')
        if not identity_token:
            return {"error": "Invalid OTP for old email"}
    except:
        return {"error": "Failed to verify OTP"}
    
    data = {'email': new_email, 'locale': 'en_PK', 'region': 'PK', 'app_id': '100067', 'access_token': access_token}
    
    try:
        r = requests.post(url_send, headers=headers, data=data, timeout=30)
        if r.status_code != 200 or r.json().get('result') != 0:
            return {"error": "Failed to send OTP to new email"}
    except:
        return {"error": "Failed to send OTP to new email"}
    
    url_verify_otp = 'https://100067.connect.garena.com/game/account_security/bind:verify_otp'
    data = {'email': new_email, 'app_id': '100067', 'access_token': access_token, 'otp': otp_new}
    
    try:
        r = requests.post(url_verify_otp, headers=headers, data=data, timeout=30)
        res = r.json()
        verifier_token = res.get('verifier_token')
        if not verifier_token:
            return {"error": "Invalid OTP for new email"}
    except:
        return {"error": "Failed to verify new email OTP"}
    
    url_rebind = 'https://100067.connect.garena.com/game/account_security/bind:create_rebind_request'
    data = {'identity_token': identity_token, 'email': new_email, 'app_id': '100067', 'verifier_token': verifier_token, 'access_token': access_token}
    
    try:
        r = requests.post(url_rebind, headers=headers, data=data, timeout=30)
        if r.status_code == 200 and 'result": 0' in r.text:
            return {"success": "Email change request submitted successfully!"}
        else:
            return {"error": "Email change failed"}
    except:
        return {"error": "Failed to create rebind request"}

def unbind_email_api(access_token, email, otp):
    headers = {
        'User-Agent': 'GarenaMSDK/4.0.30',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
    }
    
    url_send = 'https://100067.connect.garena.com/game/account_security/bind:send_otp'
    data = {'email': email, 'locale': 'en_PK', 'region': 'PK', 'app_id': '100067', 'access_token': access_token}
    
    try:
        r = requests.post(url_send, headers=headers, data=data, timeout=30)
        if r.status_code != 200 or r.json().get('result') != 0:
            return {"error": "Failed to send OTP"}
    except:
        return {"error": "Failed to send OTP"}
    
    url_verify = 'https://100067.connect.garena.com/game/account_security/bind:verify_identity'
    data = {'email': email, 'app_id': '100067', 'access_token': access_token, 'otp': otp}
    
    try:
        r = requests.post(url_verify, headers=headers, data=data, timeout=30)
        res = r.json()
        identity_token = res.get('identity_token')
        if not identity_token:
            return {"error": "Invalid OTP"}
    except:
        return {"error": "Failed to verify OTP"}
    
    url_unbind = 'https://100067.connect.garena.com/game/account_security/bind:create_unbind_request'
    data = {'app_id': '100067', 'access_token': access_token, 'identity_token': identity_token}
    
    try:
        r = requests.post(url_unbind, headers=headers, data=data, timeout=30)
        if r.status_code == 200 and 'result": 0' in r.text:
            return {"success": "Unbind request successfully created!"}
        else:
            return {"error": "Unbind request failed"}
    except:
        return {"error": "Failed to create unbind request"}

def cancel_bind_api(access_token):
    headers = {
        'User-Agent': 'GarenaMSDK/4.0.30',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
    }
    
    url_cancel = 'https://100067.connect.garena.com/game/account_security/bind:cancel_request'
    data = {'access_token': access_token, 'app_id': '100067'}
    
    try:
        r = requests.post(url_cancel, headers=headers, data=data, timeout=30)
        res = r.json()
        if r.status_code == 200 and res.get('result') == 0:
            return {"success": "Successfully cancelled bind request"}
        else:
            return {"error": "Cancel failed"}
    except:
        return {"error": "Failed to cancel bind request"}

def get_main_keyboard():
    keyboard = [
        [KeyboardButton("𝐂𝐇𝐀𝐍𝐆𝐄 𝐁𝐈𝐍𝐃"), KeyboardButton("𝐂𝐀𝐍𝐂𝐄𝐋 𝐁𝐈𝐍𝐃")],
        [KeyboardButton("𝐔𝐍𝐁𝐈𝐍𝐃"), KeyboardButton("𝐄𝐀𝐓 𝐓𝐎 𝐓𝐎𝐊𝐄𝐍")],
        [KeyboardButton("𝐁𝐈𝐍𝐃 𝐈𝐍𝐅𝐎"), KeyboardButton("𝐑𝐄𝐕𝐎𝐊𝐄")],
        [KeyboardButton("𝐉𝐖𝐓 𝐆𝐄𝐍"), KeyboardButton("𝐀𝐃𝐌𝐈𝐍")],
        [KeyboardButton("𝐇𝐄𝐋𝐏")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_admin_keyboard():
    keyboard = [
        [KeyboardButton("𝐀𝐃𝐃 𝐖𝐇𝐈𝐓𝐄𝐋𝐈𝐒𝐓"), KeyboardButton("𝐑𝐄𝐌𝐎𝐕𝐄 𝐖𝐇𝐈𝐓𝐄𝐋𝐈𝐒𝐓")],
        [KeyboardButton("𝐕𝐈𝐄𝐖 𝐖𝐇𝐈𝐓𝐄𝐋𝐈𝐒𝐓"), KeyboardButton("𝐕𝐈𝐄𝐖 𝐒𝐓𝐀𝐓𝐒")],
        [KeyboardButton("𝐁𝐀𝐂𝐊 𝐓𝐎 𝐌𝐀𝐈𝐍")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def get_cancel_keyboard():
    keyboard = [[KeyboardButton("𝐂𝐀𝐍𝐂𝐄𝐋")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.first_name or user.username or str(user_id)
    
    if not is_whitelisted(user_id) and not is_admin(user_id):
        await update.message.reply_text(
            f"╔═══《 ⛔ 𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃! 》═══╗\n\n"
            f"𝐔𝐒𝐄𝐑: {username}\n"
            f"𝐔𝐒𝐄𝐑 𝐈𝐃: {user_id}\n\n"
            f"╰═══════《 🔒 》═══════╝\n\n"
            f"𝐘𝐎𝐔 𝐀𝐑𝐄 𝐍𝐎𝐓 𝐖𝐇𝐈𝐓𝐄𝐋𝐈𝐒𝐓𝐄𝐃!\n\n"
            f"📌 𝐂𝐎𝐍𝐓𝐀𝐂𝐓 𝐀𝐃𝐌𝐈𝐍: @exucoder"
        )
        return
    
    is_admin_status = "𝐀𝐃𝐌𝐈𝐍𝐈𝐒𝐓𝐑𝐀𝐓𝐎𝐑" if is_admin(user_id) else "𝐔𝐒𝐄𝐑"
    greeting = get_greeting()
    
    await update.message.reply_text(
        f"╔═══《 🎉 {greeting}! 》═══╗\n\n"
        f"𝐔𝐒𝐄𝐑: {username}\n"
        f"𝐔𝐒𝐄𝐑 𝐈𝐃: {user_id}\n"
        f"𝐒𝐓𝐀𝐓𝐔𝐒: {is_admin_status}\n\n"
        f"╰═══════《 🤖 》═══════╝\n\n"
        f"𝐖𝐄𝐋𝐂𝐎𝐌𝐄 𝐓𝐎 𝐄𝐗𝐑𝐌𝐀𝐈𝐋 𝐁𝐎𝐓\n\n"
        f"📌 𝐀𝐁𝐎𝐔𝐓 𝐓𝐇𝐈𝐒 𝐁𝐎𝐓:\n"
        f"• 𝐒𝐄𝐂𝐔𝐑𝐄 𝐄𝐌𝐀𝐈𝐋 𝐌𝐀𝐍𝐀𝐆𝐄𝐑\n"
        f"• 𝐅𝐑𝐄𝐄 𝐅𝐈𝐑𝐄 𝐁𝐈𝐍𝐃 𝐂𝐇𝐀𝐍𝐆𝐄\n"
        f"• 𝐓𝐎𝐊𝐄𝐍 𝐌𝐀𝐍𝐀𝐆𝐄𝐌𝐄𝐍𝐓\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ 𝐀𝐂𝐂𝐄𝐒𝐒 𝐆𝐑𝐀𝐍𝐓𝐄𝐃!\n\n"
        f"📌 𝐐𝐔𝐈𝐂𝐊 𝐆𝐔𝐈𝐃𝐄:\n"
        f"• 𝐔𝐒𝐄 𝐓𝐇𝐄 𝐁𝐔𝐓𝐓𝐎𝐍𝐒 𝐁𝐄𝐋𝐎𝐖\n"
        f"• 𝐄𝐍𝐓𝐄𝐑 𝐘𝐎𝐔𝐑 𝐂𝐑𝐄𝐃𝐄𝐍𝐓𝐈𝐀𝐋𝐒\n"
        f"• 𝐆𝐄𝐓 𝐈𝐍𝐒𝐓𝐀𝐍𝐓 𝐑𝐄𝐒𝐔𝐋𝐓𝐒",
        reply_markup=get_main_keyboard()
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    if not is_whitelisted(user_id) and not is_admin(user_id):
        await update.message.reply_text("⛔ 𝐀𝐂𝐂𝐄𝐒𝐒 𝐃𝐄𝐍𝐈𝐄𝐃!")
        return
    
    if text == "𝐂𝐀𝐍𝐂𝐄𝐋":
        if 'conversation' in context.user_data:
            del context.user_data['conversation']
        await update.message.reply_text("✅ 𝐎𝐏𝐄𝐑𝐀𝐓𝐈𝐎𝐍 𝐂𝐀𝐍𝐂𝐄𝐋𝐋𝐄𝐃!", reply_markup=get_main_keyboard())
        return
    
    if text == "𝐁𝐀𝐂𝐊 𝐓𝐎 𝐌𝐀𝐈𝐍":
        await update.message.reply_text("🏠 𝐌𝐀𝐈𝐍 𝐌𝐄𝐍𝐔", reply_markup=get_main_keyboard())
        return
    
    # Main menu buttons
    if text == "𝐂𝐇𝐀𝐍𝐆𝐄 𝐁𝐈𝐍𝐃":
        context.user_data['conversation'] = 'change_bind'
        context.user_data['step'] = 1
        await update.message.reply_text(
            f"𝐂𝐇𝐀𝐍𝐆𝐄 𝐁𝐈𝐍𝐃 𝐄𝐌𝐀𝐈𝐋\n\n𝐒𝐓𝐄𝐏 𝟏/𝟓 - 𝐒𝐄𝐍𝐃 𝐘𝐎𝐔𝐑 𝐀𝐂𝐂𝐄𝐒𝐒 𝐓𝐎𝐊𝐄𝐍:\n\n𝐓𝐘𝐏𝐄 𝐂𝐀𝐍𝐂𝐄𝐋 𝐓𝐎 𝐂𝐀𝐍𝐂𝐄𝐋.",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    elif text == "𝐂𝐀𝐍𝐂𝐄𝐋 𝐁𝐈𝐍𝐃":
        context.user_data['conversation'] = 'cancel_bind'
        await update.message.reply_text(
            f"𝐂𝐀𝐍𝐂𝐄𝐋 𝐁𝐈𝐍𝐃 𝐑𝐄𝐐𝐔𝐄𝐒𝐓\n\n𝐒𝐄𝐍𝐃 𝐘𝐎𝐔𝐑 𝐀𝐂𝐂𝐄𝐒𝐒 𝐓𝐎𝐊𝐄𝐍:\n\n𝐓𝐘𝐏𝐄 𝐂𝐀𝐍𝐂𝐄𝐋 𝐓𝐎 𝐂𝐀𝐍𝐂𝐄𝐋.",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    elif text == "𝐔𝐍𝐁𝐈𝐍𝐃":
        context.user_data['conversation'] = 'unbind'
        context.user_data['step'] = 1
        await update.message.reply_text(
            f"𝐔𝐍𝐁𝐈𝐍𝐃 𝐄𝐌𝐀𝐈𝐋\n\n𝐒𝐓𝐄𝐏 𝟏/𝟑 - 𝐒𝐄𝐍𝐃 𝐘𝐎𝐔𝐑 𝐀𝐂𝐂𝐄𝐒𝐒 𝐓𝐎𝐊𝐄𝐍:\n\n𝐓𝐘𝐏𝐄 𝐂𝐀𝐍𝐂𝐄𝐋 𝐓𝐎 𝐂𝐀𝐍𝐂𝐄𝐋.",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    elif text == "𝐄𝐀𝐓 𝐓𝐎 𝐓𝐎𝐊𝐄𝐍":
        context.user_data['conversation'] = 'eat_to_token'
        await update.message.reply_text(
            f"𝐄𝐀𝐓 𝐓𝐎 𝐀𝐂𝐂𝐄𝐒𝐒 𝐓𝐎𝐊𝐄𝐍\n\n𝐒𝐄𝐍𝐃 𝐘𝐎𝐔𝐑 𝐄𝐀𝐓 𝐓𝐎𝐊𝐄𝐍 𝐎𝐑 𝐔𝐑𝐋:\n\n𝐓𝐘𝐏𝐄 𝐂𝐀𝐍𝐂𝐄𝐋 𝐓𝐎 𝐂𝐀𝐍𝐂𝐄𝐋.",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    elif text == "𝐁𝐈𝐍𝐃 𝐈𝐍𝐅𝐎":
        context.user_data['conversation'] = 'bind_info'
        await update.message.reply_text(
            f"𝐁𝐈𝐍𝐃 𝐈𝐍𝐅𝐎𝐑𝐌𝐀𝐓𝐈𝐎𝐍\n\n𝐒𝐄𝐍𝐃 𝐘𝐎𝐔𝐑 𝐀𝐂𝐂𝐄𝐒𝐒 𝐓𝐎𝐊𝐄𝐍:\n\n𝐓𝐘𝐏𝐄 𝐂𝐀𝐍𝐂𝐄𝐋 𝐓𝐎 𝐂𝐀𝐍𝐂𝐄𝐋.",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    elif text == "𝐑𝐄𝐕𝐎𝐊𝐄":
        context.user_data['conversation'] = 'revoke'
        await update.message.reply_text(
            f"𝐑𝐄𝐕𝐎𝐊𝐄 𝐀𝐂𝐂𝐄𝐒𝐒 𝐓𝐎𝐊𝐄𝐍\n\n𝐒𝐄𝐍𝐃 𝐓𝐇𝐄 𝐀𝐂𝐂𝐄𝐒𝐒 𝐓𝐎𝐊𝐄𝐍 𝐓𝐎 𝐑𝐄𝐕𝐎𝐊𝐄:\n\n𝐓𝐘𝐏𝐄 𝐂𝐀𝐍𝐂𝐄𝐋 𝐓𝐎 𝐂𝐀𝐍𝐂𝐄𝐋.",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    elif text == "𝐉𝐖𝐓 𝐆𝐄𝐍":
        context.user_data['conversation'] = 'jwt'
        await update.message.reply_text(
            f"𝐉𝐖𝐓 𝐆𝐄𝐍𝐄𝐑𝐀𝐓𝐎𝐑\n\n𝐒𝐄𝐍𝐃 𝐘𝐎𝐔𝐑 𝐀𝐂𝐂𝐄𝐒𝐒 𝐓𝐎𝐊𝐄𝐍:\n\n𝐓𝐘𝐏𝐄 𝐂𝐀𝐍𝐂𝐄𝐋 𝐓𝐎 𝐂𝐀𝐍𝐂𝐄𝐋.",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    elif text == "𝐀𝐃𝐌𝐈𝐍":
        if not is_admin(user_id):
            await update.message.reply_text("⛔ 𝐀𝐃𝐌𝐈𝐍 𝐀𝐂𝐂𝐄𝐒𝐒 𝐎𝐍𝐋𝐘!")
            return
        await update.message.reply_text("𝐀𝐃𝐌𝐈𝐍 𝐏𝐀𝐍𝐄𝐋\n\n𝐖𝐄𝐋𝐂𝐎𝐌𝐄 𝐓𝐎 𝐀𝐃𝐌𝐈𝐍 𝐏𝐀𝐍𝐄𝐋!", reply_markup=get_admin_keyboard())
        return
    
    elif text == "𝐇𝐄𝐋𝐏":
        await update.message.reply_text(
            f"𝐇𝐄𝐋𝐏 𝐆𝐔𝐈𝐃𝐄\n\n"
            f"𝐂𝐇𝐀𝐍𝐆𝐄 𝐁𝐈𝐍𝐃 - 𝐂𝐇𝐀𝐍𝐆𝐄 𝐁𝐎𝐔𝐍𝐃 𝐄𝐌𝐀𝐈𝐋 (𝐎𝐓𝐏 𝐑𝐄𝐐𝐔𝐈𝐑𝐄𝐃)\n"
            f"𝐂𝐀𝐍𝐂𝐄𝐋 𝐁𝐈𝐍𝐃 - 𝐂𝐀𝐍𝐂𝐄𝐋 𝐏𝐄𝐍𝐃𝐈𝐍𝐆 𝐁𝐈𝐍𝐃 𝐑𝐄𝐐𝐔𝐄𝐒𝐓\n"
            f"𝐔𝐍𝐁𝐈𝐍𝐃 - 𝐑𝐄𝐌𝐎𝐕𝐄 𝐄𝐌𝐀𝐈𝐋 𝐁𝐈𝐍𝐃𝐈𝐍𝐆\n"
            f"𝐄𝐀𝐓 𝐓𝐎 𝐓𝐎𝐊𝐄𝐍 - 𝐂𝐎𝐍𝐕𝐄𝐑𝐓 𝐄𝐀𝐓 𝐓𝐎 𝐀𝐂𝐂𝐄𝐒𝐒 𝐓𝐎𝐊𝐄𝐍\n"
            f"𝐁𝐈𝐍𝐃 𝐈𝐍𝐅𝐎 - 𝐂𝐇𝐄𝐂𝐊 𝐀𝐂𝐂𝐎𝐔𝐍𝐓 𝐁𝐈𝐍𝐃 𝐒𝐓𝐀𝐓𝐔𝐒\n"
            f"𝐑𝐄𝐕𝐎𝐊𝐄 - 𝐈𝐍𝐕𝐀𝐋𝐈𝐃𝐀𝐓𝐄 𝐀𝐂𝐂𝐄𝐒𝐒 𝐓𝐎𝐊𝐄𝐍\n"
            f"𝐉𝐖𝐓 𝐆𝐄𝐍 - 𝐆𝐄𝐍𝐄𝐑𝐀𝐓𝐄 𝐉𝐖𝐓 𝐅𝐑𝐎𝐌 𝐓𝐎𝐊𝐄𝐍\n\n"
            f"𝐏𝐎𝐖𝐄𝐑𝐄𝐃 𝐁𝐘 @exucoder",
            reply_markup=get_main_keyboard()
        )
        return
    
    # Admin panel buttons
    elif text == "𝐀𝐃𝐃 𝐖𝐇𝐈𝐓𝐄𝐋𝐈𝐒𝐓":
        context.user_data['conversation'] = 'admin_add'
        await update.message.reply_text(
            f"𝐀𝐃𝐃 𝐓𝐎 𝐖𝐇𝐈𝐓𝐄𝐋𝐈𝐒𝐓\n\n𝐒𝐄𝐍𝐃 𝐓𝐇𝐄 𝐔𝐒𝐄𝐑 𝐈𝐃 𝐓𝐎 𝐀𝐃𝐃:\n\n𝐓𝐘𝐏𝐄 𝐂𝐀𝐍𝐂𝐄𝐋 𝐓𝐎 𝐂𝐀𝐍𝐂𝐄𝐋.",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    elif text == "𝐑𝐄𝐌𝐎𝐕𝐄 𝐖𝐇𝐈𝐓𝐄𝐋𝐈𝐒𝐓":
        context.user_data['conversation'] = 'admin_remove'
        await update.message.reply_text(
            f"𝐑𝐄𝐌𝐎𝐕𝐄 𝐅𝐑𝐎𝐌 𝐖𝐇𝐈𝐓𝐄𝐋𝐈𝐒𝐓\n\n𝐒𝐄𝐍𝐃 𝐓𝐇𝐄 𝐔𝐒𝐄𝐑 𝐈𝐃 𝐓𝐎 𝐑𝐄𝐌𝐎𝐕𝐄:\n\n𝐓𝐘𝐏𝐄 𝐂𝐀𝐍𝐂𝐄𝐋 𝐓𝐎 𝐂𝐀𝐍𝐂𝐄𝐋.",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    elif text == "𝐕𝐈𝐄𝐖 𝐖𝐇𝐈𝐓𝐄𝐋𝐈𝐒𝐓":
        whitelist = get_whitelist()
        if not whitelist:
            await update.message.reply_text("𝐖𝐇𝐈𝐓𝐄𝐋𝐈𝐒𝐓\n\n𝐄𝐌𝐏𝐓𝐘 𝐋𝐈𝐒𝐓!")
        else:
            msg = "𝐖𝐇𝐈𝐓𝐄𝐋𝐈𝐒𝐓𝐄𝐃 𝐔𝐒𝐄𝐑𝐒\n\n"
            for uid, uname, date in whitelist:
                msg += f"• {uid} | {uname}\n"
            await update.message.reply_text(msg)
        return
    
    elif text == "𝐕𝐈𝐄𝐖 𝐒𝐓𝐀𝐓𝐒":
        whitelist = get_whitelist()
        total_users = len(whitelist)
        await update.message.reply_text(
            f"𝐁𝐎𝐓 𝐒𝐓𝐀𝐓𝐈𝐒𝐓𝐈𝐂𝐒\n\n𝐓𝐎𝐓𝐀𝐋 𝐔𝐒𝐄𝐑𝐒: {total_users}\n𝐓𝐎𝐓𝐀𝐋 𝐀𝐃𝐌𝐈𝐍𝐒: {len(ADMIN_IDS)}"
        )
        return
    
    # Handle conversation flows
    if 'conversation' in context.user_data:
        conv = context.user_data['conversation']
        
        if conv == 'change_bind':
            step = context.user_data.get('step', 1)
            if step == 1:
                context.user_data['access_token'] = text
                context.user_data['step'] = 2
                await update.message.reply_text(f"𝐂𝐇𝐀𝐍𝐆𝐄 𝐁𝐈𝐍𝐃\n\n𝐒𝐓𝐄𝐏 𝟐/𝟓 - 𝐒𝐄𝐍𝐃 𝐘𝐎𝐔𝐑 𝐎𝐋𝐃 𝐄𝐌𝐀𝐈𝐋:")
            elif step == 2:
                context.user_data['old_email'] = text
                context.user_data['step'] = 3
                await update.message.reply_text(f"𝐂𝐇𝐀𝐍𝐆𝐄 𝐁𝐈𝐍𝐃\n\n𝐒𝐓𝐄𝐏 𝟑/𝟓 - 𝐒𝐄𝐍𝐃 𝐘𝐎𝐔𝐑 𝐍𝐄𝐖 𝐄𝐌𝐀𝐈𝐋:")
            elif step == 3:
                context.user_data['new_email'] = text
                context.user_data['step'] = 4
                await update.message.reply_text(f"𝐂𝐇𝐀𝐍𝐆𝐄 𝐁𝐈𝐍𝐃\n\n𝐒𝐓𝐄𝐏 𝟒/𝟓 - 𝐄𝐍𝐓𝐄𝐑 𝐎𝐓𝐏 𝐅𝐑𝐎𝐌 {context.user_data['old_email']}:")
            elif step == 4:
                context.user_data['otp_old'] = text
                context.user_data['step'] = 5
                await update.message.reply_text(f"𝐂𝐇𝐀𝐍𝐆𝐄 𝐁𝐈𝐍𝐃\n\n𝐒𝐓𝐄𝐏 𝟓/𝟓 - 𝐄𝐍𝐓𝐄𝐑 𝐎𝐓𝐏 𝐅𝐑𝐎𝐌 {context.user_data['new_email']}:")
            elif step == 5:
                result = change_bind_email_api(
                    context.user_data['access_token'],
                    context.user_data['old_email'],
                    context.user_data['new_email'],
                    context.user_data['otp_old'],
                    text
                )
                if 'success' in result:
                    msg = f"𝐂𝐇𝐀𝐍𝐆𝐄 𝐁𝐈𝐍𝐃\n\n✅ {result['success']}"
                else:
                    msg = f"❌ 𝐅𝐀𝐈𝐋𝐄𝐃!\n\n{result.get('error', '𝐔𝐍𝐊𝐍𝐎𝐖𝐍 𝐄𝐑𝐑𝐎𝐑')}"
                await update.message.reply_text(msg, reply_markup=get_main_keyboard())
                del context.user_data['conversation']
                del context.user_data['step']
        
        elif conv == 'unbind':
            step = context.user_data.get('step', 1)
            if step == 1:
                context.user_data['access_token'] = text
                context.user_data['step'] = 2
                await update.message.reply_text(f"𝐔𝐍𝐁𝐈𝐍𝐃\n\n𝐒𝐓𝐄𝐏 𝟐/𝟑 - 𝐒𝐄𝐍𝐃 𝐘𝐎𝐔𝐑 𝐄𝐌𝐀𝐈𝐋:")
            elif step == 2:
                context.user_data['email'] = text
                context.user_data['step'] = 3
                await update.message.reply_text(f"𝐔𝐍𝐁𝐈𝐍𝐃\n\n𝐒𝐓𝐄𝐏 𝟑/𝟑 - 𝐄𝐍𝐓𝐄𝐑 𝐎𝐓𝐏 𝐅𝐑𝐎𝐌 {text}:")
            elif step == 3:
                result = unbind_email_api(context.user_data['access_token'], context.user_data['email'], text)
                if 'success' in result:
                    msg = f"𝐔𝐍𝐁𝐈𝐍𝐃\n\n✅ {result['success']}"
                else:
                    msg = f"❌ 𝐅𝐀𝐈𝐋𝐄𝐃!\n\n{result.get('error', '𝐔𝐍𝐊𝐍𝐎𝐖𝐍 𝐄𝐑𝐑𝐎𝐑')}"
                await update.message.reply_text(msg, reply_markup=get_main_keyboard())
                del context.user_data['conversation']
                del context.user_data['step']
        
        elif conv == 'cancel_bind':
            result = cancel_bind_api(text)
            if 'success' in result:
                msg = f"𝐂𝐀𝐍𝐂𝐄𝐋 𝐁𝐈𝐍𝐃\n\n✅ {result['success']}"
            else:
                msg = f"❌ 𝐅𝐀𝐈𝐋𝐄𝐃!\n\n{result.get('error', '𝐔𝐍𝐊𝐍𝐎𝐖𝐍 𝐄𝐑𝐑𝐎𝐑')}"
            await update.message.reply_text(msg, reply_markup=get_main_keyboard())
            del context.user_data['conversation']
        
        elif conv == 'bind_info':
            result = check_bind_info_api(text)
            if result.get('status') == 'success' and 'data' in result:
                data = result['data']
                msg = (
                    f"𝐁𝐈𝐍𝐃 𝐈𝐍𝐅𝐎\n\n"
                    f"𝐂𝐔𝐑𝐑𝐄𝐍𝐓: {data.get('current_email', '𝐍/𝐀')}\n"
                    f"𝐏𝐄𝐍𝐃𝐈𝐍𝐆: {data.get('pending_email', '𝐍/𝐀')}\n"
                    f"𝐂𝐎𝐔𝐍𝐓𝐃𝐎𝐖𝐍: {data.get('countdown_human', '𝟎')}\n\n"
                    f"{result.get('summary', '𝐔𝐍𝐊𝐍𝐎𝐖𝐍')}"
                )
            else:
                msg = f"❌ 𝐅𝐀𝐈𝐋𝐄𝐃!\n\n{result.get('message', '𝐔𝐍𝐊𝐍𝐎𝐖𝐍 𝐄𝐑𝐑𝐎𝐑')}"
            await update.message.reply_text(msg, reply_markup=get_main_keyboard())
            del context.user_data['conversation']
        
        elif conv == 'eat_to_token':
            result = eat_to_access_api(text)
            full_response = json.dumps(result, indent=2, ensure_ascii=False)
            
            if 'access_token' in result:
                msg = f"𝐄𝐀𝐓 𝐓𝐎 𝐓𝐎𝐊𝐄𝐍\n\n✅ 𝐒𝐔𝐂𝐂𝐄𝐒𝐒!\n\n𝐅𝐔𝐋𝐋 𝐑𝐄𝐒𝐏𝐎𝐍𝐒𝐄:\n─────────────────────\n{full_response}\n─────────────────────\n\n🔑 𝐀𝐂𝐂𝐄𝐒𝐒 𝐓𝐎𝐊𝐄𝐍:\n{result['access_token']}"
                if 'game_uid' in result:
                    msg += f"\n🎮 𝐆𝐀𝐌𝐄 𝐔𝐈𝐃: {result['game_uid']}"
                if 'nickname' in result:
                    msg += f"\n📛 𝐍𝐈𝐂𝐊𝐍𝐀𝐌𝐄: {result['nickname']}"
            else:
                msg = f"❌ 𝐅𝐀𝐈𝐋𝐄𝐃!\n\n𝐅𝐔𝐋𝐋 𝐑𝐄𝐒𝐏𝐎𝐍𝐒𝐄:\n─────────────────────\n{full_response}\n─────────────────────\n\n{result.get('error', '𝐔𝐍𝐊𝐍𝐎𝐖𝐍 𝐄𝐑𝐑𝐎𝐑')}"
            
            await update.message.reply_text(msg, reply_markup=get_main_keyboard())
            del context.user_data['conversation']
        
        elif conv == 'revoke':
            result = revoke_token_api(text)
            full_response = json.dumps(result, indent=2, ensure_ascii=False)
            
            if result.get('status') == 'success' or result.get('success'):
                msg = f"𝐑𝐄𝐕𝐎𝐊𝐄\n\n✅ 𝐓𝐎𝐊𝐄𝐍 𝐑𝐄𝐕𝐎𝐊𝐄𝐃!\n\n𝐅𝐔𝐋𝐋 𝐑𝐄𝐒𝐏𝐎𝐍𝐒𝐄:\n─────────────────────\n{full_response}"
            else:
                msg = f"❌ 𝐅𝐀𝐈𝐋𝐄𝐃!\n\n𝐅𝐔𝐋𝐋 𝐑𝐄𝐒𝐏𝐎𝐍𝐒𝐄:\n─────────────────────\n{full_response}\n─────────────────────\n\n{result.get('error', '𝐔𝐍𝐊𝐍𝐎𝐖𝐍 𝐄𝐑𝐑𝐎𝐑')}"
            
            await update.message.reply_text(msg, reply_markup=get_main_keyboard())
            del context.user_data['conversation']
        
        elif conv == 'jwt':
            result = generate_jwt_api(text)
            full_response = json.dumps(result, indent=2, ensure_ascii=False)
            
            if result.get('success'):
                msg = f"𝐉𝐖𝐓 𝐆𝐄𝐍𝐄𝐑𝐀𝐓𝐎𝐑\n\n✅ 𝐒𝐔𝐂𝐂𝐄𝐒𝐒!\n\n𝐅𝐔𝐋𝐋 𝐑𝐄𝐒𝐏𝐎𝐍𝐒𝐄:\n─────────────────────\n{full_response}\n─────────────────────\n\n📋 𝐀𝐂𝐂𝐎𝐔𝐍𝐓 𝐔𝐈𝐃: {result.get('account_uid', '𝐍/𝐀')}\n📍 𝐑𝐄𝐆𝐈𝐎𝐍: {result.get('region', '𝐍/𝐀')}"
                
                if 'jwt_decoded' in result and 'payload' in result['jwt_decoded']:
                    payload = result['jwt_decoded']['payload']
                    msg += f"\n👤 𝐍𝐈𝐂𝐊𝐍𝐀𝐌𝐄: {payload.get('nickname', '𝐍/𝐀')}\n📱 𝐂𝐋𝐈𝐄𝐍𝐓 𝐕𝐄𝐑𝐒𝐈𝐎𝐍: {payload.get('client_version', '𝐍/𝐀')}"
                    exp_time = payload.get('exp', 0)
                    if exp_time:
                        exp_date = datetime.fromtimestamp(exp_time).strftime('%Y-%m-%d %H:%M:%S')
                        msg += f"\n⏰ 𝐄𝐗𝐏𝐈𝐑𝐄𝐒 𝐀𝐓: {exp_date}"
                
                jwt_token = result.get('jwt', '𝐍/𝐀')
                msg += f"\n\n🔑 𝐉𝐖𝐓 𝐓𝐎𝐊𝐄𝐍:\n{jwt_token[:150]}..."
            else:
                msg = f"❌ 𝐅𝐀𝐈𝐋𝐄𝐃!\n\n𝐅𝐔𝐋𝐋 𝐑𝐄𝐒𝐏𝐎𝐍𝐒𝐄:\n─────────────────────\n{full_response}\n─────────────────────\n\n{result.get('error', '𝐔𝐍𝐊𝐍𝐎𝐖𝐍 𝐄𝐑𝐑𝐎𝐑')}"
            
            await update.message.reply_text(msg, reply_markup=get_main_keyboard())
            del context.user_data['conversation']
        
        elif conv == 'admin_add':
            try:
                target_id = int(text)
                user = await context.bot.get_chat(target_id)
                username = user.first_name or str(target_id)
                add_to_whitelist(target_id, username, user_id)
                await update.message.reply_text(
                    f"✅ 𝐔𝐒𝐄𝐑 𝐀𝐃𝐃𝐄𝐃!\n\n𝐔𝐒𝐄𝐑 𝐈𝐃: {target_id}\n𝐍𝐀𝐌𝐄: {username}",
                    reply_markup=get_admin_keyboard()
                )
            except:
                await update.message.reply_text("❌ 𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐔𝐒𝐄𝐑 𝐈𝐃!", reply_markup=get_admin_keyboard())
            del context.user_data['conversation']
        
        elif conv == 'admin_remove':
            try:
                target_id = int(text)
                remove_from_whitelist(target_id)
                await update.message.reply_text(
                    f"✅ 𝐔𝐒𝐄𝐑 𝐑𝐄𝐌𝐎𝐕𝐄𝐃!\n\n𝐔𝐒𝐄𝐑 𝐈𝐃: {target_id}",
                    reply_markup=get_admin_keyboard()
                )
            except:
                await update.message.reply_text("❌ 𝐈𝐍𝐕𝐀𝐋𝐈𝐃 𝐔𝐒𝐄𝐑 𝐈𝐃!", reply_markup=get_admin_keyboard())
            del context.user_data['conversation']

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'conversation' in context.user_data:
        del context.user_data['conversation']
    await update.message.reply_text("✅ 𝐎𝐏𝐄𝐑𝐀𝐓𝐈𝐎𝐍 𝐂𝐀𝐍𝐂𝐄𝐋𝐋𝐄𝐃!", reply_markup=get_main_keyboard())


# ═══════════════════════════════════════════════════════════════
# FIXED: Reversed architecture for Render compatibility
# Flask runs as the MAIN foreground service (required by Render)
# Telegram bot runs in a BACKGROUND daemon thread
# ═══════════════════════════════════════════════════════════════

def run_telegram_bot():
    """Run the Telegram bot in a background thread with its own event loop."""
    async def bot_main():
        try:
            if not BOT_TOKEN or ":" not in BOT_TOKEN:
                logger.error("❌ BOT_TOKEN is missing or invalid! Set it in Render environment variables.")
                return

            application = Application.builder().token(BOT_TOKEN).build()
            application.add_handler(CommandHandler("start", start))
            application.add_handler(CommandHandler("cancel", cancel))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

            logger.info("🤖 BOT: Initializing...")
            await application.initialize()
            await application.start()
            await application.updater.start_polling()
            logger.info("✅ BOT: Running and polling for messages!")

            # Keep the bot alive indefinitely
            while True:
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"❌ BOT CRASHED: {e}", exc_info=True)
            # Keep thread alive so it doesn't kill Flask - attempt restart after delay
            await asyncio.sleep(10)
            logger.info("🔄 BOT: Attempting to restart...")

    # Run the async bot_main in a fresh event loop (required for threads)
    try:
        asyncio.run(bot_main())
    except Exception as e:
        logger.error(f"❌ Bot thread fatal error: {e}", exc_info=True)


if __name__ == "__main__":
    # Start Telegram bot in a background daemon thread
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()

    logger.info(f"🌐 FLASK: Starting server on port {PORT}")
    logger.info("📝 If Render health checks fail, check that PORT env var matches.")

    # Run Flask as the MAIN foreground process (Render requires this)
    # This keeps the process alive and binds to the expected port
    app_flask.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
