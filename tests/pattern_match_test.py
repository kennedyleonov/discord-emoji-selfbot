import logging

import pytest

from emojibot.bot import match_emoji_patterns, EmojiPattern

logger = logging.getLogger(__name__)

@pytest.mark.parametrize(
    'text,expected',
    [
        ('', []),
        ('::', []),
        (':a:', []),
        (':1:', []),
        ('1', []),
        ('12 1', [EmojiPattern('12', 'id', '12', 0, 1)]),
        (':thirty_two_letter_word_qwertyuio:', [EmojiPattern(':thirty_two_letter_word_qwertyuio:', 'name', 'thirty_two_letter_word_qwertyuio', 0, 33)]),
        (':thirty_three_letter_word_qwertyui:', []),
        (':as:', [EmojiPattern(':as:', 'name', 'as', 0, 3)]),
        (':as :', [EmojiPattern(':as :', 'name', 'as ', 0, 4)]),
        (':as:df:', [EmojiPattern(':as:', 'name', 'as', 0, 3)]),
        (':as::df:', [
            EmojiPattern(':as:', 'name', 'as', 0, 3),
            EmojiPattern(':df:', 'name', 'df', 4, 7)
        ]),
        ('12 :as:', [
            EmojiPattern(':as:', 'name', 'as', 3, 6),
            EmojiPattern('12', 'id', '12', 0, 1)
        ]),
    ]
)
def test_match_emoji_pattern(text, expected):
    assert list(match_emoji_patterns(text)) == expected

def atest_match_emoji_pattern_big_string():
    input_string = ':1 ::  1234:12345:123 :1:12:'
    expected = [
        EmojiPattern(':1 :', 'name', '1 ', 0, 3),
        EmojiPattern(':  1234:', 'name', '  1234', 4, 11),
        EmojiPattern(':123 :', 'name', '123 ', 17, 22),
        EmojiPattern(':12:', 'name', '12', 24, 27),
        EmojiPattern('1', 'id', '1', 1, 1),
        EmojiPattern('1234', 'id', '1234', 7, 10),
        EmojiPattern('12345', 'id', '12345', 12, 16),
        EmojiPattern('123', 'id', '123', 18, 20),
        EmojiPattern('1', 'id', '1', 23, 23),
        EmojiPattern('12', 'id', '12', 25, 26)
    ]
    lists_exact_match(list(match_emoji_patterns(input_string)), expected)

def lists_exact_match(result, test_list):
    assert len(result) == len(test_list)
    i = 0
    while i < len(test_list):
        assert result[i] == test_list[i]
        i += 1