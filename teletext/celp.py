import numpy as np
import matplotlib.pyplot as plt

from teletext.coding import hamming8_decode

from tqdm import tqdm

from spectrum.linear_prediction import lsf2poly
from scipy.signal import lfilter, filtfilt

def celp_print(packets, rows, o):
    """Dump CELP packets from data channels 4 and 12. We don't know how to decode all of these."""

    dblevels = [0, 4, 8, 12, 18, 24, 30, 0]

    servicetypes = [
        'Single-channel mode using 1 VBI line per frame',
        'Single-channel mode using 2 VBI lines per frame',
        'Single-channel mode using 3 VBI lines per frame',
        'Single-channel mode using 4 VBI lines per frame',
        'Mute Channel 1',
        'Two-channel Mode using 2 VBI lines per frame',
        'Mute Channel 2',
        'Two-channel Mode using 4 VBI lines per frame',
    ]

    for p in packets:
        if p.mrag.magazine == 4 and p.mrag.row in rows:
            dcn = p.mrag.magazine + ((p.mrag.row & 1) << 3)
            control = hamming8_decode(p._array[2])
            service = hamming8_decode(p._array[3])

            frame0 = p._array[4:23]
            frame1 = p._array[23:42]
            if o is None:
                print(f'DCN: {dcn} ({p.mrag.magazine}/{p.mrag.row})', end=' ')
                if dcn == 4:
                    print('Programme-related audio.', end=' ')
                    print('Service:', 'AUDETEL' if service == 0 else hex(service), end=' ')
                    print('Control:', hex(control), dblevels[control & 0x7], 'dB',
                          '(muted)' if control & 0x8 else '')
                elif dcn == 12:
                    print('Programme-independant audio.', end=' ')
                    if service & 0x8:
                        print('User-defined service', hex(service & 0x7), hex(p._array[3]))
                    else:
                        print(servicetypes[service], f'Control: {hex(control)}' if control else '')
                print(frame0.tobytes().hex(), frame1.tobytes().hex())
            else:
                o.write(frame0.tobytes())
                o.write(frame1.tobytes())


def celp_plot(data):
    """Plot data from CELP packets. Experimental code."""
    data = np.unpackbits(np.fromfile(data, dtype=np.uint8).reshape(-1, 2, 19), bitorder='little').reshape(-1, 2, 152)
    frame0 = data[:, 0, :]
    frame1 = data[:, 1, :]
    d1 = np.sum(data, axis=0)

    p = np.arange(152)
    widths = np.array([
        0,
        3, 4, 4, 4, 4, 4, 4, 4, 3, 3, # 37 bytes - 10 x LPC params of (unknown?) variable size
        5, 5, 5, 5,             # 4x5 = 20 bytes - pitch gain (LTP gain)
        5, 5, 5, 5,             # 4x5 = 20 bytes - vector gain
        7, 7, 7, 7,             # 4x7 = 28 bytes - pitch index (LTP lag)
        8, 8, 8, 8,             # 4x8 = 32 bytes - vector index
        3, 3, 3, 3,             # 4x3 = 12 bytes - error correction for vector gains?
        3,                      # 3 bytes - always zero (except for recovery errors)
    ])
    g = np.cumsum(widths)
    print(sum(widths))

    fig, ax = plt.subplots(5, 2)
    for n in range(g.shape[0]-1):
        ax[0][0].bar(p[g[n]:g[n+1]], d1[0][g[n]:g[n+1]], 0.8)
        ax[0][1].bar(p[g[n]:g[n + 1]], d1[1][g[n]:g[n + 1]], 0.8)

    a = np.packbits(frame0[:,37:37+20].reshape(-1, 5), axis=-1, bitorder='little').flatten()
    b = np.packbits(frame0[:,37+20:37+20+20].reshape(-1, 5), axis=-1, bitorder='little').flatten()
    c = np.packbits(frame0[:,37+20+20:37+20+20+28].reshape(-1, 7), axis=-1, bitorder='little').flatten()
    d = np.packbits(frame0[:,37+20+20+28:37+20+20+28+32].reshape(-1, 8), axis=-1, bitorder='little').flatten()

    ax[1][0].plot(a[:10000], linewidth=0.5)
    ax[2][0].plot(b[:10000], linewidth=0.5)
    ax[3][0].plot(c[:10000], linewidth=0.5)
    ax[4][0].plot(d[:10000], linewidth=0.5)

    a = np.packbits(frame1[:,37:37+20].reshape(-1, 5), axis=-1, bitorder='little').flatten()
    b = np.packbits(frame1[:,37+20:37+20+20].reshape(-1, 5), axis=-1, bitorder='little').flatten()
    c = np.packbits(frame1[:,37+20+20:37+20+20+28].reshape(-1, 7), axis=-1, bitorder='little').flatten()
    d = np.packbits(frame1[:,37+20+20+28:37+20+20+28+32].reshape(-1, 8), axis=-1, bitorder='little').flatten()

    ax[1][1].plot(a[:10000], linewidth=0.5)
    ax[2][1].plot(b[:10000], linewidth=0.5)
    ax[3][1].plot(c[:10000], linewidth=0.5)
    ax[4][1].plot(d[:10000], linewidth=0.5)

    fig.tight_layout()

    plt.show()


def celp_generate_audio(data, frame=None, sample_rate=8000):
    data = np.unpackbits(np.fromfile(data, dtype=np.uint8).reshape(-1, 2, 19),
                         bitorder='little').reshape(-1, 2, 152)
    if frame == 0:
        data = data[:, 0, :]
    elif frame == 1:
        data = data[:, 1, :]
    else:
        data = data.reshape(-1, 152)

    widths = np.array([
        0,
        3, 4, 4, 4, 4, 4, 4, 4, 3, 3, # 37 bytes - 10 x LPC params of (unknown?) variable size
        5, 5, 5, 5,             # 4x5 = 20 bytes - pitch gain (LTP gain)
        5, 5, 5, 5,             # 4x5 = 20 bytes - vector gain
        7, 7, 7, 7,             # 4x7 = 28 bytes - pitch index (LTP lag)
        8, 8, 8, 8,             # 4x8 = 32 bytes - vector index
        3, 3, 3, 3,             # 4x3 = 12 bytes - error correction for vector gains?
        3,                      # 3 bytes - always zero (except for recovery errors)
    ])
    g = np.cumsum(widths)

    sq = (((np.sin(np.linspace(0, 500*2*3.14159, 8000)) > 0) * 2) - 1)
    #sn1 = np.sin(np.linspace(0, 1000*2*3.14159, 8000))
    sn2 = np.sin(np.linspace(0, 3800*2*3.14159, 8000))
    wn = np.random.uniform(-1, 1, size=(8000, ))
    wave = wn * 1

    pos = 0

    for n in tqdm(range(0,data.shape[0])): # frames
        raw_frame = data[n]
        decoded_frame = np.empty((30, ), dtype=np.int32)
        for n in range(len(g)-2):
            slice = raw_frame[g[n]:g[n+1]]
            width = widths[n+1]
            decoded_frame[n] = np.packbits(slice, bitorder='little')
        lsf = decoded_frame[:10]
        pitch_gain = decoded_frame[10:14]
        vector_gain = (decoded_frame[14:18] - 16) / 16.0
        pitch_idx = decoded_frame[18:22]
        vector_idx = decoded_frame[22:26]
        frame = np.empty((160,), dtype=np.float)
        framex = np.empty((160,), dtype=np.float)
        for subframe in range(4):
            gain = vector_gain[subframe]
            #gain = np.mean(np.abs(vector_gain))
            for n in range(40):
                posn = pos + (subframe*40) + n
                sfn = wave[posn % wave.shape[0]] * gain
                frame[(subframe*40) + n] = wave[posn % wave.shape[0]] * gain
                framex[(subframe*40) + n] = wave[posn % wave.shape[0]] * gain * abs(gain)
            pos += 40

        #yield (frame * 32768).astype(np.int16)
        #continue

        # hmm
        #lsf += 1
        lsf <<= np.array([0, 0, 0, 0, 0, 0, 0, 0, 1, 1])
        #lsf = lsf + 0.1
        lsf = lsf + np.linspace(2.5, 60, 10)
        lsf = np.array(sorted(lsf))
        # lsf += 2
        #if np.any(np.diff(lsf) < 0):
        #    print(lsf)
        #    continue
        # lsf += np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]) * 4

        #print(lsf.min(), lsf.max())
        a = lsf2poly(3.1 * lsf/(74))
        #print(a)
        #a = lsf2poly(np.linspace(0.12, 3.0, 10))
        b = np.hstack([[0], -1 * a[1:]])

        filt = filtfilt(b, [1], frame)

        result = ((framex * 3000) + (filt * 1500))

        if np.max(result) > 32767:
            print("NOO", np.max(result))
        yield result.astype(np.int16)


def celp_to_raw(data, output):
    if output is None:
        import subprocess
        ps = subprocess.Popen(['play', '-t', 'raw', '-r', '8k', '-e', 'signed', '-b', '16', '-c', '1', '-', 'sinc', '200-3800'], stdin=subprocess.PIPE)
        output = ps.stdin
    for subframe in celp_generate_audio(data):
        output.write(subframe.tobytes())
