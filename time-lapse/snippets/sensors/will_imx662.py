# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import subprocess, re, numpy as np

SENSOR_NAME = "imx662"
MEDIA_ENTITY_NAME = "imx662 10-001a"
WIDTH, HEIGHT = 1936, 1100
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

def parse_hw_inventory(container):
    inventory = {}
    try:
        out = subprocess.check_output(f"v4l2-ctl -d {container.s_node} --list-ctrls", shell=True, text=True)

        pattern = re.compile(r"([a-z0-9_]+)\s+0x[0-9a-f]+\s+\([a-z]+\)\s+:\s+min=(-?\d+)\s+max=(-?\d+).*?value=(-?\d+)")
        
        for line in out.splitlines():
            m = pattern.search(line)
            if m:
                inventory[m.group(1)] = {
                    'min': int(m.group(2)),
                    'max': int(m.group(3)),
                    'val': int(m.group(4))
                }
    except Exception as e:
        print(f"[IMX662] Critical error parsing hw: {e}")
        
    return inventory

def get_init_cmds(container):
    cmds = [
        f"media-ctl -d {container.m_node} -V \"'{container.MEDIA_ENTITY_NAME}':0 [fmt:{container.MEDIA_CTL_FMT}/{container.WIDTH}x{container.HEIGHT}]\"",
        f"v4l2-ctl -d {container.v_node} --set-fmt-video=width={container.WIDTH},height={container.HEIGHT},pixelformat={container.V4L2_PIXELFORMAT}",
        f"v4l2-ctl -d {container.s_node} --set-ctrl=hcg_enable=1"
    ]
    return cmds

def get_runtime_ctrls(target_us, gain, container):
    inv = container.hw_inventory
    pr = inv.get(DRV_KEYS['prate'], {'val': 72600000})['val']
    hb = inv.get(DRV_KEYS['hblk'], {'val': 0})['val']
    hmax = WIDTH + hb
    
    req_vmax = int((target_us / 1000.0 * pr) / (1000 * hmax))

    ctrls = []

    v_key = DRV_KEYS['vblk']
    v_val = int(np.clip(req_vmax - HEIGHT, inv[v_key]['min'], inv[v_key]['max']))
    ctrls.append((v_key, v_val))

    e_key = DRV_KEYS['exp']
    e_val = int(np.clip(req_vmax - 8, inv[e_key]['min'], inv[e_key]['max']))
    ctrls.append((e_key, e_val))

    g_key = DRV_KEYS['gain']
    g_val = int(np.clip(gain, inv[g_key]['min'], inv[g_key]['max']))
    ctrls.append((g_key, g_val))
    
    return ctrls

MIN_EXPOSURE = 1e-6
MAX_EXPOSURE = 1.0
MIN_GAIN = 34
MAX_GAIN = 240
VIRT_GAIN_MIN = 1.0
VIRT_GAIN_MAX = 16.0
