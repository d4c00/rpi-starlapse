# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAVE_DIR = os.path.join(BASE_DIR, "photo")

DEVICE_ID = "01"
SHM_ROOT = f"/dev/shm/time-lapse/{DEVICE_ID}"
SHM_QUEUE = os.path.join(SHM_ROOT, "queue")
SAVE_DIR = os.path.join(BASE_DIR, "photo")
SUB_DIRS = {
    "lights": "lights",
    "darks":  "darks",
    "biases": "biases"
}

# Network
DEVICE_TOKEN = "6XQzzwB0R8kwFQOp3Dg8YzK2sWisbtdQbFf8Qk4raDlFgaAKXpqTbs7EVhOodUOFQl0lQumiG4LzQoS7FW4rnzlKXp3IPwE2O7bpu7nvo3i3DKyjUrKrzOK3ahdRJQvb"
UPLOAD_SRV_BASE = "https://rpi-upload-srv.example.com"
SERVER_URL = f"{UPLOAD_SRV_BASE.rstrip('/')}/upload"
TIME_SOURCE = "https://any.example.com/"

# Capture
CAMERA_ENABLED = True
CAPTURE_INTERVAL = 30
AE_TARGET_LUMA = 0.33333
AE_MARGIN = 0.15
SENSOR_INDEX = 0

# Calibration Trigger
DARK_TRIGGER_FILE = f"/dev/shm/time-lapse/{DEVICE_ID}/calibration"
# Dark Frames
DARK_FRAME_COUNT = 100
# Bias Frames
CAPTURE_BIAS_FRAMES = False
BIAS_FRAME_COUNT = 100
BIAS_INTERVAL = 2.0

# Sync & Upload
BOOT_FIRST_LIVE_FAST_SYNC = True
SWITCH_BACK_LIVE_FAST_SYNC = False
SLOW_SYNC_COUNT_PER_CYCLE = 2
DISK_THRESHOLD = 0.05
LED_PATH = "/sys/class/leds/ACT/brightness"
MAX_UPLOAD_RETRY = 5
LOCAL_TRY_UPLOAD_RATE = 10
