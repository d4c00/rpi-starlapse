# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import subprocess, re, numpy as np

SENSOR_NAME = "imx662"
MEDIA_ENTITY_NAME = "imx662 10-001a"
WIDTH, HEIGHT = 1920, 1080
MEDIA_CTL_FMT = "SRGGB12_1X12"
V4L2_PIXELFORMAT = "RG12"
RAW_BPP = 2

DRV_KEYS = {
    "exp": "exposure",
    "gain": "analogue_gain",
    "vblk": "vertical_blanking",
    "hblk": "horizontal_blanking",
    "prate": "pixel_rate"
}

MIN_EXPOSURE = 1e-6
MAX_EXPOSURE = 1.0
MIN_GAIN = 0
MAX_GAIN = 100
VIRT_GAIN_MIN = 1.0
VIRT_GAIN_MAX = 31.0

def parse_hw_inventory(container):
    inventory = {}
    try:
        out = subprocess.check_output(f"v4l2-ctl -d {container.s_node} --list-ctrls", shell=True, text=True)
        pattern = re.compile(r"([a-z0-9_]+)\s+0x[0-9a-f]+\s+\([a-z0-9]+\)\s+:\s+min=(-?\d+)\s+max=(-?\d+).*?value=(-?\d+)")
        for line in out.splitlines():
            m = pattern.search(line)
            if m:
                inventory[m.group(1)] = {
                    'min': int(m.group(2)),
                    'max': int(m.group(3)),
                    'val': int(m.group(4))
                }
    except Exception:
        pass
    return inventory

def get_init_cmds(container):
    return [
        f"media-ctl -d {container.m_node} -V \"'{container.MEDIA_ENTITY_NAME}':0 [fmt:{container.MEDIA_CTL_FMT}/{WIDTH}x{HEIGHT}]\"",
        f"v4l2-ctl -d {container.v_node} --set-fmt-video=width={WIDTH},height={HEIGHT},pixelformat={V4L2_PIXELFORMAT}",
        f"v4l2-ctl -d {container.s_node} --set-ctrl=horizontal_flip=0,vertical_flip=0"
    ]

def get_runtime_cmds(target_us, gain, container):
    inv = container.hw_inventory
    pr = inv.get(DRV_KEYS['prate'], {'val': 222750000})['val']
    hb = inv.get(DRV_KEYS['hblk'], {'val': 1034})['val']
    hmax = WIDTH + hb
    
    req_vmax = int((target_us / 1000.0 * pr) / (1000 * hmax))
    
    v_key = DRV_KEYS['vblk']
    v_val = int(np.clip(req_vmax - HEIGHT, inv[v_key]['min'], inv[v_key]['max']))
    if v_val % 2 != 0: v_val -= 1
    
    e_key = DRV_KEYS['exp']
    e_val = int(np.clip(req_vmax - 8, inv[e_key]['min'], inv[e_key]['max']))
    
    g_key = DRV_KEYS['gain']
    g_val = int(np.clip(gain, inv[g_key]['min'], inv[g_key]['max']))
    
    return [
        f"v4l2-ctl -d {container.s_node} --set-ctrl={v_key}={v_val}",
        f"v4l2-ctl -d {container.s_node} --set-ctrl={e_key}={e_val}",
        f"v4l2-ctl -d {container.s_node} --set-ctrl={g_key}={g_val}"
    ]

def get_capture_cmd(out_path):
    from snippets.sensors import sensor
    return f"v4l2-ctl -d {sensor.v_node} --stream-mmap --stream-count=1 --stream-to={out_path}"