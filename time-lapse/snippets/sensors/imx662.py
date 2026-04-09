# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os
import subprocess
import re

INIT_SNAP_STR = "0|666666|34.0|0.0|0.0"

SENSOR_NAME = "imx662"
WIDTH, HEIGHT = 1936, 1100
V4L2_PIXELFORMAT = "RG12"
RAW_BPP = 2
EXP_OFFSET = 8

def find_nodes():
    v_node = "/dev/video0"
    s_node = None
    base_path = "/sys/class/video4linux"
    for dev in os.listdir(base_path):
        name_path = os.path.join(base_path, dev, "name")
        if os.path.exists(name_path):
            with open(name_path, 'r') as f:
                if SENSOR_NAME in f.read():
                    s_node = f"/dev/{dev}"
                    break
    if not s_node: raise RuntimeError(f"{SENSOR_NAME} subdev missing")
    return v_node, s_node

def get_runtime_cmds(target_us, gain, container):
    out = subprocess.check_output(f"v4l2-ctl -d {container.s_node} --list-ctrls", shell=True, text=True)

    def fetch(name):
        m = re.search(rf"{name}\s+.*?\bvalue=(\d+)", out)
        if not m:
            m = re.search(rf"{name}\s+.*?(\d+)", out) 
        return int(m.group(1))

    pixel_rate = fetch("pixel_rate")
    h_blank = fetch("horizontal_blanking")

    v_min = int(re.search(r"vertical_blanking.*?min=(\d+)", out).group(1))
    v_max = int(re.search(r"vertical_blanking.*?max=(\d+)", out).group(1))
    e_max_hard = int(re.search(r"exposure.*?max=(\d+)", out).group(1))

    v_total = ((target_us / 1000000.0) * pixel_rate) / (WIDTH + h_blank)
    v_blank = int(min(max(v_total - HEIGHT, v_min), v_max))

    return [
        f"v4l2-ctl -d {container.s_node} --set-ctrl vertical_blanking={v_blank}",
        f"v4l2-ctl -d {container.s_node} --set-ctrl exposure={int(min((HEIGHT + v_blank) - EXP_OFFSET, e_max_hard))}",
        f"v4l2-ctl -d {container.s_node} --set-ctrl analogue_gain={int(gain)}"
    ]

def get_capture_cmd(out_path, container):
    return (f"v4l2-ctl -d {container.v_node} --set-fmt-video=width={WIDTH},height={HEIGHT},"
            f"pixelformat={V4L2_PIXELFORMAT} --stream-mmap --stream-count=1 --stream-to={out_path}")