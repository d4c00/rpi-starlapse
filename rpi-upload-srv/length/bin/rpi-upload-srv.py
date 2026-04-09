# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.
import os, time, re, configparser, random, sys
from flask import Flask, request, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

CONFIG_FILE_PATH = '/home/length/conf/rpi-upload-srv.ini'

DEVICE_CONFIGS = {}
LISTEN_PORT = None

def load_configuration():
    global LISTEN_PORT, DEVICE_CONFIGS
    config = configparser.ConfigParser(interpolation=None)
    
    if not os.path.exists(CONFIG_FILE_PATH):
        print(f"Error: Configuration file not found: {CONFIG_FILE_PATH}")
        sys.exit(1)

    config.read(CONFIG_FILE_PATH)
    DEVICE_CONFIGS.clear()

    try:
        LISTEN_PORT = config.getint('settings', 'port')
    except (configparser.NoSectionError, configparser.NoOptionError, ValueError):
        print("Error: [settings] missing 'port' configuration or invalid")
        sys.exit(1)

    sections = [s for s in config.sections() if s.isdigit()]
    if not sections:
        print("Error: No [device_xx] configuration found in the config file")
        sys.exit(1)

    for section in sections:
        try:
            device_id = config.get(section, 'device_id')
            device_token = config.get(section, 'device_token')
            expected_size = config.getint(section, 'expected_raw_size')

            upload_root = '/home/length/uploads'
            final_path = os.path.join(upload_root, device_id)
            os.makedirs(final_path, exist_ok=True)

            DEVICE_CONFIGS[device_id] = {
                "device_id": device_id,
                "device_token": device_token,
                "expected_raw_size": expected_size,
                "upload_folder": final_path
            }
        except Exception as e:
            print(f"Error: Section [{section}] configuration is incomplete or invalid: {e}")
            sys.exit(1)

load_configuration()

SUB_DIR_KEYWORDS = {
    "lights": "lights",
    "darks": "darks",
    "biases": "biases",
}

def is_not_all_zeros(data, sample_count=10000):
    data_len = len(data)
    if data_len == 0: return False
    for _ in range(min(sample_count, data_len)):
        if data[random.randint(0, data_len - 1)] != 0:
            return True
    return False

def validate_device_headers():
    device_id = request.headers.get('X-Device-Id')
    device_token = request.headers.get('X-Device-Token')

    if not device_id or not device_token:
        return None, jsonify({"status": "error", "message": "Missing ID/Token"}), 400

    device_cfg = DEVICE_CONFIGS.get(device_id)
    if not device_cfg:
        return None, jsonify({"status": "error", "message": "Unknown Device"}), 403

    if device_token != device_cfg["device_token"]:
        return None, jsonify({"status": "error", "message": "Invalid Token"}), 401

    return device_cfg, None, None

@app.after_request
def add_delay_for_errors(response):
    if response.status_code != 200:
        time.sleep(0.1)
    return response

@app.route('/upload', methods=['POST'])
def upload_photo():
    allowed_kws = "|".join(SUB_DIR_KEYWORDS.keys())
    FILENAME_PATTERN = rf"^({allowed_kws})_(\d{{2}})_(\d{{8}})_(\d{{6}})_T[\d.]+_+G[\d.]+_+E[\d.-]+_+Y[\d.]+_+CPU\d+\.raw$"

    device_cfg, err_resp, err_code = validate_device_headers()
    if err_resp: return err_resp, err_code

    filename_header = request.headers.get('X-Filename')
    if not filename_header:
        return jsonify({"status": "error", "message": "Missing X-Filename"}), 400

    base_filename = os.path.basename(filename_header)
    match = re.match(FILENAME_PATTERN, base_filename)
    if not match:
        return jsonify({"status": "error", "message": "Invalid Filename Format"}), 415

    if match.group(2) != device_cfg["device_id"]:
        return jsonify({"status": "error", "message": "Filename ID Mismatch"}), 403

    image_data = request.data
    actual_size = len(image_data)
    target_size = device_cfg["expected_raw_size"]

    if actual_size != target_size:
        return jsonify({
            "status": "error", 
            "message": f"Size Mismatch. Expected {target_size}, got {actual_size}"
        }), 406

    if not is_not_all_zeros(image_data, 100):
        return jsonify({"status": "error", "message": "Invalid Data (All Zeros)"}), 422

    target_sub_dir = SUB_DIR_KEYWORDS[match.group(1)]
    final_upload_path = os.path.join(device_cfg["upload_folder"], target_sub_dir)
    
    try:
        os.makedirs(final_upload_path, exist_ok=True)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to create directory: {str(e)}"}), 500

    filepath = os.path.join(final_upload_path, base_filename)
    tmppath = filepath + ".tmp"

    try:
        with open(tmppath, 'wb') as f:
            f.write(image_data)
            f.flush()
            os.fsync(f.fileno())
        
        os.replace(tmppath, filepath)

        if os.path.getsize(filepath) != target_size:
            if os.path.exists(filepath): os.remove(filepath)
            return jsonify({"status": "error", "message": "Disk IO Size Inconsistency"}), 500

    except Exception as e:
        if os.path.exists(tmppath): os.remove(tmppath)
        return jsonify({"status": "error", "message": f"IO Error: {str(e)}"}), 500

    return jsonify({"status": "success", "message": f"Accepted {base_filename}"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=LISTEN_PORT, debug=False, threaded=True)
