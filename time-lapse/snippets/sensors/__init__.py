# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os
import importlib.util
import fcntl
from snippets.config import SENSOR_INDEX

class BaseSensor:
    def __init__(self, mod, v_node, s_node):
        for name in dir(mod):
            if not name.startswith("__"):
                setattr(self, name, getattr(mod, name))
        
        self.v_node = v_node
        self.s_node = s_node
        
        self.v_fd = os.open(self.v_node, os.O_RDWR | os.O_NONBLOCK)
        self.s_fd = os.open(self.s_node, os.O_RDWR)
        
        if hasattr(self, "WIDTH") and hasattr(self, "HEIGHT"):
            self.EXACT_RAW_SIZE = self.WIDTH * self.HEIGHT * 2

        if hasattr(self, "apply_init"):
            self.apply_init(self)

        self._refresh_hardware_limits()

    def _refresh_hardware_limits(self):
        if not hasattr(self, "get_v4l2_ctrls"):
            return
            
        ctrls = self.get_v4l2_ctrls(self.s_fd)

        if 'exposure' in ctrls:
            self.HW_MIN_LINES = ctrls['exposure']['min']
            self.HW_MAX_LINES = ctrls['exposure']['max']

        if 'analogue_gain' in ctrls:
            self.MIN_GAIN = ctrls['analogue_gain']['min']
            self.MAX_GAIN = ctrls['analogue_gain']['max']

        if hasattr(self, '_calculate_phys_exposure'):
            self.MIN_EXPOSURE = self._calculate_phys_exposure(self.HW_MIN_LINES, self, mode="min")

            v_max = ctrls.get('vertical_blanking', {'max': 1000})['max']
            self.MAX_EXPOSURE = self._calculate_phys_exposure(self.HEIGHT + v_max, self, mode="max")

            self.AE_MIN_US = int(self.MIN_EXPOSURE * 1e6)

        print(f"[*] Hardware Limits Loaded for {getattr(self, 'SENSOR_NAME', 'Unknown')}")
        if hasattr(self, 'MIN_EXPOSURE'):
            print(f"    - Exposure: {self.MIN_EXPOSURE*1000:.3f}ms ~ {self.MAX_EXPOSURE*1000:.3f}ms")
            print(f"    - Gain: {self.MIN_GAIN} ~ {self.MAX_GAIN}")

    def __del__(self):
        if hasattr(self, 's_fd') and self.s_fd:
            os.close(self.s_fd)
        if hasattr(self, 'v_fd') and self.v_fd:
            os.close(self.v_fd)

def _init_factory():
    hw_sensors = []
    v_node = None
    base_v4l = "/sys/class/video4linux"

    if os.path.exists(base_v4l):
        for dev in sorted(os.listdir(base_v4l)):
            p = os.path.join(base_v4l, dev, "name")
            if not os.path.exists(p):
                continue
            with open(p, 'r') as f:
                name_str = f.read().strip().lower()
                if "subdev" in dev:
                    hw_sensors.append({"name": name_str, "node": f"/dev/{dev}"})
                elif "video" in dev:
                    uevent_p = os.path.join(base_v4l, dev, "device/uevent")
                    if os.path.exists(uevent_p):
                        with open(uevent_p, 'r') as uf:
                            if "unicam" in uf.read().lower():
                                v_node = f"/dev/{dev}"

    pkg_path = os.path.dirname(__file__)
    match_list = []
    for f in sorted(os.listdir(pkg_path)):
        if f.endswith(".py") and f != "__init__.py":
            mod_name = f[:-3]
            spec = importlib.util.spec_from_file_location(mod_name, os.path.join(pkg_path, f))
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            
            if hasattr(m, "SENSOR_NAME"):
                for hw in hw_sensors:
                    if m.SENSOR_NAME.lower() in hw['name']:
                        match_list.append({
                            "mod": m, 
                            "s": hw['node'], 
                            "v": v_node
                        })

    if not match_list:
        raise RuntimeError("Fatal: No hardware matched the available drivers.")

    sel = match_list[SENSOR_INDEX % len(match_list)]
    print(f"[*] Auto-Matched Driver: {sel['mod'].SENSOR_NAME} on {sel['s']}")
    
    return BaseSensor(sel['mod'], sel['v'], sel['s'])

sensor = _init_factory()