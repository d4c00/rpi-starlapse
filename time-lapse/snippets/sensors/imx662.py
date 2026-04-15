# Copyright (c) 2026 length <me@length.cc>
# Licensed under the MIT License.

import os
import subprocess
import re
import numpy as np

INIT_SNAP_STR = "0|1000000|34|0|0"

SENSOR_NAME = "imx662"
WIDTH, HEIGHT = 1936, 1096

BIT = 12
EXACT_RAW_SIZE = WIDTH * HEIGHT * 2

V4L2_PIXELFORMAT = "RG12"
MBUS_FORMAT = "SRGGB12_1X12"
EXP_OFFSET = 0

def find_nodes():
    v_node, s_node = None, None
    base = "/sys/class/video4linux"

    for dev in sorted(os.listdir(base)):
        p = os.path.join(base, dev, "name")
        if os.path.exists(p):
            with open(p) as f:
                if SENSOR_NAME in f.read():
                    s_node = f"/dev/{dev}"
                    break

    for dev in sorted(os.listdir(base)):
        if dev.startswith("video"):
            p = os.path.join(base, dev, "device/uevent")
            if os.path.exists(p):
                with open(p) as f:
                    if "unicam" in f.read().lower():
                        v_node = f"/dev/{dev}"
                        break

    return v_node, s_node

_v_n, _s_n = find_nodes()

def get_init_cmds():
    if not _s_n or not _v_n:
        return []

    subdev = os.path.basename(_s_n)

    with open(f"/sys/class/video4linux/{subdev}/name") as f:
        entity = f.read().strip()

    m_node = "/dev/media0"
    for i in range(5):
        if os.path.exists(f"/dev/media{i}"):
            try:
                out = subprocess.check_output(
                    f"media-ctl -d /dev/media{i} -p",
                    shell=True,
                    text=True
                )
                if SENSOR_NAME in out:
                    m_node = f"/dev/media{i}"
                    break
            except:
                pass

    return [
        f"media-ctl -d {m_node} -V '\"{entity}\":0 [fmt:{MBUS_FORMAT}/{WIDTH}x{HEIGHT} field:none]'",
        f"media-ctl -d {m_node} -V '\"{entity}\":0 [crop:(0,0)/{WIDTH}x{HEIGHT}]'",
        f"v4l2-ctl -d {_v_n} --set-fmt-video=width={WIDTH},height={HEIGHT},pixelformat={V4L2_PIXELFORMAT}",
        f"v4l2-ctl -d {_s_n} --set-ctrl hcg_enable=1"
    ]

_ctrl_cache = None


def _fetch(out, name, field="value"):
    m = re.search(rf"{name}.*?{field}=(\d+)", out)
    return int(m.group(1)) if m else 0


def _load_ctrl_cache(dev):
    global _ctrl_cache

    if _ctrl_cache is not None:
        return _ctrl_cache

    out = subprocess.check_output(
        f"v4l2-ctl -d {dev} --list-ctrls",
        shell=True,
        text=True
    )

    _ctrl_cache = {
        "pixel_rate": _fetch(out, "pixel_rate"),
        "h_min": _fetch(out, "horizontal_blanking", "min"),
        "h_max": _fetch(out, "horizontal_blanking", "max"),
        "v_min": _fetch(out, "vertical_blanking", "min"),
        "v_max": _fetch(out, "vertical_blanking", "max"),
        "exp_min": _fetch(out, "exposure", "min"),
        "exp_max": _fetch(out, "exposure", "max"),
        "gain_min": _fetch(out, "analogue_gain", "min"),
        "gain_max": _fetch(out, "analogue_gain", "max"),
    }

    return _ctrl_cache

def print_hardware_info(container):
    try:
        ctrl = _load_ctrl_cache(container.s_node)

        h_blank = ctrl["h_min"]
        pixel_rate = ctrl["pixel_rate"]

        min_exp_s = (ctrl["exp_min"] * (WIDTH + h_blank)) / pixel_rate
        max_exp_s = ((HEIGHT + ctrl["v_max"]) * (WIDTH + h_blank)) / pixel_rate

        print(f"[*] Exposure Min: {min_exp_s:.6f}s")
        print(f"[*] Exposure Max: {max_exp_s:.6f}s")
        print(f"[*] Gain Min: {ctrl['gain_min']}")
        print(f"[*] Gain Max: {ctrl['gain_max']}")

    except Exception as e:
        print(f"[!] Failed to read hardware info: {e}")

def get_runtime_cmds(target_us, gain, container):
    ctrl = _load_ctrl_cache(container.s_node)

    pixel_rate = ctrl["pixel_rate"]
    h_min = ctrl["h_min"]
    h_max = ctrl["h_max"]
    v_min = ctrl["v_min"]
    v_max = ctrl["v_max"]

    total_clocks = (target_us * pixel_rate) / 1_000_000.0

    line_min = WIDTH + h_min
    v_total_at_hmin = total_clocks / line_min

    if v_total_at_hmin <= (HEIGHT + v_max):
        h_blank = h_min
        v_blank = int(np.clip(v_total_at_hmin - HEIGHT + EXP_OFFSET, v_min, v_max))
    else:
        v_blank = v_max
        v_total = HEIGHT + v_blank
        line_needed = total_clocks / v_total
        h_blank = int(np.clip(line_needed - WIDTH, h_min, h_max))

    line_len = WIDTH + h_blank
    v_total = HEIGHT + v_blank

    exposure = int(np.clip(
        total_clocks / line_len,
        ctrl["exp_min"],
        ctrl["exp_max"]
    ))

    gain = int(np.clip(
        gain,
        ctrl["gain_min"],
        ctrl["gain_max"]
    ))

    return [
        f"v4l2-ctl -d {container.s_node} "
        f"-c horizontal_blanking={h_blank},"
        f"vertical_blanking={v_blank},"
        f"exposure={exposure},"
        f"analogue_gain={gain}"
    ]

def get_capture_cmd(out_path, container):
    return (
        f"v4l2-ctl -d {container.v_node} "
        f"--stream-mmap --stream-count=1 --stream-to={out_path}"
    )
