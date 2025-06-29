# bot.py

import os
import logging
from pyrogram import Client, filters
from downloader import download_vimeo_json

BOT_TOKEN = "your_bot_token"
API_ID = 1234567
API_HASH = "your_api_hash"

app = Client("vimeo_bot", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

logging.basicConfig(level=logging.INFO)

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply("🎥 Send me a Vimeo `playlist.json` URL to download.")

@app.on_message(filters.text & ~filters.command(["start"]))
async def handle_url(client, message):
    url = message.text.strip()
    await message.reply("⏳ Downloading... Please wait.")

    try:
        output_folder = "downloads"
        os.makedirs(output_folder, exist_ok=True)

        result_file = download_vimeo_json(url, output_folder)
        await message.reply_document(result_file, caption="✅ Done!")
        os.remove(result_file)

    except Exception as e:
        logging.error(str(e))
        await message.reply(f"❌ Error: {str(e)}")

app.run()
