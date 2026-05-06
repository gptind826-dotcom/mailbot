#!/usr/bin/env python3

import os
import sys
import threading
import time
from flask import Flask, jsonify
from datetime import datetime

# Import the bot application from app.py
from app import run_bot

PORT = int(os.environ.get("PORT", 8080))
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return jsonify({
        "status": "active",
        "bot": "EXRMAIL Bot",
        "uptime": time.strftime("%Y-%m-%d %H:%M:%S"),
        "version": "2.0",
        "message": "Bot is running on Telegram"
    })

@app_flask.route('/health')
def health():
    return jsonify({
        "status": "healthy", 
        "timestamp": datetime.now().isoformat()
    })

def run_flask():
    """Run Flask server for health checks"""
    print(f"🌐 Starting Flask server on port {PORT}")
    app_flask.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

def main():
    """Main entry point - runs both Flask and Telegram bot"""
    print("=" * 50)
    print("🚀 EXRMAIL BOT STARTING...")
    print("=" * 50)
    
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print(f"✅ Flask thread started on port {PORT}")
    
    # Run Telegram bot (this will block)
    print("🤖 Starting Telegram bot...")
    run_bot()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
