# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os
import re
import configparser
import shlex
import numpy as np
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import subprocess
import sys
from tqdm import tqdm
import tifffile
from scipy.ndimage import median_filter

CONFIG_FILE_PATH = "/home/length/conf/time-lapse-maker.ini"
INPUT_ROOT_DIR = "/home/length/uploads"
OUTPUT_ROOT_DIR = "/home/length/output"

CONF = {}

def load_config(device_id):
    if not os.path.exists(CONFIG_FILE_PATH):
        print(f"Error: Configuration file not found: {CONFIG_FILE_PATH}")
        sys.exit(1)

    config = configparser.ConfigParser()
    config.read(CONFIG_FILE_PATH, encoding='utf-8')

    try:
        CONF['FRAMERATE'] = config.getint(device_id, 'framerate')
        CONF['FRAME_SKIP'] = config.getint(device_id, 'frame_skip')
        CONF['BLACK_LEVEL'] = config.getint(device_id, 'black_level')
        CONF['WHITE_LEVEL'] = config.getint(device_id, 'white_level')
        CONF['CONTRAST'] = config.getfloat(device_id, 'contrast')
        CONF['GAMMA'] = config.getfloat(device_id, 'gamma')
        CONF['BRIGHTNESS'] = config.getfloat(device_id, 'brightness', fallback=0.0)
        CONF['FONT_PATH'] = config.get(device_id, 'font_path')
        CONF['FONT_SIZE'] = config.getint(device_id, 'font_size')
        CONF['TEXT_COLOR'] = config.getint(device_id, 'text_color')
        CONF['SHADOW_COLOR'] = config.getint(device_id, 'shadow_color')
        CONF['SHADOW_WIDTH'] = config.getint(device_id, 'shadow_width')
        CONF['POSITION'] = tuple(int(x.strip()) for x in config.get(device_id, 'position').split(','))
        CONF['TIMEZONE_OFFSET_HOURS'] = config.getfloat(device_id, 'timezone_offset_hours')
        CONF['ROTATE_DEGREES'] = config.getint(device_id, 'rotate_degrees')
        CONF['FFMPEG_CMD_TEMPLATE'] = config.get(device_id, 'cmd')
        CONF['WIDTH'] = config.getint(device_id, 'width')
        CONF['HEIGHT'] = config.getint(device_id, 'height')
        CONF['MAX_VALUE'] = config.getint(device_id, 'max_value')
    except Exception as e:
        print(f"Configuration parsing error: {e}")
        sys.exit(1)

def load_any_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == '.raw':
            file_size = os.path.getsize(filepath)
            pixel_total = CONF['WIDTH'] * CONF['HEIGHT']
            dtype = np.uint16 if file_size // pixel_total == 2 else np.uint32
            data = np.fromfile(filepath, dtype=dtype).reshape((CONF['HEIGHT'], CONF['WIDTH']))
        elif ext in ['.tif', '.tiff']:
            data = tifffile.imread(filepath)
        else:
            return None

        return np.clip(data.astype(np.float32), 0, CONF['MAX_VALUE'])
    except Exception as e:
        print(f"Failed to load {filepath}: {e}")
        return None

def clean_isolated_pixels(img, threshold=800, size=3):
    if img is None: return None
    smooth = median_filter(img, size=size)
    diff = img - smooth
    bright_mask = diff > threshold
    dark_threshold = threshold / 4
    dark_mask = diff < -dark_threshold
    combined_mask = bright_mask | dark_mask
    img[combined_mask] = smooth[combined_mask]
    return img

def get_master_frame(device_id, folder_name):
    dir_path = os.path.join(INPUT_ROOT_DIR, device_id, folder_name)
    if not os.path.exists(dir_path):
        return None
    
    files = [os.path.join(dir_path, f) for f in os.listdir(dir_path) 
             if f.lower().endswith(('.raw', '.tif', '.tiff'))]
    
    if not files:
        return None

    print(f"[{device_id}] Creating Master {folder_name}...")

    master_sum = np.zeros((CONF['HEIGHT'], CONF['WIDTH']), dtype=np.float64)
    valid_count = 0

    for f in tqdm(files, desc=f"  [{device_id}] Building Master {folder_name}", leave=False):
        data = load_any_file(f)
        if data is not None and data.shape == (CONF['HEIGHT'], CONF['WIDTH']):
            master_sum += data
            valid_count += 1

    if valid_count == 0: return None
    master = (master_sum / valid_count).astype(np.float32)
    
    return clean_isolated_pixels(master, threshold=400)

def process_frame(filepath, m_dark=None, m_bias=None, m_flat=None):
    img = load_any_file(filepath)
    if img is None: return None

    if m_dark is not None:
        img -= m_dark
    elif m_bias is not None:
        img -= m_bias

    if m_flat is not None:
        flat_corrected = m_flat.copy()
        if m_bias is not None:
            flat_corrected -= m_bias
        
        flat_mean = np.mean(flat_corrected)
        if flat_mean > 0:
            flat_norm = flat_corrected / flat_mean
            img /= np.clip(flat_norm, 0.05, None)

    img = clean_isolated_pixels(img, threshold=800)

    img = np.clip(img, 0, CONF['MAX_VALUE'])

    img = (img - CONF['BLACK_LEVEL']) / (CONF['WHITE_LEVEL'] - CONF['BLACK_LEVEL'])
    img = np.clip(img, 0, 1)

    if CONF['BRIGHTNESS'] != 0:
        img = img + CONF['BRIGHTNESS']
        img = np.clip(img, 0, 1)

    if CONF['CONTRAST'] != 1.0:
        img = (img - 0.5) * CONF['CONTRAST'] + 0.5

    if CONF['GAMMA'] != 1.0:
        img = np.power(np.clip(img, 0, 1), 1.0 / CONF['GAMMA'])
    
    img = np.clip(img, 0, 1)
    return Image.fromarray((img * 255).astype(np.uint8), mode='L')

def draw_with_shadow(draw, x, y, text, font):
    sw = CONF['SHADOW_WIDTH']
    for dx in range(-sw, sw + 1):
        for dy in range(-sw, sw + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=CONF['SHADOW_COLOR'])
    draw.text((x, y), text, font=font, fill=CONF['TEXT_COLOR'])

def create_timelapse():
    print("======== Time-Lapse Maker ========")
    
    device_dirs = sorted([d for d in os.listdir(INPUT_ROOT_DIR) if os.path.isdir(os.path.join(INPUT_ROOT_DIR, d))])

    for device_id in device_dirs:
        try:
            load_config(device_id)
        except Exception as e:
            print(f"Skip device {device_id}: No config or error: {e}")
            continue

        scale = CONF['FONT_SIZE'] / 30.0
    
        try:
            font = ImageFont.truetype(CONF['FONT_PATH'], CONF['FONT_SIZE'])
        except:
            font = ImageFont.load_default()

        m_dark = get_master_frame(device_id, "darks")
        m_bias = get_master_frame(device_id, "biases")
        m_flat = get_master_frame(device_id, "flats")

        input_dir = os.path.join(INPUT_ROOT_DIR, device_id, "lights")
        if not os.path.exists(input_dir): continue
        
        all_files = sorted([f for f in os.listdir(input_dir) if f.lower().endswith(('.raw', '.tif', '.tiff'))])
        if not all_files: continue

        selected_files = all_files[::CONF['FRAME_SKIP']]
        out_w, out_h = (CONF['HEIGHT'], CONF['WIDTH']) if CONF['ROTATE_DEGREES'] in [90, 270] else (CONF['WIDTH'], CONF['HEIGHT'])

        device_output_base = os.path.join(OUTPUT_ROOT_DIR, device_id, "time-lapse")
        os.makedirs(device_output_base, exist_ok=True)
        temp_output_v = os.path.join(device_output_base, "rendering.mp4")

        cmd = shlex.split(CONF['FFMPEG_CMD_TEMPLATE'].format(
            width=out_w, height=out_h, framerate=CONF['FRAMERATE'], temp_output_v=temp_output_v
        ))

        process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        pbar = tqdm(selected_files, desc=f"Device {device_id}", unit="frame")
        all_times = []

        regex = re.compile(r".*?_(\d{2})_(\d{8})_(\d{6})_T([\d.]+)_G([\d.]+)_E([\d.-]+)_Y([\d.]+)_CPU(\d+)\.(raw|tif|tiff)$", re.IGNORECASE)

        try:
            for filename in pbar:
                match = regex.match(filename)
                if not match: continue

                dt_obj = datetime.strptime(f"{match.group(2)}{match.group(3)}", "%Y%m%d%H%M%S")
                local_dt = dt_obj + timedelta(hours=CONF['TIMEZONE_OFFSET_HOURS'])
                all_times.append(local_dt)

                img = process_frame(os.path.join(input_dir, filename), m_dark, m_bias, m_flat)
                if img is None: continue

                if CONF['ROTATE_DEGREES'] % 360 != 0:
                    img = img.rotate(CONF['ROTATE_DEGREES'], expand=True)

                draw = ImageDraw.Draw(img)
                e_val = float(match.group(6))
                e_sign = "+" if e_val > 0 else ("-" if e_val < 0 else " ")
                
                info_text = [
                    (0,   local_dt.strftime('%Y-%m-%d %H:%M:%S')),
                    (390, f"T:{match.group(4)}ms"),
                    (220, f"G:{match.group(5)}"),
                    (145, f"E:{e_sign}{abs(e_val):.1f}"),
                    (135, f"Y:{match.group(7)}"),
                    (150, f"CPU:{match.group(8)}°C")
                ]

                curr_x, curr_y = CONF['POSITION']
                for spacing, text in info_text:
                    curr_x += (spacing * scale)
                    draw_with_shadow(draw, curr_x, curr_y, text, font)

                process.stdin.write(img.tobytes())

            process.stdin.close()
            process.wait()

            if all_times:
                final_v = os.path.join(device_output_base, f"{min(all_times).strftime('%Y%m%d_%H%M%S')}~{max(all_times).strftime('%Y%m%d_%H%M%S')}.mp4")
                if os.path.exists(final_v): os.remove(final_v)
                os.rename(temp_output_v, final_v)
                print(f"Successfully exported: {final_v}")

        except Exception as e:
            print(f"\nError: {e}")
            if process.poll() is None: process.terminate()

if __name__ == "__main__":
    create_timelapse()
