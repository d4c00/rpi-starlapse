# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os
import subprocess
import re

INIT_SNAP_STR = "0|666666|34.0|0.0|0.0"

SENSOR_NAME = "imx662"
WIDTH, HEIGHT = 1936, 1100

EXACT_RAW_SIZE = WIDTH * HEIGHT * 2 

V4L2_PIXELFORMAT = "RG12" 
MBUS_FORMAT = "SRGGB12_1X12"
EXP_OFFSET = 8 

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
    h_max = fetch("horizontal_blanking", "max")
    v_min = fetch("vertical_blanking", "min")
    v_max = fetch("vertical_blanking", "max")

    h_blank = h_max
    line_length = WIDTH + h_blank

    v_total = (target_us / 1000000.0) * pixel_rate / line_length
    v_blank = int(min(max(v_total - HEIGHT, v_min), v_max))

    safe_exp = int((HEIGHT + v_blank) - EXP_OFFSET)

    return [f"v4l2-ctl -d {container.s_node} --set-ctrl horizontal_blanking={h_blank} --set-ctrl vertical_blanking={v_blank} --set-ctrl exposure={safe_exp} --set-ctrl analogue_gain={int(gain)}"]

def get_capture_cmd(out_path, container):
    return f"v4l2-ctl -d {container.v_node} --stream-mmap --stream-count=1 --stream-to={out_path}"
