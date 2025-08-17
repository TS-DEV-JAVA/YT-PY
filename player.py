import sys
import ffmpeg
import pyaudio
import threading
import time
import keyboard
from queue import Queue
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from comtypes import CLSCTX_ALL

# ---------------------------
# CONFIG
# ---------------------------
CHUNK_SIZE = 4096
CHANNELS = 2
RATE = 44100
SEEK_STEP = 5  # seconds

# ---------------------------
# GLOBALS
# ---------------------------
stop_flag = False
paused = False
seek_offset = 0
seek_request = None  # store new seek time
audio_queue = Queue(maxsize=20)

# ---------------------------
# VOLUME CONTROL
# ---------------------------
devices = AudioUtilities.GetSpeakers()
interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
volume = interface.QueryInterface(IAudioEndpointVolume)

def change_volume(up=True):
    current_vol = volume.GetMasterVolumeLevelScalar()
    step = 0.05
    new_vol = min(1.0, current_vol + step) if up else max(0.0, current_vol - step)
    volume.SetMasterVolumeLevelScalar(new_vol, None)
    print(f"Volume: {int(new_vol * 100)}%")

# ---------------------------
# AUDIO THREAD
# ---------------------------
def audio_producer(url):
    global stop_flag, audio_queue, seek_request
    current_offset = 0

    while not stop_flag:
        # Restart FFmpeg if seeking
        start_offset = seek_request if seek_request is not None else current_offset
        seek_request = None

        process = (
            ffmpeg
            .input(url, ss=start_offset)
            .output('pipe:', format='s16le', acodec='pcm_s16le', ac=CHANNELS, ar=str(RATE))
            .run_async(pipe_stdout=True, pipe_stderr=True)
        )

        while not stop_flag:
            if seek_request is not None:
                break  # break loop to restart ffmpeg for new seek
            data = process.stdout.read(CHUNK_SIZE)
            if not data:
                stop_flag = True
                break
            audio_queue.put(data)
            current_offset += CHUNK_SIZE / (2 * CHANNELS * RATE)  # rough seconds

        process.terminate()

# ---------------------------
# AUDIO CONSUMER
# ---------------------------
def audio_consumer():
    global stop_flag, paused
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16,
                    channels=CHANNELS,
                    rate=RATE,
                    output=True)

    while not stop_flag:
        if paused:
            time.sleep(0.1)
            continue
        try:
            data = audio_queue.get(timeout=0.1)
            stream.write(data)
        except:
            continue

    stream.stop_stream()
    stream.close()
    p.terminate()

# ---------------------------
# KEYBOARD LISTENER
# ---------------------------
def keyboard_listener():
    global stop_flag, paused, seek_offset, seek_request
    while not stop_flag:
        if keyboard.is_pressed('q'):
            stop_flag = True
        elif keyboard.is_pressed('p'):
            paused = not paused
            print("Paused" if paused else "Resumed")
            time.sleep(0.3)
        elif keyboard.is_pressed('right'):
            seek_offset += SEEK_STEP
            seek_request = seek_offset
            print(f"Seek forward: +{SEEK_STEP}s")
            time.sleep(0.3)
        elif keyboard.is_pressed('left'):
            seek_offset = max(0, seek_offset - SEEK_STEP)
            seek_request = seek_offset
            print(f"Seek backward: -{SEEK_STEP}s")
            time.sleep(0.3)
        elif keyboard.is_pressed('up'):
            change_volume(True)
            time.sleep(0.2)
        elif keyboard.is_pressed('down'):
            change_volume(False)
            time.sleep(0.2)

# ---------------------------
# MAIN
# ---------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python player.py <URL>")
        sys.exit(1)

    url = sys.argv[1]

    # Print controls at the start
    print("Playing... [p]ause/resume, [q]uit, [←/→] seek, [↑/↓] volume")

    threading.Thread(target=keyboard_listener, daemon=True).start()
    threading.Thread(target=audio_producer, args=(url,), daemon=True).start()
    audio_consumer()
