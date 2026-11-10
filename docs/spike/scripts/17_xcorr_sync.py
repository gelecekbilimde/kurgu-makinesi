"""Independent sync check: camera scratch audio vs recorder WAV (GCC-PHAT cross-correlation).

Resolve's camera-clip transcript is made through the synced WAV, so it can't verify the sync.
This decodes the camera's own embedded audio with ffmpeg (from imageio-ffmpeg) and finds the lag
that best aligns it with the recorder track.
Output per pair: camera_frame = wav_frame + offset_f (positive = recorder started after camera
... in camera time the WAV content appears offset_f frames later), plus a confidence ratio
(main peak / best peak outside +-50 ms).
Usage: python 17_xcorr_sync.py MOV:WAV [MOV:WAV ...]
"""
import subprocess, sys
import numpy as np
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
SR, FPS = 8000, 25


def decode(path):
    cmd = [FFMPEG, "-v", "error", "-i", path, "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True, check=True).stdout, dtype=np.float32)


def gcc_phat(cam, rec):
    n = 1 << int(np.ceil(np.log2(len(cam) + len(rec))))
    C, R = np.fft.rfft(cam, n), np.fft.rfft(rec, n)
    X = C * np.conj(R)
    cc = np.fft.irfft(X / (np.abs(X) + 1e-12), n)
    cc = np.concatenate([cc[-len(rec) + 1:], cc[:len(cam)]])   # lags -(len(rec)-1) .. len(cam)-1
    lags = np.arange(-len(rec) + 1, len(cam))
    k = int(np.argmax(cc))
    excl = np.abs(lags - lags[k]) > SR * 0.05
    return lags[k], cc[k] / (cc[excl].max() + 1e-12)


for arg in sys.argv[1:]:
    mov, wav = arg.split(":", 1)
    cam, rec = decode(mov), decode(wav)
    lag, conf = gcc_phat(cam, rec)
    sec = lag / SR
    print(f"{mov.split('/')[-1]} vs {'/'.join(wav.split('/')[-2:])}: camera_t = wav_t + {sec:+.3f} s = {sec * FPS:+.2f} frames  confidence {conf:.1f}")
