# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os, importlib, re, subprocess

def _detect_sensor():
    for i in range(6):
        path = f"/dev/media{i}"
        if not os.path.exists(path):
            continue
        try:
            out = subprocess.check_output(
                f"media-ctl -d {path} -p", shell=True, text=True, stderr=subprocess.STDOUT, timeout=3
            )
            match = re.search(r"(imx\d+|ov\d+|ar\d+)", out, re.IGNORECASE)
            if match:
                return match.group(1).lower()
        except:
            continue
    raise RuntimeError("No sensor detected via media-ctl")

sensor = importlib.import_module(f"snippets.sensors.{_detect_sensor()}")
print(f"[SENSOR] Loaded: {sensor.SENSOR_NAME}")