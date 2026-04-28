# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os
import re
import configparser
import sys
import numpy as np
from datetime import datetime
from tqdm import tqdm
from PIL import Image, ImageFont
from utils import (
    INPUT_ROOT_DIR, OUTPUT_ROOT_DIR,
    get_files, get_metadata, load_raw_content,
    master_dark, master_bias, master_flat,
    perform_stacking, render_frame, rotation,
    info_overlay, ffmpeg_process, video,
    contrast, gamma, dehaze, denoise
)

CONFIG_FILE_PATH = "/home/length/conf/time-lapse-maker.ini"
cfg = {}

def load_config(device_id):
    if not os.path.exists(CONFIG_FILE_PATH):
        print(f"Error: Configuration file not found: {CONFIG_FILE_PATH}")
        sys.exit(1)

    config = configparser.ConfigParser()
    config.read(CONFIG_FILE_PATH, encoding='utf-8')

    try:
        cfg['WIDTH'] = config.getint(device_id, 'width')
        cfg['HEIGHT'] = config.getint(device_id, 'height')
        cfg['MAX_VALUE'] = config.getint(device_id, 'max_value')
        cfg['FRAMERATE'] = config.getint(device_id, 'framerate')
        cfg['FRAME_SKIP'] = config.getint(device_id, 'frame_skip')
        cfg['BLACK_LEVEL'] = config.getint(device_id, 'black_level')
        cfg['WHITE_LEVEL'] = config.getint(device_id, 'white_level')
        cfg['BRIGHTNESS'] = config.getfloat(device_id, 'brightness')
        cfg['DEHAZE'] = config.getfloat(device_id, 'dehaze')
        cfg['CONTRAST'] = config.getfloat(device_id, 'contrast')
        cfg['GAMMA'] = config.getfloat(device_id, 'gamma')
        cfg['DENOISE_STRENGTH'] = config.getfloat(device_id, 'denoise_strength')
        cfg['DENOISE_SIZE'] = config.getint(device_id, 'denoise_size')
        cfg['STACK_SIZE'] = config.getint(device_id, 'stack_size')
        cfg['FONT_PATH'] = config.get(device_id, 'font_path')
        cfg['FONT_SIZE'] = config.getint(device_id, 'font_size')
        cfg['TEXT_COLOR'] = config.getint(device_id, 'text_color')
        cfg['SHADOW_COLOR'] = config.getint(device_id, 'shadow_color')
        cfg['SHADOW_WIDTH'] = config.getint(device_id, 'shadow_width')
        cfg['POSITION'] = tuple(int(x.strip()) for x in config.get(device_id, 'position').split(','))
        cfg['TIMEZONE_OFFSET_HOURS'] = config.getfloat(device_id, 'timezone_offset_hours')
        cfg['ROTATE_DEGREES'] = config.getint(device_id, 'rotate_degrees')
        cfg['FFMPEG_CMD_TEMPLATE'] = config.get(device_id, 'cmd')
        
    except Exception as e:
        print(f"Configuration parsing error for {device_id}: {e}")
        raise

def run_task():
    print("======== Time-Lapse Maker ========")

    device_dirs = sorted([d for d in os.listdir(INPUT_ROOT_DIR) 
                         if os.path.isdir(os.path.join(INPUT_ROOT_DIR, d))])

    regex = re.compile(r".*?_(\d{2})_(\d{8})_(\d{6})_T([\d.]+)_G(\d+)_E([\d.-]+)_Y([\d.]+)_CPU(\d+)\.(raw|tif|tiff)$", re.IGNORECASE)

    for device_id in device_dirs:
        try:
            load_config(device_id)
        except:
            continue

        print(f"\n>>> Processing Device: {device_id}")

        m_bias = master_bias(device_id, INPUT_ROOT_DIR, cfg['WIDTH'], cfg['HEIGHT'], cfg['MAX_VALUE'])
        m_dark = master_dark(device_id, INPUT_ROOT_DIR, cfg['WIDTH'], cfg['HEIGHT'], cfg['MAX_VALUE'])
        m_flat = master_flat(device_id, INPUT_ROOT_DIR, cfg['WIDTH'], cfg['HEIGHT'], cfg['MAX_VALUE'], m_bias=m_bias)

        input_dir = os.path.join(INPUT_ROOT_DIR, device_id, "lights")
        all_files = get_files(input_dir)
        if not all_files: continue

        selected_files = all_files[::cfg['FRAME_SKIP']]
        out_w, out_h = (cfg['HEIGHT'], cfg['WIDTH']) if cfg['ROTATE_DEGREES'] in [90, 270] else (cfg['WIDTH'], cfg['HEIGHT'])

        device_output_base = os.path.join(OUTPUT_ROOT_DIR, device_id, "time-lapse")
        os.makedirs(device_output_base, exist_ok=True)
        temp_v = os.path.join(device_output_base, "rendering.mp4")

        process = ffmpeg_process(out_w, out_h, cfg['FRAMERATE'], temp_v, cfg['FFMPEG_CMD_TEMPLATE'])

        scale = cfg['FONT_SIZE'] / 30.0
        try:
            font = ImageFont.truetype(cfg['FONT_PATH'], cfg['FONT_SIZE'])
        except:
            font = ImageFont.load_default()

        pbar = tqdm(total=len(selected_files), desc=f"Rendering {device_id}", unit="frame")
        all_times = []
        frame_cache = {}

        try:
            for i, filepath in enumerate(selected_files): 
                filename = os.path.basename(filepath)

                stacked_data = perform_stacking(
                    i, selected_files, input_dir, frame_cache, 
                    cfg['STACK_SIZE'], m_dark, m_bias, m_flat,
                    cfg['WIDTH'], cfg['HEIGHT'], cfg['MAX_VALUE']
                )
                if stacked_data is None: continue

                render_cfg = {'black_level': cfg['BLACK_LEVEL'], 'white_level': cfg['WHITE_LEVEL']}
                img = render_frame(stacked_data, render_cfg)

                if cfg['BRIGHTNESS'] != 0: img += cfg['BRIGHTNESS']
                if cfg['DEHAZE'] > 0: img = dehaze(img, cfg['DEHAZE'])
                if cfg['GAMMA'] != 1.0: img = gamma(img, cfg['GAMMA'])
                if cfg['DENOISE_STRENGTH'] > 0: img = denoise(img, cfg['DENOISE_STRENGTH'], cfg['DENOISE_SIZE'])
                if cfg['CONTRAST'] > 1.0: img = contrast(img, cfg['CONTRAST'])

                img_8bit = (np.clip(img, 0, 1) * 255).astype(np.uint8)
                img_pil = Image.fromarray(img_8bit)

                if cfg['ROTATE_DEGREES'] != 0:
                    img_pil = rotation(img_pil, cfg['ROTATE_DEGREES'])

                meta = get_metadata(filename, regex, cfg['TIMEZONE_OFFSET_HOURS'])
                if meta:
                    all_times.append(meta['local_dt'])
                    overlay_cfg = {
                        'text_color': cfg['TEXT_COLOR'],
                        'shadow_color': cfg['SHADOW_COLOR'],
                        'shadow_width': cfg['SHADOW_WIDTH'],
                        'position': cfg['POSITION']
                    }
                    img_pil = info_overlay(img_pil, meta['match_obj'], meta['local_dt'], scale, font, overlay_cfg)

                process.stdin.write(img_pil.tobytes())
                pbar.update(1)
            pbar.close()

            video(process, temp_v, all_times, device_output_base)
            frame_cache.clear()

        except Exception as e:
            print(f"\nCRITICAL ERROR: {e}")
            if process.poll() is None:
                process.terminate()

if __name__ == "__main__":
    run_task()
