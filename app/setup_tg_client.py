import asyncio
from telethon import TelegramClient

import dotenv
import configparser


dotenv.load_dotenv()
config = configparser.ConfigParser()
config.read("tg_conn.ini")

app_id=config["TELEGRAM"].getint("app_id")
app_hash = config["TELEGRAM"]["app_hash"]


async def setup_tg_client():
    client = TelegramClient('anon', app_id, app_hash)
            
    return client

if __name__ == "__main__":
    asyncio.run(setup_tg_client())