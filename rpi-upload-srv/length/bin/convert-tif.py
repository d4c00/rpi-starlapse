# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os
import numpy as np
import tifffile
import configparser
from PIL import Image
from tqdm import tqdm

def load_config(config_path, device_id):
    config = configparser.ConfigParser()
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file missing: {config_path}")
    
    config.read(config_path, encoding='utf-8')

    return {
        'width': config.getint(device_id, 'width'),
        'height': config.getint(device_id, 'height'),
        'black_level': config.getint(device_id, 'black_level'),
        'white_level': config.getint(device_id, 'white_level'),
        'container_bits': config.getint(device_id, 'container_bits'),
        'sig_bits': config.getint(device_id, 'significant_bits'),
        'contrast': config.getfloat(device_id, 'contrast'),
        'gamma': config.getfloat(device_id, 'gamma'),
        'brightness': config.getfloat(device_id, 'brightness', fallback=0.0)  # 新增
    }

def process_for_jpg(image, cfg):
    img_float = (image.astype(np.float32) - cfg['black_level']) / (cfg['white_level'] - cfg['black_level'])
    img_float = np.clip(img_float, 0, 1)

    img_float = img_float + cfg['brightness']
    img_float = np.clip(img_float, 0, 1)

    img_float = (img_float - 0.5) * cfg['contrast'] + 0.5
    img_float = np.clip(img_float, 0, 1)

    if cfg['gamma'] != 1.0:
        img_float = np.power(img_float, 1.0 / cfg['gamma'])

    img_8bit = (img_float * 255).astype(np.uint8)
    return Image.fromarray(img_8bit)

def convert_raw_to_mono_tiff():
    CONFIG_FILE_PATH = "/home/length/conf/convert-tif.ini"
    base_input_dir = "/home/length/uploads"
    base_output_dir = "/home/length/output"

    if not os.path.exists(base_input_dir):
        print("Input directory does not exist")
        return

    device_ids = [d for d in os.listdir(base_input_dir) if os.path.isdir(os.path.join(base_input_dir, d))]

    for device_id in device_ids:
        try:
            cfg = load_config(CONFIG_FILE_PATH, device_id)
            dtype_map = {16: np.uint16, 32: np.uint32}
            target_dtype = dtype_map.get(cfg['container_bits'], np.uint16)
        except Exception as e:
            print(f"Skip device {device_id}: {e}")
            continue
            
        device_root = os.path.join(base_input_dir, device_id)
        sub_dirs = [s for s in os.listdir(device_root) if os.path.isdir(os.path.join(device_root, s))]

        for sub_name in sub_dirs:
            input_dir = os.path.join(device_root, sub_name)

            tiff_output_dir = os.path.join(base_output_dir, device_id, sub_name, "tif")
            jpg_output_dir = os.path.join(base_output_dir, device_id, sub_name, "jpg")

            files = [f for f in os.listdir(input_dir) if f.lower().endswith('.raw')]
            if not files:
                continue

            os.makedirs(tiff_output_dir, exist_ok=True)
            os.makedirs(jpg_output_dir, exist_ok=True)

            for filename in tqdm(files, desc=f"Processing {device_id}/{sub_name}", unit="file"):
                raw_path = os.path.join(input_dir, filename)
                tiff_path = os.path.join(tiff_output_dir, filename.replace(".raw", ".tif"))
                jpg_path = os.path.join(jpg_output_dir, filename.replace(".raw", ".jpg"))

                try:
                    raw_data = np.fromfile(raw_path, dtype=target_dtype)
                    if raw_data.size != cfg['width'] * cfg['height']:
                        print(f"  [Size Error] {filename} - Expected {cfg['width'] * cfg['height']} pixels, but got {raw_data.size}")
                        continue
                
                    image = raw_data.reshape((cfg['height'], cfg['width'])

                    )

                    image = np.clip(image, cfg['black_level'], cfg['white_level']).astype(np.uint16)

                    tifffile.imwrite(
                        tiff_path,
                        image,
                        photometric='minisblack',
                        planarconfig='contig',
                        compression=None,
                        metadata={
                            'SignificantBits': cfg['sig_bits'],
                            'BlackLevel': cfg['black_level'],
                            'WhiteLevel': cfg['white_level']
                        }
                    )

                    jpg_image = process_for_jpg(image, cfg)
                    jpg_image.save(jpg_path, quality=95)

                    tqdm.write(f"[{device_id}/{sub_name}] Success: {filename} → TIFF + JPG")

                except Exception as e:
                    print(f"[{device_id}/{sub_name}] Error {filename}: {e}")

if __name__ == "__main__":
    convert_raw_to_mono_tiff()
