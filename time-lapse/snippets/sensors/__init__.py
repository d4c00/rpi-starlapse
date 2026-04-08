# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os, importlib, re, subprocess, pkgutil, inspect
from functools import partial
import snippets.sensors as sensors_pkg

class SensorContainer:
    def __init__(self, mod):
        self.raw_config = mod

        for attr_name in dir(mod):
            if attr_name.startswith("__"): continue
            attr_value = getattr(mod, attr_name)

            if inspect.isfunction(attr_value):
                sig = inspect.signature(attr_value)
                if 'container' in sig.parameters:
                    setattr(self, attr_name, partial(attr_value, container=self))
                else:
                    setattr(self, attr_name, attr_value)
            else:
                setattr(self, attr_name, attr_value)

        self.m_node, self.s_node, self.v_node = self._find_nodes()

        self.hw_inventory = {}
        if hasattr(self, "parse_hw_inventory"):
            self.hw_inventory = self.parse_hw_inventory()

    def _find_nodes(self):
        patterns = getattr(self.raw_config, "SEARCH_PATTERNS", {})
        entity_name = getattr(self.raw_config, "MEDIA_ENTITY_NAME", "")
        
        for i in range(10):
            path = f"/dev/media{i}"
            if not os.path.exists(path): continue
            out = subprocess.run(f"media-ctl -d {path} -p", shell=True, capture_output=True, text=True).stdout
            
            if entity_name.lower() in out.lower():
                try:
                    res = {}
                    for key, pat in patterns.items():
                        m = re.search(rf"{pat}.*?device node name\s+(/dev/[a-z0-9-]+)", out, re.S | re.I)
                        res[key] = m.group(1) if m else None

                    return path, res.get("s_node"), res.get("v_node")
                except: continue
        raise RuntimeError(f"Sensor '{getattr(self.raw_config, 'SENSOR_NAME', 'Unknown')}' not found.")

def _init_factory():
    entities = ""
    for i in range(5):
        p = f"/dev/media{i}"
        if os.path.exists(p):
            entities += subprocess.run(f"media-ctl -d {p} -p", shell=True, capture_output=True, text=True).stdout

    for _, module_name, _ in pkgutil.iter_modules(sensors_pkg.__path__):
        if module_name == "sensor": continue
        mod = importlib.import_module(f"snippets.sensors.{module_name}")
        if getattr(mod, "MEDIA_ENTITY_NAME", "N/A") in entities:
            return SensorContainer(mod)
    raise RuntimeError("No matching sensor config.")

sensor = _init_factory()