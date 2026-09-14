import time
import cv2 
from tqdm import tqdm
import picamera2
from picamera2.encoders import JpegEncoder
from ffmpegoutput import FfmpegOutput
import simplejpeg
import re
import csv
import glob
import os
import pandas as pd
import fcntl
import gc

import subprocess

from camera_benchmark import CaptureBenchmark

def non_block_read(output):
    fd = output.fileno()
    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
    try:
        return output.read()
    except:
        return ""

for i in range(20):
    cmd = 'rpicam-vid -o /home/pi/imseq/09-09-2026_16-31.h264 --width 1920 --height 1080 --codec h264 --level 4.2 --denoise cdn_off --nopreview --buffer-count 12 --timeout 10000 --save-pts /home/pi/imseq/09-09-2026_16-31_frame_times.txt --awb auto --framerate 30'

    process = subprocess.Popen(
        cmd.split(' '),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        universal_newlines=True
    )

    # Check for stalled file and any errors
    start_time = time.time()
    capture_success = True 
    capture_complete = False
    old_size = 0
    while process.poll() is None:
        # Read ALL currently available lines
        while True:
            line = non_block_read(process.stdout)

            if line == '':
                break

            print(line)

            if 'Halting: reached timeout' in line:
                capture_complete = True
                break

            if 'ERROR' in line:
                capture_success = False
                break

        if not capture_success or capture_complete:
            break

        time.sleep(0.05)

    if not capture_complete:
        process.kill()
        time.sleep(5)
        continue
    else:
        print('Video captured successfully...', i)

    time.sleep(2)
