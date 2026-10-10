"""Bounded, ephemeral utterance assembly for gRPC Auto intake only."""
import re
import time
from collections import deque

BUFFER_SECONDS = 4.0
ENDPOINT_SECONDS = 1.0
LEADING = {'what is', 'what are', 'explain', 'define', 'difference between', 'tell me about', 'can you explain', 'how does', 'write code for'}
TOPIC_WORDS = set('supervised unsupervised learning database indexing rest api pointers pointer in c normalization dbms machine vs deep and sql tcp udp http fastapi python javascript data structures binary search neural networks operating systems garbage collection dependency injection performance'.split())
TOPICS = re.compile(r'\b(?:supervised learning|unsupervised learning|database indexing|rest api|pointers? in c|normalization in dbms|machine learning|deep learning|sql|dbms|tcp|udp|http|fastapi|python|javascript|data structures|binary search|neural networks|operating systems|garbage collection|dependency injection)\b', re.I)
NOISE = re.compile(r'\b(?:yes|okay|ok|hello|hmm|click|button|window|sign in|log out|thank you|subscribe|i|we)\b', re.I)


def normalized(text):
    return re.sub(r'[^\w\s]', '', str(text)).strip().lower()


def topic_question(text):
    words = normalized(text).split()
    if len(words) >= 4 and len(words) % 2 == 0 and words[:len(words)//2] == words[len(words)//2:]:
        return None
    if 2 <= len(words) <= 8 and len(set(words)) > 1 and all(word in TOPIC_WORDS for word in words) and TOPICS.search(text) and not NOISE.search(text):
        return 'Explain ' + text.strip().rstrip('.?!') + '.'
    return None


def merge(left, right):
    a, b = left.split(), right.split()
    if normalized(left) == normalized(right): return left
    if normalized(right).startswith(normalized(left) + ' '): return right
    for overlap in range(min(len(a), len(b)), 0, -1):
        if [normalized(x) for x in a[-overlap:]] == [normalized(x) for x in b[:overlap]]:
            return ' '.join(a + b[overlap:])
    return (left + ' ' + right).strip()


class UtteranceBuffer:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.recent = deque(maxlen=8)
        self.pending = ''
        self.pending_at = 0
        self.partial = ''
        self.partial_at = 0
        self.partial_turn = None
        self.last_text = ''
        self.last_at = 0

    def partial_update(self, text, turn):
        self.partial, self.partial_at, self.partial_turn = text[:4096], self.clock(), turn
        self.recent.append((self.partial_at, self.partial))

    def assemble(self, text, turn):
        now = self.clock()
        while self.recent and now - self.recent[0][0] > BUFFER_SECONDS: self.recent.popleft()
        self.recent.append((now, text[:4096]))
        leading = self.pending if now - self.pending_at <= BUFFER_SECONDS else ''
        if not leading and now - self.partial_at <= BUFFER_SECONDS and normalized(self.partial) in LEADING:
            leading = self.partial
        if NOISE.search(text): leading = ''
        if leading and normalized(leading) not in LEADING and not all(word in TOPIC_WORDS for word in normalized(leading).split()) and topic_question(text):
            leading = ''  # A clear new topic must not be poisoned by unrelated chatter.
        result = merge(leading, text)[:4096] if leading else text[:4096]
        if leading and normalized(leading) in LEADING and normalized(result) != normalized(leading):
            result = result[0].upper() + result[1:].rstrip('.?!') + ('?' if normalized(leading) in {'what is', 'what are', 'difference between', 'how does'} else '.')
        self.partial = ''
        self.pending = ''
        self.last_text, self.last_at = result, now
        return result, bool(leading and normalized(result) != normalized(text))

    def hold(self, text):
        if not self.pending_at or self.clock() - self.pending_at > BUFFER_SECONDS: self.pending_at = self.clock()
        self.pending = text[:4096]

    def snapshot(self):
        now = self.clock()
        text = self.pending or self.partial or self.last_text
        at = self.pending_at if self.pending else self.partial_at if self.partial else self.last_at
        if now - at > BUFFER_SECONDS: text = ''
        return {'utterance_buffer_text': text[:256], 'utterance_buffer_age_ms': int(max(0, now-at)*1000) if text else 0}
