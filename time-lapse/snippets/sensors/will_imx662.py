# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.
# It based on the v4l2 driver from https://github.com/will127534/imx662-v4l2-driver . You can adjust it as needed.

# --- Basic Identity ---
SENSOR_NAME = "imx662"
MEDIA_ENTITY_NAME = "imx662 10-001a"   # Found via 'media-ctl -p'
WIDTH, HEIGHT = 1936, 1100            # Native resolution
MEDIA_CTL_FMT = "SRGGB12_1X12"        # Media-bus format
V4L2_PIXELFORMAT = "RG12"             # Capture format (12-bit Raw)

# --- Physical Constraints ---
RAW_BPP = 2          # Bytes Per Pixel (e.g., 2 for 12-bit unpacked)
EXP_OFFSET = 8       # Exposure line offset (Hardware specific: VMAX - OFFSET)

# --- V4L2 Control Mapping ---
# Maps standard logic names to driver-specific V4L2 control strings
CORE_MAPPING = {
    "exposure": "exposure",
    "gain": "analogue_gain",
    "vblank": "vertical_blanking",
    "hblank": "horizontal_blanking",
    "pixel_rate": "pixel_rate"
}

# --- Driver Extensions ---
# Static parameters applied once during camera initialization
EXTENSIONS = {
    "hcg_enable": 1,      # High Conversion Gain
    "black_level": 64,    # Pedestal level
    "horizontal_flip": 0,
    "vertical_flip": 0
}

# --- AE Workspace ---
# Normalized gain range for Auto Exposure algorithm
VIRT_GAIN_MIN = 1.0
VIRT_GAIN_MAX = 16.0
