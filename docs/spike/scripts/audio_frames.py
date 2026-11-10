"""Per-video-frame audio features from a WAV (spike helper, needs numpy).

For every camera frame f (window = one frame, e.g. 40 ms at 25 fps) of the WAV shifted by
offset_f frames, compute:
  db     RMS level in dBFS
  voice  voicing strength: max normalised autocorrelation in the 70-400 Hz pitch-lag range,
         averaged over two half-frame windows. Voiced speech ~0.5-0.95; breath/cough/noise low.
Returns numpy arrays indexed by camera frame (0..n_frames-1).
"""
import wave
import numpy as np


def load_mono(path):
    w = wave.open(path)
    sr, sw, ch, n = w.getframerate(), w.getsampwidth(), w.getnchannels(), w.getnframes()
    raw = w.readframes(n)
    if sw == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        x = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
        x = np.where(x & 0x800000, x - 0x1000000, x).astype(np.float32) / 2 ** 23
    elif sw == 2:
        x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 2 ** 15
    else:
        raise ValueError("unsupported sample width %d" % sw)
    x = x.reshape(-1, ch)[:, 0]
    return x, sr


def _voicing(seg, sr):
    seg = seg - seg.mean()
    e = float(np.dot(seg, seg))
    if e <= 1e-10:
        return 0.0
    lo, hi = int(sr / 400), int(sr / 70)
    n = len(seg)
    spec = np.fft.rfft(seg, 2 * n)
    ac = np.fft.irfft(spec * np.conj(spec))[: n]
    ac = ac / ac[0]
    hi = min(hi, n - 1)
    return float(ac[lo:hi].max()) if hi > lo else 0.0


def frame_features(wav_path, fps, offset_f, n_frames):
    x, sr = load_mono(wav_path)
    spf = sr / fps
    db = np.full(n_frames, -120.0)
    voice = np.zeros(n_frames)
    for f in range(n_frames):
        a = int(round((f - offset_f) * spf))
        b = int(round((f - offset_f + 1) * spf))
        if a < 0 or b > len(x):
            continue
        seg = x[a:b]
        rms = float(np.sqrt(np.mean(seg * seg)))
        db[f] = 20 * np.log10(rms + 1e-12)
        h = len(seg) // 2
        voice[f] = 0.5 * (_voicing(seg[:h], sr) + _voicing(seg[h:], sr))
    return db, voice
