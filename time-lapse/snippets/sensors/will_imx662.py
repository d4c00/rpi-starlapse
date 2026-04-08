# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.
import numpy as np

SENSOR_NAME = "imx662"
MEDIA_ENTITY_NAME = "imx662 10-001a"
WIDTH, HEIGHT = 1936, 1100
MEDIA_CTL_FMT = "SRGGB12_1X12"
V4L2_PIXELFORMAT = "RG12"

RAW_BPP = 2
EXP_OFFSET = 8
MIN_EXPOSURE = 1.0e-6 
MAX_EXPOSURE = 1.0     
MIN_GAIN = 34
MAX_GAIN = 240

VIRT_GAIN_MIN = 1.0
VIRT_GAIN_MAX = 16.0

_MAP = {
    "exp": "exposure",
    "gain": "analogue_gain",
    "vblk": "vertical_blanking",
    "hblk": "horizontal_blanking",
    "pr": "pixel_rate"
}

EXTENSIONS = {
    "hcg_enable": 1,
    "brightness": 50,
    "horizontal_flip": 0,
    "vertical_flip": 0
}

def get_runtime_ctrls(target_us, gain, container):
    inv = container.hw_inventory
    pix_rate = inv[_MAP['pr']]['val']
    hmax = WIDTH + inv[_MAP['hblk']]['val']

    req_vmax = int((target_us / 1000.0 * pix_rate) / (1000 * hmax))

    ctrls = []
    
    v_val = int(np.clip(req_vmax - HEIGHT, inv[_MAP['vblk']]['min'], inv[_MAP['vblk']]['max']))
    ctrls.append((_MAP['vblk'], v_val))
    
    e_val = int(np.clip(req_vmax - EXP_OFFSET, inv[_MAP['exp']]['min'], inv[_MAP['exp']]['max']))
    g_val = int(np.clip(gain, inv[_MAP['gain']]['min'], inv[_MAP['gain']]['max']))

    ctrls.append((_MAP['exp'], e_val))
    ctrls.append((_MAP['gain'], g_val))
    
    return ctrls
