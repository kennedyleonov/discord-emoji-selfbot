import logging
from typing import List, Callable, Any

import pytest
import keyring
from unittest.mock import AsyncMock
from types import SimpleNamespace

from tests.mock_bot import MockMessage, MockGuild, MockEmoji, MockUser

import emojibot.bot as bot

logger = logging.getLogger(__name__)

message_id_counter = 10000
emoji_id_counter = 20000
created_emojis = []

def dataset():
    own_guild_emojis = [
        MockEmoji(id=1, name='emoji1', url='emoji1'),
        MockEmoji(id=2, name='emoji2', url='emoji2'),
        MockEmoji(id=3, name='emoji3', url='emoji3')
    ]
    target_guild_emojis = [
        MockEmoji(id=4, name='emoji4', url='emoji4'),
        MockEmoji(id=5, name='emoji5', url='emoji5'),
        MockEmoji(id=6, name='emoji6', url='emoji6')
    ]
    other_guild_emojis = [
        MockEmoji(id=7, name='emoji7', url='emoji7'),
        MockEmoji(id=8, name='emoji8', url='emoji8'),
        MockEmoji(id=9, name='emoji9', url='emoji9')
    ]

    guilds = {
        'own': MockGuild(id=10, name='My Guild', emojis=own_guild_emojis),
        'target': MockGuild(id=20, name='Target Guild', emojis=target_guild_emojis),
        'other': MockGuild(id=30, name='Other Guild', emojis=other_guild_emojis)
    }

    bot_user = MockUser(110, 'BotUser')
    some_user = MockUser(120, 'SomeUser')
    some_user2 = MockUser(130, 'SomeUser2')

    async def create_custom_emoji(guild, name, image_url) -> MockEmoji:
        # genid = hash(image_url) % 10 ** 6
        # genid = random.randint(1, 10**10)
        global emoji_id_counter
        emoji_id_counter += 1
        genid = emoji_id_counter
        e = MockEmoji(id=genid, name=name, url=image_url)
        created_emojis.append(e)
        return e

    mock_bot = SimpleNamespace(
        user=bot_user,
        guilds=list(guilds.values()),
        run=lambda token: None,
        on_ready=bot.on_ready,
        on_message=bot.on_message,
    )

    return SimpleNamespace(
        create_custom_emoji=create_custom_emoji,
        mock_bot=mock_bot,
        own_guild_emojis=own_guild_emojis,
        target_guild_emojis=target_guild_emojis,
        other_guild_emojis=other_guild_emojis,
        guilds=guilds,
        bot_user=bot_user,
        some_user=some_user,
        some_user2=some_user2
    )

default_dataset = dataset()

@pytest.fixture(autouse=True)
def patch_keyring(monkeypatch):
    mock_keyring = SimpleNamespace(
        get_password=lambda service, username: 'token',
        set_password=lambda service, username, password: None,
    )
    monkeypatch.setattr(keyring, 'get_password', mock_keyring.get_password, raising=False)
    monkeypatch.setattr(keyring, 'set_password', mock_keyring.set_password, raising=False)

@pytest.fixture(autouse=True)
def clear_created_emojis():
    created_emojis.clear()
    bot.created_emojis_cache.clear()

@pytest.fixture
def bot_setup_default(monkeypatch):
    monkeypatch.setattr(bot, 'bot', default_dataset.mock_bot, raising=False)
    monkeypatch.setattr(bot, 'create_custom_emoji', default_dataset.create_custom_emoji, raising=False)
    bot.created_emojis_cache.clear()

@pytest.fixture
def bot_setup_custom(monkeypatch):
    def patch(custom_dataset):
        monkeypatch.setattr(bot, 'bot', custom_dataset.mock_bot, raising=False)
        monkeypatch.setattr(bot, 'create_custom_emoji', custom_dataset.create_custom_emoji, raising=False)
    return patch

@pytest.fixture
def mock_time(monkeypatch):
    import time
    def patch(f):
        monkeypatch.setattr(time, 'time', f, raising=False)
    return patch

def sample_history():
    message_factory = lambda n: create_mock_message(
        _id=-1,
        author=default_dataset.bot_user,
        content=f'sample message {n}',
        guild=default_dataset.guilds['target']
    )
    def f(limit=2):
        result = []
        for i in range(limit):
            result.append(message_factory(i))
        return result
    return f

def create_mock_message(
        _id: int,
        author: MockUser,
        content: str,
        guild: MockGuild,
        edit=None,
        delete=None,
        add_reaction=None,
        history: Callable[[int], List[Any]]=lambda limit: [],
):
    global message_id_counter
    message_id_counter += 1

    if _id <= 0:
        _id = message_id_counter
    if not edit:
        edit = AsyncMock()
    if not delete:
        delete = AsyncMock()
    if not add_reaction:
        add_reaction = AsyncMock()

    async def history_callable(limit):
        for item in history(limit):
            yield item

    return SimpleNamespace(
        id=_id,
        author=author,
        content=content,
        guild=guild,
        edit=edit,
        delete=delete,
        channel=SimpleNamespace(
            history=history_callable
        ),
        add_reaction=add_reaction
    )

@pytest.mark.asyncio
async def test_one_emoji_target_guild(bot_setup_default):
    data = dataset()

    message = create_mock_message(
        _id=0,
        author=data.bot_user,
        content=f'hello :emoji1:',
        guild=data.guilds['target'],
        edit=AsyncMock(),
        delete=AsyncMock(),
    )

    await bot.on_message(message)
    message.edit.assert_awaited_once()
    message.delete.assert_not_awaited()
    assert len(created_emojis) == 1
    assert message.edit.call_args.kwargs['content'] == f'hello <:emoji1:{created_emojis[0].id}>'

@pytest.mark.asyncio
async def test_message_from_non_owner(bot_setup_custom):
    data = dataset()
    emoji_creator = AsyncMock(side_effect=AssertionError("create_custom_emoji should not be called"))
    data.create_custom_emoji = emoji_creator
    bot_setup_custom(data)

    message = create_mock_message(
        _id=0,
        author=data.some_user,
        content='hello :emoji1:',
        guild=data.guilds['target'],
        edit=AsyncMock(),
        delete=AsyncMock(),
    )

    await bot.on_message(message)

    message.edit.assert_not_awaited()
    message.delete.assert_not_awaited()
    assert len(bot.created_emojis_cache) == 0
    emoji_creator.assert_not_awaited()

@pytest.mark.asyncio
async def test_emoji_already_exists_in_current_guild(bot_setup_custom):
    data = dataset()

    current_guild_has_emoji = MockEmoji(id=1, name='some_emoji1934712', url='some_emoji1934712')
    data.guilds['target'].emojis = [current_guild_has_emoji] + data.guilds['target'].emojis
    emoji_creator = AsyncMock(side_effect=AssertionError("create_custom_emoji should not be called"))
    data.create_custom_emoji = emoji_creator

    bot_setup_custom(data)

    message = create_mock_message(
        _id=0,
        author=data.bot_user,
        content='hello :some_emoji1934712:',
        guild=data.guilds['target'],
        edit=AsyncMock(),
        delete=AsyncMock(),
    )

    await bot.on_message(message)

    message.edit.assert_not_awaited()
    message.delete.assert_not_awaited()
    assert len(bot.created_emojis_cache) == 0
    emoji_creator.assert_not_awaited()

@pytest.mark.asyncio
async def test_emoji_create_failure(bot_setup_custom):
    data = dataset()
    async def fail_create_emoji(a, b, c):
        return None
    data.create_custom_emoji = fail_create_emoji
    bot_setup_custom(data)

    message = create_mock_message(
        _id=-1,
        author=data.bot_user,
        content=f'hello :emoji1:',
        guild=data.guilds['target'],
        edit=AsyncMock(),
        delete=AsyncMock(),
    )
    await bot.on_message(message)
    message.edit.assert_not_awaited()
    message.delete.assert_not_awaited()
    assert len(bot.created_emojis_cache) == 0

@pytest.mark.asyncio
async def test_cache_hit(bot_setup_default):
    data = dataset()

    message1 = create_mock_message(
        _id=-1,
        author=data.bot_user,
        content=f'hello :emoji1:',
        guild=data.guilds['target'],
        edit=AsyncMock(),
        delete=AsyncMock(),
    )
    message2 = create_mock_message(
        _id=-1,
        author=data.bot_user,
        content=f'hello2 :emoji1:',
        guild=data.guilds['target'],
        edit=AsyncMock(),
        delete=AsyncMock(),
    )

    await bot.on_message(message1)
    await bot.on_message(message2)

    assert len(created_emojis) == 1

    message1.delete.assert_not_awaited()
    message1.edit.assert_awaited_once()
    assert message1.edit.call_args.kwargs['content'] == f'hello <:emoji1:{created_emojis[0].id}>'

    message2.delete.assert_not_awaited()
    message2.edit.assert_awaited_once()
    assert message2.edit.call_args.kwargs['content'] == f'hello2 <:emoji1:{created_emojis[0].id}>'

@pytest.mark.asyncio
async def test_cache_expiry(bot_setup_default, mock_time):
    data = dataset()
    message_factory = lambda: create_mock_message(
            _id=-1,
            author=data.bot_user,
            content=f'hello :emoji1:',
            guild=data.guilds['target'],
            edit=AsyncMock(),
            delete=AsyncMock(),
        )

    time = 1000
    mock_time(lambda: time)

    message = message_factory()
    await bot.on_message(message)
    message.edit.assert_awaited_once()
    assert len(bot.created_emojis_cache) == 1
    old_cache_emoji = list(bot.created_emojis_cache.values())[0][0]

    time = 1000 + bot.DELETE_EMOJI_TIMEOUT_SECONDS - 2

    message = message_factory()
    await bot.on_message(message)
    message.edit.assert_awaited_once()
    assert len(bot.created_emojis_cache) == 1
    old_cache_emoji_2 = list(bot.created_emojis_cache.values())[0][0]
    assert old_cache_emoji_2 == old_cache_emoji

    time = 1000 + bot.DELETE_EMOJI_TIMEOUT_SECONDS + 2

    message = message_factory()
    await bot.on_message(message)
    message.edit.assert_awaited_once()
    assert len(bot.created_emojis_cache) == 1
    new_cache_emoji = list(bot.created_emojis_cache.values())[0][0]
    assert new_cache_emoji != old_cache_emoji

@pytest.mark.asyncio
async def test_delete_command(bot_setup_default):
    data = dataset()
    message = create_mock_message(
        _id=-1,
        author=data.bot_user,
        content=r'\d :emoji1:',
        guild=data.guilds['target'],
        edit=AsyncMock(),
        delete=AsyncMock()
    )
    await bot.on_message(message)
    message.edit.assert_not_awaited()
    message.delete.assert_awaited_once()
    assert len(created_emojis) == 1
    assert created_emojis[0].name == 'emoji1'

@pytest.mark.asyncio
async def test_replace_and_react_command(bot_setup_default):
    data = dataset()
    previous_message = create_mock_message(
        _id=-1,
        author=data.bot_user,
        content=f'some message',
        guild=data.guilds['target'],
        add_reaction=AsyncMock()
    )
    message = create_mock_message(
        _id=-1,
        author=data.bot_user,
        content=r'\r :emoji1:',
        guild=data.guilds['target'],
        edit=AsyncMock(),
        delete=AsyncMock(),
        history=lambda limit: [message, previous_message],
    )
    await bot.on_message(message)
    message.edit.assert_not_awaited()
    message.delete.assert_awaited_once()
    previous_message.add_reaction.assert_awaited_once()