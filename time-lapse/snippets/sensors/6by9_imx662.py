# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import subprocess
import re
import glob
import os

SENSOR_NAME = "imx662"
MEDIA_ENTITY_NAME = "imx662 10-001a"
WIDTH, HEIGHT = 1936, 1100
V4L2_PIXELFORMAT = "RG12"
RAW_BPP = 2
EXACT_RAW_SIZE = 4259200
EXP_OFFSET = 8

def get_v4l2_limit(ctrl_name):
    try:
        res = subprocess.check_output(f"v4l2-ctl -d {ACTUAL_SUBDEV} --list-ctrls", shell=True, text=True)
        # 匹配格式: name 0x... (type) : min=X max=Y ...
        match = re.search(rf"{ctrl_name}.*min=(\d+)\s+max=(\d+)", res)
        if match:
            return int(match.group(1)), int(match.group(2))
    except:
        pass
    return 0, 0

def get_pixel_rate():
    try:
        res = subprocess.check_output(f"v4l2-ctl -d {ACTUAL_SUBDEV} --list-ctrls", shell=True, text=True)
        match = re.search(r"pixel_rate.*value=(\d+)", res)
        return int(match.group(1)) if match else 222750000
    except:
        return 222750000

def _find_node(name, is_subdev=True):
    nodes = glob.glob("/sys/class/video4linux/v4l-subdev*/name" if is_subdev else "/sys/class/video4linux/video*/name")
    for n in nodes:
        try:
            with open(n, 'r') as f:
                if name in f.read():
                    return f"/dev/{os.path.basename(os.path.dirname(n))}"
        except: continue
    return "/dev/v4l-subdev0" if is_subdev else "/dev/video0"

ACTUAL_SUBDEV = _find_node(MEDIA_ENTITY_NAME, True)
ACTUAL_VIDEO = "/dev/video0"

PIXEL_RATE = get_pixel_rate()
H_MIN, H_MAX = get_v4l2_limit("horizontal_blanking")
V_MIN, V_MAX = get_v4l2_limit("vertical_blanking")
E_MIN, E_MAX_HARD = get_v4l2_limit("exposure")

MAX_FRAME_US = ((WIDTH + H_MAX) * (HEIGHT + V_MAX) / float(PIXEL_RATE)) * 1000000.0

MIN_EXPOSURE = 100.0
MAX_EXPOSURE = MAX_FRAME_US
MIN_GAIN = 1.0
MAX_GAIN = 31.0
VIRT_GAIN_MIN = 1.0
VIRT_GAIN_MAX = 31.0

EXTENSIONS = {"horizontal_flip": 0, "vertical_flip": 0}

def get_runtime_cmds(target_us, gain_request):
    total_clocks = (target_us / 1000000.0) * PIXEL_RATE

    h_blank = H_MIN
    v_total = total_clocks / (WIDTH + h_blank)

    if v_total > (HEIGHT + V_MAX):
        v_blank = V_MAX
        v_total_fixed = HEIGHT + v_blank
        h_total = total_clocks / v_total_fixed
        h_blank = int(min(max(h_total - WIDTH, H_MIN), H_MAX))
    else:
        v_blank = int(min(max(v_total - HEIGHT, V_MIN), V_MAX))

    actual_v_total = HEIGHT + v_blank
    
    exp_lines = int(min(actual_v_total - EXP_OFFSET, E_MAX_HARD))

    gain_val = int(min(max(gain_request * 34, 34), 1000))

    return [
        f"v4l2-ctl -d {ACTUAL_SUBDEV} --set-ctrl horizontal_blanking={h_blank}",
        f"v4l2-ctl -d {ACTUAL_SUBDEV} --set-ctrl vertical_blanking={v_blank}",
        f"v4l2-ctl -d {ACTUAL_SUBDEV} --set-ctrl exposure={exp_lines}",
        f"v4l2-ctl -d {ACTUAL_SUBDEV} --set-ctrl analogue_gain={gain_val}"
    ]

def get_capture_cmd(out_path):
    return (
        f"v4l2-ctl -d {ACTUAL_VIDEO} "
        f"--set-fmt-video=width={WIDTH},height={HEIGHT},pixelformat={V4L2_PIXELFORMAT} "
        f"--stream-mmap --stream-count=1 --stream-to={out_path}"
    )