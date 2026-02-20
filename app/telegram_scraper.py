from telethon import TelegramClient
from datetime import datetime
from pathlib import Path
import os
import json
import dotenv
import configparser
import argparse

dotenv.load_dotenv()
config = configparser.ConfigParser()
config.read("tg_conn.ini")

app_id=config["TELEGRAM"].getint("app_id")
app_hash = config["TELEGRAM"]["app_hash"]
client = TelegramClient('anon', app_id, app_hash)
# argparser = argparse.ArgumentParser("telegram_scraper")

argparser = argparse.ArgumentParser("telegram_scraper")
argparser.add_argument("-u", dest="username", nargs="+", required=True)
argparser.add_argument("-d", dest="day", type=int, required=True) 
argparser.add_argument("-y", dest="year", type=int, required=True) 
argparser.add_argument("-m", dest="month", type=int, required=True)
argparser.add_argument("-l", dest="limit", type=int)


async def get_channel_id(account_name: str):
    try:
        channel_id = await client.get_entity(account_name)
    except:
        return None
    return channel_id.id 

async def get_post(channel_id: int, datetime_: datetime, limit: int) -> dict:
    """returns channel's post"""
    post = await client.get_messages(channel_id, offset_date=datetime_, limit=limit)
    return post
    

async def main(fp_save_to: str, channel_id: int, datetime_: datetime, limit: int) -> list[dict]:
    posts = await get_post(channel_id, datetime_, limit=limit)
    channel = await client.get_entity(channel_id)

    posts = [
        {
            "channel_id": channel_id,
            "username": channel.username,
            "datetime": post.date.strftime(format="%Y/%m/%d_%H:%M"),
            "message": post.message,
            "reactions": [r.reaction.emoticon for r in post.reactions.results]
        } for post in posts
    ] 
    
    existing_posts = []
    if not os.path.exists(fp_save_to):
        parent_path = Path(fp_save_to).parent
        if parent_path != ".":
            os.makedirs(parent_path, exist_ok=True)

        with open(fp_save_to, mode="w") as f:
            json.dump(posts, f)
    else:
        with open(fp_save_to) as f:
            existing_posts = json.load(f)
        existing_posts.extend(posts)

        with open(fp_save_to, mode="w") as f:
            json.dump(existing_posts, f)

    return posts


def load_channnels_ids(channels, fp):
    # channels = ["KyivCityOfficial", "dtek_ua", "kyivmaps"]
    # fp = "tg_channels.json"
    with open(Path(fp), mode="w") as f:
        channels_info = {channel: client.loop.run_until_complete(get_channel_id(channel)) for channel in channels}
        json.dump(channels_info, f)

def load_channel(channels: dict[str, int], channel_name: str) -> tuple[int, bool]:
    """Returns channel's id and value 'if present in data base'"""
    channel_id = channels.get(channel_name, None)
    channel_in_base = channel_id is not None
    if not channel_in_base:
        channel_id = client.loop.run_until_complete(get_channel_id(channel_name))
    return channel_id, channel_in_base
    

with client:
    fp = "tg_channels.json"
    if not os.path.exists(fp):
        os.makedirs(Path(fp), exist_ok=True)
        with open(fp, "w") as f:
            f.write("")
        channels = dict()

    with open(Path(fp), mode="r") as f:
        channels = json.load(f)
    # channels = {"KyivCityOfficial": 1247556894, "dtek_ua": 1399067835, "kyivmaps": 1395254824}

    posts_fp = "posts.json"

    requested_channels = argparser.parse_args().username
    requested_channels_info = [load_channel(channels, channel_name) for channel_name in requested_channels]
    valid_channels = [channel_id for channel_id, _ in requested_channels_info if channel_id is not None]
    unknown_channels = [(channel_name, channel_id) for channel_name, (channel_id, is_present) in zip(requested_channels, requested_channels_info) if not is_present]

    if len(unknown_channels) > 0:
        channels.update(unknown_channels)
        with open("tg_channels.json", "w") as f:
            json.dump(channels, f)

    try:
        year, month, day = argparser.parse_args().year, argparser.parse_args().month, argparser.parse_args().day
        datetime_ = datetime(year, month, day)
    except SystemExit:
        print("Wrong date format, the current date is used instead. ")
        datetime_ = datetime.now()

    # print(datetime_.strftime("%Y/%m/%d"))
    # [print(f"{c_n}: {c_id}") for c_n, (c_id, _) in zip(requested_channels, requested_channels_info)]
    limit = argparser.parse_args().limit
    limit = 1 if limit is None else limit
    try:
        posts = [client.loop.run_until_complete(main(posts_fp, channel_id, datetime_, limit=limit)) for channel_id in valid_channels]
        posts = [post for ch_posts in posts for post in ch_posts]

        [print(post) for post in posts]
    except Exception as ex:
        print(ex)
