"""Cache RAM có giới hạn; không lưu ảnh hoặc khóa xuống ổ đĩa."""
from collections import OrderedDict
from secrets import token_urlsafe
from threading import Lock
import time

ENTRIES=OrderedDict()
LOCK=Lock()
TTL=600
MAX_BYTES=64*1024*1024


def save(raw, candidates):
    token=token_urlsafe(24)
    with LOCK:
        now=time.monotonic()
        for old in list(ENTRIES):
            if ENTRIES[old]['expires']<now:
                del ENTRIES[old]
        while ENTRIES and (len(ENTRIES)>=8 or sum(len(v['raw']) for v in ENTRIES.values())+len(raw)>MAX_BYTES):
            ENTRIES.popitem(last=False)
        ENTRIES[token]={'raw':raw,'candidates':candidates,'expires':now+TTL}
    return token


def load(token):
    with LOCK:
        entry=ENTRIES.get(token)
        if not entry or entry['expires']<time.monotonic():
            ENTRIES.pop(token,None)
            raise ValueError('Ảnh phân tích đã hết hạn. Hãy phân tích lại hoặc tải ảnh trong trang Trích xuất.')
        return entry
