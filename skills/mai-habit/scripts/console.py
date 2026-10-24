"""Keep Chinese reports readable on legacy Windows code pages.

Redirected output on a Chinese Windows console defaults to cp936, which has no
code point for '¥' (U+00A5). Printing a price then raises UnicodeEncodeError
halfway through a report, so `python habit.py demo > report.md` fails with a
traceback that has nothing to do with the actual bug the user is chasing.

Two defences, cheapest first:
1. If the stream cannot encode the characters this project prints, switch the
   stream to UTF-8 -- but only when it is not a terminal, so an interactive
   console keeps whatever encoding it negotiated.
2. If that switch is unavailable, fall back to '￥' (U+FFE5, the fullwidth
   form that GBK does contain). The meaning is identical; the bytes survive.
"""
import sys

YEN = '¥'
FULLWIDTH_YEN = '￥'
PROBE = YEN + '—＋'


def prepare(stream=None):
    """Return the currency symbol the output stream can actually encode."""
    stream = stream if stream is not None else sys.stdout
    encoding = getattr(stream, 'encoding', None) or 'utf-8'
    try:
        PROBE.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        if not getattr(stream, 'isatty', lambda: False)():
            try:
                stream.reconfigure(encoding='utf-8', errors='replace')
                encoding = getattr(stream, 'encoding', None) or 'utf-8'
            except (AttributeError, ValueError, OSError):
                pass
    try:
        YEN.encode(encoding)
        return YEN
    except (UnicodeEncodeError, LookupError):
        return FULLWIDTH_YEN
