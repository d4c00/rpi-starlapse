# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os
import re
import sys
import configparser
import numpy as np
import tifffile
from PIL import Image, ImageFont
from tqdm import tqdm
from utils import (
    INPUT_ROOT_DIR, OUTPUT_ROOT_DIR,
    get_files, get_metadata, load_raw_content,
    master_dark, master_bias, master_flat,
    perform_stacking, render_frame, render_tif, render_jpg,
    rotation, info_overlay,
    dehaze, denoise, gamma, contrast
)

CONFIG_FILE_PATH = "/home/length/conf/convert-tif.ini"
cfg = {}

def load_strict_config(device_id):
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE_PATH, encoding='utf-8')
    if not config.has_section(device_id):
        raise ValueError(f"Missing config section: {device_id}")

    output_modes = {
        'lights': config.getint(device_id, 'output_lights'),
        'darks': config.getint(device_id, 'output_darks'),
        'flats': config.getint(device_id, 'output_flats'),
        'biases': config.getint(device_id, 'output_biases'),
        'stack': config.getint(device_id, 'output_stack'),
    }

    cfg['WIDTH'] = config.getint(device_id, 'width')
    cfg['HEIGHT'] = config.getint(device_id, 'height')
    cfg['BLACK_LEVEL'] = config.getint(device_id, 'black_level')
    cfg['WHITE_LEVEL'] = config.getint(device_id, 'white_level')
    cfg['MAX_VALUE'] = config.getint(device_id, 'white_level')
    cfg['SIG_BITS'] = config.getint(device_id, 'significant_bits')

    cfg['PURE_BRIGHTNESS'] = config.getfloat(device_id, 'brightness')
    cfg['PURE_CONTRAST'] = config.getfloat(device_id, 'contrast')
    cfg['PURE_GAMMA'] = config.getfloat(device_id, 'gamma')

    if output_modes['stack'] > 0:
        cfg['STACK_SIZE'] = config.getint(device_id, 'stack_size')
        cfg['STACK_BRIGHTNESS'] = config.getfloat(device_id, 'stack_brightness')
        cfg['STACK_DEHAZE'] = config.getfloat(device_id, 'stack_dehaze')
        cfg['STACK_CONTRAST'] = config.getfloat(device_id, 'stack_contrast')
        cfg['STACK_GAMMA'] = config.getfloat(device_id, 'stack_gamma')
        cfg['DENOISE_STRENGTH'] = config.getfloat(device_id, 'stack_denoise_strength')
        cfg['DENOISE_SIZE'] = config.getint(device_id, 'stack_denoise_size')
        cfg['ROTATE_DEGREES'] = config.getint(device_id, 'stack_rotate')

        cfg['FONT_PATH'] = config.get(device_id, 'font_path')
        cfg['FONT_SIZE'] = config.getint(device_id, 'font_size')
        cfg['POSITION'] = tuple(int(x.strip()) for x in config.get(device_id, 'position').split(','))
        cfg['TIMEZONE_OFFSET_HOURS'] = config.getfloat(device_id, 'timezone_offset_hours')
        cfg['TEXT_COLOR'] = config.getint(device_id, 'text_color')
        cfg['SHADOW_COLOR'] = config.getint(device_id, 'shadow_color')
        cfg['SHADOW_WIDTH'] = config.getint(device_id, 'shadow_width')

    return output_modes

def process_output_logic(data, mode, out_base, filename, cfg, regex=None, meta=None, font=None, is_stack=False):
    ext = os.path.splitext(filename)[1]
    tif_name = filename.replace(ext, ".tif")
    jpg_name = filename.replace(ext, ".jpg")

    if mode in [2, 3]:
        tif_dir = os.path.join(out_base, "tif")
        os.makedirs(tif_dir, exist_ok=True)
        tif_path = os.path.join(tif_dir, tif_name)
        
        if is_stack:
            render_cfg = {'black_level': cfg['BLACK_LEVEL'], 'white_level': cfg['WHITE_LEVEL']}
            img_tif = render_frame(data, render_cfg)
            img_tif += cfg['STACK_BRIGHTNESS']
            img_tif = dehaze(img_tif, cfg['STACK_DEHAZE'])
            img_tif = gamma(img_tif, cfg['STACK_GAMMA'])
            img_tif = denoise(img_tif, cfg['DENOISE_STRENGTH'], cfg['DENOISE_SIZE'])
            img_tif = contrast(img_tif, cfg['STACK_CONTRAST'])
            render_tif(img_tif, tif_path, cfg['SIG_BITS'], cfg['BLACK_LEVEL'], cfg['WHITE_LEVEL'])
        else:
            render_tif(data, tif_path, cfg['SIG_BITS'], cfg['BLACK_LEVEL'], cfg['WHITE_LEVEL'])

    if mode in [1, 3]:
        jpg_dir = os.path.join(out_base, "jpg")
        os.makedirs(jpg_dir, exist_ok=True)
        out_path = os.path.join(jpg_dir, jpg_name)

        render_cfg = {'black_level': cfg['BLACK_LEVEL'], 'white_level': cfg['WHITE_LEVEL']}
        img_jpg = render_frame(data, render_cfg)

        if is_stack:
            img_jpg += cfg['STACK_BRIGHTNESS']
            img_jpg = dehaze(img_jpg, cfg['STACK_DEHAZE'])
            img_jpg = gamma(img_jpg, cfg['STACK_GAMMA'])
            img_jpg = denoise(img_jpg, cfg['DENOISE_STRENGTH'], cfg['DENOISE_SIZE'])
            img_jpg = contrast(img_jpg, cfg['STACK_CONTRAST'])
        else:
            img_jpg += cfg['PURE_BRIGHTNESS']
            img_jpg = gamma(img_jpg, cfg['PURE_GAMMA'])
            img_jpg = contrast(img_jpg, cfg['PURE_CONTRAST'])

        img_8bit = (np.clip(img_jpg, 0, 1) * 255).astype(np.uint8)
        img_pil = Image.fromarray(img_8bit)

        if is_stack:
            if cfg['ROTATE_DEGREES'] != 0:
                img_pil = rotation(img_pil, cfg['ROTATE_DEGREES'])

            if font and regex:
                if meta is None:
                    meta = get_metadata(filename, regex, cfg['TIMEZONE_OFFSET_HOURS'])
                
                if meta:
                    overlay_cfg = {
                        'text_color': cfg['TEXT_COLOR'],
                        'shadow_color': cfg['SHADOW_COLOR'],
                        'shadow_width': cfg['SHADOW_WIDTH'],
                        'position': cfg['POSITION']
                    }
                    img_pil = info_overlay(img_pil, meta['match_obj'], meta['local_dt'], cfg['FONT_SIZE']/30.0, font, overlay_cfg)
        
        img_pil.save(out_path, quality=95)

def run_main():
    device_dirs = sorted([d for d in os.listdir(INPUT_ROOT_DIR) if os.path.isdir(os.path.join(INPUT_ROOT_DIR, d))])
    regex = re.compile(r".*?_(\d{2})_(\d{8})_(\d{6})_T([\d.]+)_G(\d+)_E([\d.-]+)_Y([\d.]+)_CPU(\d+)\.(raw|tif|tiff)$", re.IGNORECASE)

    for device_id in device_dirs:
        print(f"\n>>> Device: {device_id}")
        try:
            modes = load_strict_config(device_id)
        except Exception as e:
            print(f"Config Error: {e}")
            continue

        if sum(modes.values()) == 0: continue

        device_input_root = os.path.join(INPUT_ROOT_DIR, device_id)

        for folder in ['lights', 'darks', 'flats', 'biases']:
            mode = modes[folder]
            if mode == 0: continue
            
            input_dir = os.path.join(device_input_root, folder)
            if not os.path.exists(input_dir): continue

            files = get_files(input_dir)
            if not files: continue

            out_base = os.path.join(OUTPUT_ROOT_DIR, device_id, folder)
            for f_path in tqdm(files, desc=f"Exporting {folder}"):
                raw_data = load_raw_content(f_path, cfg['WIDTH'], cfg['HEIGHT'], cfg['MAX_VALUE'], keep_raw=True)
                if raw_data is not None:
                    process_output_logic(raw_data, mode, out_base, os.path.basename(f_path), cfg, is_stack=False)

        stack_mode = modes['stack']
        if stack_mode > 0:
            light_in = os.path.join(device_input_root, "lights")
            if os.path.exists(light_in):
                out_base = os.path.join(OUTPUT_ROOT_DIR, device_id, "stack")
                m_bias = master_bias(device_id, INPUT_ROOT_DIR, cfg['WIDTH'], cfg['HEIGHT'], cfg['MAX_VALUE'])
                m_dark = master_dark(device_id, INPUT_ROOT_DIR, cfg['WIDTH'], cfg['HEIGHT'], cfg['MAX_VALUE'])
                m_flat = master_flat(device_id, INPUT_ROOT_DIR, cfg['WIDTH'], cfg['HEIGHT'], cfg['MAX_VALUE'], m_bias=m_bias)
                
                files = get_files(light_in)
                frame_cache = {}
                try:
                    font = ImageFont.truetype(cfg['FONT_PATH'], cfg['FONT_SIZE'])
                except:
                    font = ImageFont.load_default()

                pbar = tqdm(total=len(files), desc="Processing Stack Preview")
                
                for i, f_path in enumerate(files):
                    fname = os.path.basename(f_path)

                    stacked_data = perform_stacking(
                        i, files, light_in, frame_cache, 
                        cfg['STACK_SIZE'], m_dark, m_bias, m_flat,
                        cfg['WIDTH'], cfg['HEIGHT'], cfg['MAX_VALUE']
                    )
                    
                    if stacked_data is not None:
                        pbar.update(1)
                        process_output_logic(stacked_data, stack_mode, out_base, fname, cfg, regex=regex, font=font, is_stack=True)

                pbar.close()
                frame_cache.clear()

if __name__ == "__main__":
    run_main()
