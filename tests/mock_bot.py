import logging
from dataclasses import dataclass
from typing import List

@dataclass
class MockEmoji:
    id: int
    name: str
    url: str

    def __init__(self, id: int, name: str, url: str):
        self.id = id
        self.name = name
        self.url = url

    def a(self):
        return self.id

    def __str__ (self):
        return f'<:{self.name}:{self.id}>'

@dataclass
class MockGuild:
    id: int
    name: str
    emojis: List[MockEmoji]

@dataclass
class MockUser:
    id: int
    name: str

class MockMessage:
    id: int
    author: MockUser
    content: str
    guild: MockGuild


    def __init__(self, _id: int, author: MockUser, content: str, guild: MockGuild):
        self.id = _id
        self.author = author
        self.content = content
        self.guild = guild

    async def edit(self, content: str):
        logging.getLogger(__name__).info('asd')
        return '123'