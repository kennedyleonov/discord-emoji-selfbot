import asyncio
import json
import sys

import aiohttp
import time
import keyring
import logging

from pathlib import Path
from typing import Dict, Tuple, Generator, Optional, List
from dataclasses import dataclass

from discord import Emoji, Message
from discord.ext import commands

DELETE_EMOJI_TIMEOUT_SECONDS=15
COMMAND_PREFIX='?'
KEYRING_SERVICE = 'dsembot'
CRED_FILE_NAME='cred.txt'
CONFIG_FILE_NAME='config.json'

# emoji_url -> Tuple[emoji_code, create_timestamp]
created_emojis_cache: Dict[str, Tuple[str, int]] = {}

logger = logging.getLogger('emojibot')
bot = commands.Bot(command_prefix=COMMAND_PREFIX, self_bot=False)

@dataclass
class AvailableEmoji:
    emoji_id: int
    emoji_name: str
    emoji_url: str
    guild_id: int

@dataclass
class EmojiPattern:
    pattern_raw_text: str
    pattern_type: str
    pattern_emoji_text: str
    raw_start_pos: int
    raw_end_pos: int

def run_emoji_bot():
    global DELETE_EMOJI_TIMEOUT_SECONDS
    global logger
    global bot

    token = None

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout
    )
    logging.basicConfig(level=logging.INFO)

    logger.setLevel(logging.INFO)

    logging.getLogger('discord').setLevel(logging.ERROR)
    logging.getLogger('discord.http').setLevel(logging.ERROR)
    logging.getLogger('discord.client').setLevel(logging.ERROR)
    logging.getLogger('discord.gateway').setLevel(logging.ERROR)

    cred_file = Path(CRED_FILE_NAME)
    if cred_file.exists():
        content = cred_file.read_text(encoding='utf-8')
        if len(content) > 0:
            token = content.strip()
            logger.info(f'read token from file "..."')
            cred_file.unlink()

    if token:
        keyring.set_password(KEYRING_SERVICE, 'token', token)
    else:
        token = keyring.get_password(KEYRING_SERVICE, 'token')
        logger.info(f'read token from keyring "..."')

    if not token:
        logger.info('no token available')
        exit(1)

    config_file = Path(CONFIG_FILE_NAME)
    if config_file.exists():
        logger.info(f'reading config file...')
        content = config_file.read_text(encoding='utf-8')
        try:
            obj = json.loads(content)
            if obj['DELETE_EMOJI_TIMEOUT_SECONDS']:
                DELETE_EMOJI_TIMEOUT_SECONDS = obj['DELETE_EMOJI_TIMEOUT_SECONDS']
        except json.decoder.JSONDecodeError:
            logger.error("can't decode config file")
            exit(1)
        except KeyError:
            pass
    else:
        logger.info('no config file found, using defaults...')

    bot.run(token)

@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})')
    for g in bot.guilds:
        logger.debug(g.name)

@bot.event
async def on_message(message):
    logger.debug(f'received message: {message.content} in "{message.guild.name}" from: {message.author.name}')
    if message.author.id != bot.user.id:
        return

    text = message.content

    command = None
    if text.startswith('\\'):
        next_symbol = text.find(' ')
        if next_symbol > 0:
            cmd_text = text[1:next_symbol]
            command = cmd_text

    created_emojis_list = []
    data = text
    result = bytearray()
    last_char = 0
    for pattern in match_emoji_patterns(text):
        logger.debug(pattern)
        available_emoji = None
        guild_loop_exit_flag = False
        pattern_loop_skip_flag = False

        # check if message uses current guild's emoji
        for cur_emoji in message.guild.emojis:
            if (
                    (pattern.pattern_type == 'id' and pattern.pattern_emoji_text == str(cur_emoji.id))
                    or
                    (pattern.pattern_type == 'name' and pattern.pattern_emoji_text == cur_emoji.name)
            ):
                pattern_loop_skip_flag = True
                break

        if pattern_loop_skip_flag:
            continue

        for guild in bot.guilds:
            # logger.debug(f'checking guild {guild.id} {guild.name}')
            if guild.id == message.guild.id:
                continue
            for cur_emoji in guild.emojis:
                if (
                    (pattern.pattern_type == 'id' and pattern.pattern_emoji_text == str(cur_emoji.id))
                    or
                    (pattern.pattern_type == 'name' and pattern.pattern_emoji_text == cur_emoji.name)
                ):
                    available_emoji = AvailableEmoji(cur_emoji.id, cur_emoji.name, cur_emoji.url, guild.id)
                    guild_loop_exit_flag = True
                    break
            if guild_loop_exit_flag:
                break

        if not available_emoji:
            continue

        logger.debug(f'available emoji found: {available_emoji}')

        new_emoji = None
        cached = created_emojis_cache.get(available_emoji.emoji_url)
        if cached:
            create_time = cached[1]
            current_time = int(time.time())
            if (current_time - create_time) < DELETE_EMOJI_TIMEOUT_SECONDS * 0.9:
                new_emoji = created_emojis_cache.get(available_emoji.emoji_url)[0]
                logger.info(f'using cached {new_emoji}')
            else:
                logger.info(f'removing cached {available_emoji.emoji_name}')
                created_emojis_cache.pop(available_emoji.emoji_url)
                cached = False

        if not cached:
            new_emoji = await create_custom_emoji(message.guild, available_emoji.emoji_name, available_emoji.emoji_url)
            if not new_emoji:
                logger.error(f"can't create emoji: ${available_emoji.emoji_name}")
                continue
            created_emojis_cache[available_emoji.emoji_url] = (str(new_emoji), int(time.time()))
        created_emojis_list.append(str(new_emoji))

        result += (data[last_char:pattern.raw_start_pos]).encode('utf-8')
        result += str(new_emoji).encode('utf-8')
        last_char = pattern.raw_end_pos + 1

    result += (data[last_char:]).encode('utf-8')
    result = result.decode('utf-8')

    if last_char > 0:
        if command:
            if command == 'd':
                await message.delete()
            elif command == 'r' and len(created_emojis_list) > 0:
                flag = False
                async for msg in message.channel.history(limit=4):
                    if msg.id == message.id:
                        flag = True
                        continue
                    elif flag:
                        try:
                            await message.delete()
                            await msg.add_reaction(created_emojis_list[0])
                        except Exception as exception:
                            logger.error('error deleting message or adding reaction:')
                            logger.error(exception)
                        break

        else:
            await message.edit(content=result)

async def create_custom_emoji(guild, name, image_url) -> Emoji|None:
    img_bytes = None
    async with aiohttp.ClientSession() as session:
        async with session.get(image_url) as resp:
            if resp.status != 200:
                return None
            img_bytes = await resp.read()
    discord_emoji_data = await guild.create_custom_emoji(name=name, image=img_bytes)
    logger.info(f'created {discord_emoji_data} in "{guild.name}"')
    asyncio.create_task(delay_async_func(DELETE_EMOJI_TIMEOUT_SECONDS, delete_custom_emoji, guild, discord_emoji_data))
    return discord_emoji_data

async def delete_custom_emoji(guild, emoji) -> None:
    emoji_code = str(emoji)
    await guild.delete_emoji(emoji)
    logger.info(f'deleted {emoji_code}')

# if not message.guild.me.guild_permissions.manage_emojis:
#     await message.channel.send("I don't have the 'Manage Emojis' permission")
#     return None
# return f'<:{cur_emoji['name']}:{cur_emoji['id']}>'

def match_emoji_patterns(text) -> Generator[EmojiPattern, None, None]:
    i = 0
    while i < len(text):
        if text[i] == ':':
            next_symbol = text.find(':', i + 1)
            if next_symbol == -1:
                break
            else:
                logger.debug(f'name_match: next_symbol: {next_symbol}, i: {i}, text: {text[i + 1:next_symbol]},')
                if (next_symbol - i - 1 >= 2) and (next_symbol - i - 1 <= 32):
                    yield EmojiPattern(text[i:next_symbol + 1], 'name', text[i + 1:next_symbol], i, next_symbol)
                i = next_symbol
        i += 1

    i = 0
    number_start = -1
    while i < len(text):
        if text[i].isdigit():
            if number_start == -1:
                number_start = i
        else:
            if number_start != -1 and i - number_start >= 2:
                yield EmojiPattern(text[number_start:i], 'id', text[number_start:i], number_start, i - 1)
                number_start = -1
        i += 1
    if number_start != -1 and len(text) - 1 - number_start >= 2:
        yield EmojiPattern(text[number_start:i], 'id', text[number_start:], number_start, len(text) - 1)

async def delay_async_func(seconds, func, *args):
    await asyncio.sleep(seconds)
    return await func(*args)