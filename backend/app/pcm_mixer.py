"""Bounded, arrival-anchored 16 kHz mono mixer; no shared client/server clock."""
import numpy as np


class PcmMixer:
    rate = 16000
    frame_samples = 1600
    capacity = 8000  # 500 ms per source; never retain arbitrary packet backlog.

    def __init__(self):
        self.position = 0
        self.sources = {name: dict(data=np.zeros(self.capacity, dtype=np.int16),
                                  end=0, seen=False, last=0., sequence=0,
                                  timestamp=0, origin=None) for name in ('microphone', 'system')}
        self.dropped = 0

    def push(self, source, pcm, now, sequence=0, timestamp=0):
        state = self.sources[source]
        if not pcm or len(pcm) % 2 or len(pcm) > 65536:
            raise ValueError('Invalid bounded PCM')
        if sequence and sequence <= state['sequence']:
            self.dropped += 1
            return False
        if timestamp and state['timestamp'] and timestamp < state['timestamp']:
            self.dropped += 1
            return False
        # Compare elapsed durations only. Combined clients timestamp sample-frame
        # start on a fixed per-run epoch; older clients may omit timing entirely.
        if timestamp and state['origin'] is not None and now - state['origin'][0] - (timestamp - state['origin'][1]) / 1000 > .3:
            self.dropped += 1
            return False
        if timestamp and state['origin'] is None:
            state['origin'] = (now, timestamp)
        state.update(sequence=sequence or state['sequence'], timestamp=timestamp or state['timestamp'], last=now, seen=True)
        samples = np.frombuffer(pcm, dtype='<i2')
        start = max(state['end'], self.position)
        # Slow sources resume at the current tick; fast sources lose oldest
        # buffered samples at 500 ms. No unbounded clock-drift accumulation.
        if start + len(samples) > self.position + self.capacity:
            self.dropped += 1
            state['data'].fill(0)
            start = self.position
            samples = samples[-self.capacity:]
        indexes = np.arange(start, start + len(samples)) % self.capacity
        state['data'][indexes] = samples
        state['end'] = start + len(samples)
        return True

    def render(self):
        indexes = np.arange(self.position, self.position + self.frame_samples) % self.capacity
        mixed = np.zeros(self.frame_samples, dtype=np.int32)
        for state in self.sources.values():
            mixed += state['data'][indexes].astype(np.int32)
            state['data'][indexes] = 0
        self.position += self.frame_samples
        # Equal fixed -6 dB gains preserve headroom even for coherent sources.
        return np.clip(mixed // 2, -32768, 32767).astype('<i2').tobytes()

    def clear(self):
        for state in self.sources.values():
            state['data'].fill(0)


class StreamingResampler:
    """Stateful sample-area conversion; carry the fractional input interval."""
    def __init__(self, source_rate, target_rate=16000):
        if source_rate <= 0 or target_rate <= 0:
            raise ValueError('Invalid rate')
        self.step = source_rate / target_rate
        self.phase = 0.
        self.tail = np.empty(0, dtype=np.float64)

    def process(self, samples):
        data = np.concatenate((self.tail, np.asarray(samples, dtype=np.float64)))
        count = max(0, int((len(data) - self.phase + 1e-9) / self.step))
        edges = self.phase + np.arange(count + 1) * self.step
        integral = np.concatenate(([0.], np.cumsum(data)))
        areas = np.interp(edges, np.arange(len(data) + 1), integral)
        result = np.diff(areas) / self.step
        end = self.phase + count * self.step
        consumed = int(end + 1e-9)
        self.phase = max(0., end - consumed)
        self.tail = data[consumed:]
        return result
