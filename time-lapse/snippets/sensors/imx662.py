# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os
import subprocess
import re
import numpy as np

INIT_SNAP_STR = "0|1000000|34.0|0.0|0.0"

SENSOR_NAME = "imx662"
WIDTH, HEIGHT = 1936, 1096

BIT = 12
EXACT_RAW_SIZE = WIDTH * HEIGHT * 2 

V4L2_PIXELFORMAT = "RG12" 
MBUS_FORMAT = "SRGGB12_1X12"
EXP_OFFSET = 0 

class DevContainer:
    def __init__(self, v_node, s_node):
        self.v_node = v_node
        self.s_node = s_node

def find_nodes():
    v_node, s_node = None, None
    base_v4l = "/sys/class/video4linux"

    for dev in sorted(os.listdir(base_v4l)):
        path = os.path.join(base_v4l, dev, "name")
        if os.path.exists(path):
            with open(path, 'r') as f:
                if SENSOR_NAME in f.read():
                    s_node = f"/dev/{dev}"
                    break

    for dev in sorted(os.listdir(base_v4l)):
        if dev.startswith("video"):
            u_path = os.path.join(base_v4l, dev, "device/uevent")
            if os.path.exists(u_path):
                with open(u_path, 'r') as f:
                    if "unicam" in f.read().lower():
                        v_node = f"/dev/{dev}"
                        break
    return v_node, s_node

_v_n, _s_n = find_nodes()
_out = subprocess.check_output(f"v4l2-ctl -d {_s_n} --list-ctrls", shell=True, text=True)
_f = lambda n, f: int(re.search(rf"{n}.*?{f}=(\d+)", _out).group(1))

def _calculate_phys_exposure(exp_lines, mode="min"):
    _out_now = subprocess.check_output(f"v4l2-ctl -d {_s_n} --list-ctrls", shell=True, text=True)
    _fetch = lambda n, f: int(re.search(rf"{n}.*?{f}=(\d+)", _out_now).group(1))
    
    h_blank = _fetch("horizontal_blanking", mode)
    pixel_rate = _fetch("pixel_rate", "value")
    
    return (exp_lines * (WIDTH + h_blank)) / pixel_rate

MIN_EXPOSURE = _calculate_phys_exposure(_f("exposure", "min"), mode="min")

v_total_max = HEIGHT + _f("vertical_blanking", "max")

MAX_EXPOSURE = _calculate_phys_exposure(v_total_max, mode="max")

AE_MIN_US = int(MIN_EXPOSURE * 1e6)

def print_hardware_info():
    print(f"[*] Hardware Max Exposure: {MAX_EXPOSURE:.6f}s")
    print(f"[*] Hardware Min Exposure: {MIN_EXPOSURE:.6f}s")
    print(f"[*] AE Logic Min Limit: {AE_MIN_US}us")

print_hardware_info()

def get_init_cmds():
    v_node, s_node = find_nodes()
    if not s_node: return []

    subdev_name = os.path.basename(s_node)
    with open(f"/sys/class/video4linux/{subdev_name}/name", 'r') as f:
        full_entity_name = f.read().strip()

    m_node = "/dev/media0"
    for i in range(5):
        if os.path.exists(f"/dev/media{i}"):
            try:
                out = subprocess.check_output(f"media-ctl -d /dev/media{i} -p", shell=True, text=True)
                if SENSOR_NAME in out:
                    m_node = f"/dev/media{i}"
                    break
            except: pass

    return [
        f"media-ctl -d {m_node} -V '\"{full_entity_name}\":0 [fmt:{MBUS_FORMAT}/{WIDTH}x{HEIGHT} field:none]'",
        f"media-ctl -d {m_node} -V '\"{full_entity_name}\":0 [crop:(0,0)/{WIDTH}x{HEIGHT}]'",
        f"v4l2-ctl -d {v_node} --set-fmt-video=width={WIDTH},height={HEIGHT},pixelformat={V4L2_PIXELFORMAT}"]

def get_runtime_cmds(target_us, gain, container):
    out = subprocess.check_output(f"v4l2-ctl -d {container.s_node} --list-ctrls", shell=True, text=True)
    
    def fetch(name, field="value"):
        m = re.search(rf"{name}.*?{field}=(\d+)", out)
        return int(m.group(1)) if m else 0

    pixel_rate = fetch("pixel_rate")
    h_min = fetch("horizontal_blanking", "min")
    h_max = fetch("horizontal_blanking", "max")
    v_min = fetch("vertical_blanking", "min")
    v_max = fetch("vertical_blanking", "max")

    total_clocks_needed = (target_us * pixel_rate) / 1000000.0

    line_min = WIDTH + h_min
    v_total_at_hmin = total_clocks_needed / line_min
    
    if v_total_at_hmin <= (HEIGHT + v_max):
        h_blank = h_min
        v_blank = int(np.clip(v_total_at_hmin - HEIGHT + EXP_OFFSET, v_min, v_max))
    else:
        v_blank = v_max
        v_total_fixed = HEIGHT + v_blank
        line_needed = total_clocks_needed / v_total_fixed
        h_blank = int(np.clip(line_needed - WIDTH, h_min, h_max))

    current_line_length = WIDTH + h_blank
    current_v_total = HEIGHT + v_blank
    safe_exp = int(np.clip(total_clocks_needed / current_line_length, 1, current_v_total - EXP_OFFSET))

    return [f"v4l2-ctl -d {container.s_node} -c horizontal_blanking={h_blank},vertical_blanking={v_blank},exposure={safe_exp},analogue_gain={int(gain)}"]

def get_capture_cmd(out_path, container):
    return f"v4l2-ctl -d {container.v_node} --stream-mmap --stream-count=1 --stream-to={out_path}"
