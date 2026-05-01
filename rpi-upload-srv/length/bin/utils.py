# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os
import shlex
import subprocess
import numpy as np
import cv2
import tifffile
import astroalign as aa
from scipy.ndimage import gaussian_filter, minimum_filter
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import median_filter
from tqdm import tqdm

INPUT_ROOT_DIR = "/home/length/uploads"
OUTPUT_ROOT_DIR = "/home/length/output"

def get_files(dir_path):
    if not dir_path or not os.path.exists(dir_path):
        return []

    EXTENSIONS = ('.raw', '.tif', '.tiff')
    
    files = [
        os.path.join(dir_path, f) 
        for f in os.listdir(dir_path) 
        if f.lower().endswith(EXTENSIONS)
    ]
    return sorted(files)

def get_metadata(filename, regex, timezone_offset):
    match = regex.match(filename)
    if not match:
        return None

    dt_obj = datetime.strptime(f"{match.group(2)}{match.group(3)}", "%Y%m%d%H%M%S")
    local_dt = dt_obj + timedelta(hours=timezone_offset)

    e_val = float(match.group(6))
    e_sign = "+" if e_val > 0 else ("-" if e_val < 0 else " ")

    return {
        "local_dt": local_dt,
        "exposure_ms": match.group(4),
        "gain": int(float(match.group(5))),
        "ev_text": f"{e_sign}{abs(e_val):.1f}",
        "y_val": match.group(7),
        "cpu_temp": match.group(8),
        "match_obj": match
    }

def load_raw_content(filepath, width, height, max_value, keep_raw=False):
    ext = os.path.splitext(filepath)[1].lower()
    try:
        if ext == '.raw':
            file_size = os.path.getsize(filepath)
            pixel_total = width * height

            if file_size == pixel_total * 2:
                dtype = np.uint16
            elif file_size == pixel_total * 4:
                dtype = np.uint32
            else:
                raise ValueError(f"Size mismatch: {file_size}")

            data = np.fromfile(filepath, dtype=dtype).reshape((height, width))
            
        elif ext in ['.tif', '.tiff']:
            data = tifffile.imread(filepath)
        else:
            return None

        if keep_raw:
            return data

        return np.clip(data.astype(np.float32), 0, max_value)
        
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        raise e

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

def stacking(i, selected_files, input_dir, frame_cache, stack_size, m_dark, m_bias, m_flat, width, height, max_value):
    total_frames = len(selected_files)
    needed_indices = range(max(0, i - stack_size), min(total_frames, i + stack_size + 1))

    for idx in needed_indices:
        if idx not in frame_cache:
            f_path = os.path.join(input_dir, selected_files[idx])
            raw_data = load_raw_content(f_path, width, height, max_value)
            if raw_data is not None:
                frame_cache[idx] = calibration(raw_data, m_dark, m_bias, m_flat, max_value)

    for idx in list(frame_cache.keys()):
        if idx < i - stack_size:
            del frame_cache[idx]

    target_img = frame_cache[i]
    if target_img is None:
        return None

    if stack_size > 0:
        aligned_images = []
        for idx in needed_indices:
            img_to_align = frame_cache[idx]
            if img_to_align is None: continue
            
            if idx == i:
                aligned_images.append(target_img)
                continue
                
            try:
                aligned, footprint = aa.register(img_to_align, target_img)
                aligned_images.append(aligned)
            except Exception:
                continue 

        if len(aligned_images) < 2:
            return target_img

        stack_array = np.array(aligned_images, dtype=np.float32)
        
        med = np.median(stack_array, axis=0)

        std = np.std(stack_array, axis=0) 
        
        sigma = 1.5
        lower_bound = med - sigma * std
        upper_bound = med + sigma * std

        mask = (stack_array < lower_bound) | (stack_array > upper_bound)
        stack_array[mask] = np.nan

        stacked_data = np.nanmean(stack_array, axis=0)

        nan_mask = np.isnan(stacked_data)
        if np.any(nan_mask):
            stacked_data[nan_mask] = med[nan_mask]
            
    else:
        stacked_data = target_img

    return stacked_data

def master_dark(device_id, input_root, width, height, max_value):
    m_dark = get_master_frame(device_id, "darks", input_root, width, height, max_value)
    if m_dark is not None:
        return clean_isolated_pixels(m_dark, threshold=400)
    return None

def master_bias(device_id, input_root, width, height, max_value):
    m_bias = get_master_frame(device_id, "biases", input_root, width, height, max_value)
    if m_bias is not None:
        return clean_isolated_pixels(m_bias, threshold=400)
    return None

def master_flat(device_id, input_root, width, height, max_value, m_bias=None):
    m_flat = get_master_frame(device_id, "flats", input_root, width, height, max_value, bias=m_bias)
    
    if m_flat is not None:
        np.maximum(m_flat, 1e-6, out=m_flat)

        m_flat = clean_isolated_pixels(m_flat, threshold=400)
        m_flat = gaussian_filter(m_flat, sigma=0.5)

        return m_flat
    return None

def get_master_frame(device_id, folder_name, input_root, width, height, max_value, bias=None):
    dir_path = os.path.join(input_root, device_id, folder_name)
    files = get_files(dir_path)
    
    if not files: return None

    print(f"[{device_id}] Creating Master {folder_name}...")
    master_sum = np.zeros((height, width), dtype=np.float64)
    valid_count = 0

    for f in tqdm(files, desc=f"  Building {folder_name}", leave=False):
        data = load_raw_content(f, width, height, max_value)
        if data is not None and data.shape == (height, width):
            if bias is not None:
                data = data - bias
            master_sum += data
            valid_count += 1

    return (master_sum / valid_count).astype(np.float32) if valid_count > 0 else None

def calibration(data, m_dark, m_bias, m_flat, max_value):
    if m_dark is not None:
        data = data - m_dark

    data = np.maximum(data, 1e-5) 

    if m_flat is not None:
        flat_median = np.median(m_flat)
        if flat_median > 0:
            flat_norm = np.clip(m_flat / flat_median, 0.2, 5.0)
            data = data / flat_norm

    data = clean_isolated_pixels(data, threshold=800)
    
    return np.clip(data, 0, max_value)

def contrast(img, contrast_factor):
    if contrast_factor <= 1.0:
        return img

    img_f32 = img.astype(np.float32)

    median = np.median(img_f32)
    pivot = np.clip(median + 0.02, 0.05, 0.5)

    k = contrast_factor

    out = 1.0 / (1.0 + np.exp(-k * (img_f32 - pivot)))

    min_val = 1.0 / (1.0 + np.exp(-k * (0.0 - pivot)))
    max_val = 1.0 / (1.0 + np.exp(-k * (1.0 - pivot)))
    
    out = (out - min_val) / (max_val - min_val)
    
    return np.clip(out, 0, 1)

def dehaze(img, strength):
    if strength <= 0:
        return img

    img_f32 = img.astype(np.float32)
    h, w = img_f32.shape

    scale = 16
    small = cv2.resize(img_f32, (w // scale, h // scale), interpolation=cv2.INTER_AREA)

    bg = cv2.GaussianBlur(small, (0, 0), sigmaX=15)

    bg_full = cv2.resize(bg, (w, h), interpolation=cv2.INTER_CUBIC)

    out = img_f32 - bg_full * strength

    return np.clip(out, 0, 1)

def gamma(img, gamma_value):
    if gamma_value == 1.0:
        return img
        
    img_clipped = np.clip(img, 1e-6, 1.0)
    
    stretch_factor = 50.0
    asinh_img = np.arcsinh(img_clipped * stretch_factor) / np.arcsinh(stretch_factor)

    return np.power(asinh_img, 1.0 / gamma_value)

def denoise(img, strength, size):
    if strength <= 0:
        return img

    smoothed = median_filter(img, size=size)
    
    details = img - smoothed
    
    star_mask = cv2.GaussianBlur(np.clip(details * 5, 0, 1), (3, 3), 0)

    background_denoised = (img * (1 - strength)) + (smoothed * strength)
    
    output = img * star_mask + background_denoised * (1 - star_mask)
    
    return np.clip(output, 0, 1)

def brightness(data, cfg):
    denominator = max(1, cfg['white_level'] - cfg['black_level'])
    img = (data - cfg['black_level']) / denominator
    img = np.clip(img, 0, 1)

    b_val = cfg.get('BRIGHTNESS', 0)
    if b_val == 0:
        return img

    m = 0.5 * (1.0 - b_val * 0.8) 
    m = np.clip(m, 0.01, 0.99)

    img_stretched = ((m - 1) * img) / ((2 * m - 1) * img - m + 1e-8)
    
    return np.clip(img_stretched, 0, 1)

def rotation(img, degrees):
    if degrees != 0:
        return img.rotate(degrees, expand=True)
    return img

def info_overlay(img, match, local_dt, scale, font, overlay_cfg):
    draw = ImageDraw.Draw(img)

    e_val = float(match.group(6))
    e_sign = "+" if e_val > 0 else ("-" if e_val < 0 else " ")

    info_text = [
        (0,   local_dt.strftime('%Y-%m-%d %H:%M:%S')),
        (390, f"T:{match.group(4)}ms"),
        (220, f"G:{int(float(match.group(5)))}"),
        (105, f"E:{e_sign}{abs(e_val):.1f}"),
        (135, f"Y:{match.group(7)}"),
        (150, f"CPU:{match.group(8)}°C")
    ]

    text_color = overlay_cfg['text_color']
    shadow_color = overlay_cfg['shadow_color']
    sw = overlay_cfg['shadow_width']
    curr_x, curr_y = overlay_cfg['position']
    
    for spacing, text in info_text:
        curr_x += (spacing * scale)

        for dx in range(-sw, sw + 1):
            for dy in range(-sw, sw + 1):
                if dx != 0 or dy != 0:
                    draw.text((curr_x + dx, curr_y + dy), text, font=font, fill=shadow_color)

        draw.text((curr_x, curr_y), text, font=font, fill=text_color)
        
    return img

def ffmpeg_process(out_w, out_h, framerate, output_path, cmd_template):
    cmd_str = cmd_template.format(
        width=out_w, 
        height=out_h, 
        framerate=framerate, 
        temp_output_v=output_path
    )
    cmd = shlex.split(cmd_str)
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)

def video(process, temp_v, all_times, device_output_base):
    process.stdin.close()
    process.wait()

    if all_times:
        start_t = min(all_times).strftime('%Y%m%d_%H%M%S')
        end_t = max(all_times).strftime('%Y%m%d_%H%M%S')
        final_v = os.path.join(device_output_base, f"{start_t}~{end_t}.mp4")
        
        if os.path.exists(final_v): 
            os.remove(final_v)
        os.rename(temp_v, final_v)
        print(f"Successfully exported: {final_v}")
    else:
        print("No frames were processed, cleanup temp file.")
        if os.path.exists(temp_v): os.remove(temp_v)

def render_tif(raw_data, output_path, sig_bits, black_level, white_level):
    if np.issubdtype(raw_data.dtype, np.integer):
        tifffile.imwrite(
            output_path,
            raw_data,
            photometric='minisblack',
            planarconfig='contig',
            compression=None
        )
    else:
        out_data = (raw_data * (white_level - black_level) + black_level)
        out_data = out_data.astype(np.uint16 if sig_bits <= 16 else np.uint32)
        tifffile.imwrite(
            output_path,
            out_data,
            photometric='minisblack',
            planarconfig='contig',
            compression=None,
            metadata={
                'SignificantBits': sig_bits,
                'BlackLevel': black_level,
                'WhiteLevel': white_level
            }
        )

def render_jpg(image_float, output_path, quality):
    img_8bit = (np.clip(image_float, 0, 1) * 255).astype(np.uint8)
    Image.fromarray(img_8bit).save(output_path, quality=quality)
