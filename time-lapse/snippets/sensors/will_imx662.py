# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.
import numpy as np

# --- Basic Identity ---
SENSOR_NAME = "imx662"
MEDIA_ENTITY_NAME = "imx662 10-001a"
WIDTH, HEIGHT = 1936, 1100
MEDIA_CTL_FMT = "SRGGB12_1X12"
V4L2_PIXELFORMAT = "RG12"

# --- Physical Constraints ---
RAW_BPP = 2
EXP_OFFSET = 8
MIN_EXPOSURE = 1.2e-5
MAX_EXPOSURE = 1.0
MIN_GAIN = 1
MAX_GAIN = 480

# --- V4L2 Control Mapping ---
CORE_MAPPING = {
    "exposure": "exposure",
    "gain": "analogue_gain",
    "vblank": "vertical_blanking",
    "hblank": "horizontal_blanking",
    "pixel_rate": "pixel_rate"
}

# --- Driver Extensions ---
EXTENSIONS = {
    "hcg_enable": 1,
    "black_level": 64,
    "horizontal_flip": 0,
    "vertical_flip": 0
}

VIRT_GAIN_MIN = 1.0
VIRT_GAIN_MAX = 16.0

def get_runtime_ctrls(target_us, gain, container):
    pixel_rate = container.hw_inventory[CORE_MAPPING['pixel_rate']]['val']
    hblank = container.hw_inventory[CORE_MAPPING['hblank']]['val']
    hmax = WIDTH + hblank

    req_vmax = int((target_us / 1000.0 * pixel_rate) / (1000 * hmax))

    v_key, e_key, g_key = CORE_MAPPING['vblank'], CORE_MAPPING['exposure'], CORE_MAPPING['gain']

    return {
        v_key: int(np.clip(req_vmax - HEIGHT, container.hw_inventory[v_key]['min'], container.hw_inventory[v_key]['max'])),
        e_key: int(np.clip(req_vmax - EXP_OFFSET, container.hw_inventory[e_key]['min'], container.hw_inventory[e_key]['max'])),
        g_key: int(np.clip(gain, container.hw_inventory[g_key]['min'], container.hw_inventory[g_key]['max']))
    }
