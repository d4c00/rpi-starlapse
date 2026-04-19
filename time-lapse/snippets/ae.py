# Copyright (c) 2026 length <me@length.cc>
# Licensed under the MIT License.

import numpy as np
import math
import os
from snippets.config import AE_TARGET_LUMA

MAX_LUMA_JUMP_RATIO = 0.5
DELAY_FRAMES_COUNT = 0

class AdaptiveExposureEngine:
    def __init__(self, reg_min, reg_max, min_us, max_us, gain_db_min, gain_db_max):
        self.target = AE_TARGET_LUMA

        self.REG_MIN = reg_min
        self.REG_MAX = reg_max
        self.MIN_US = min_us
        self.MAX_US = max_us
        self.GAIN_DB_MIN = gain_db_min
        self.GAIN_DB_MAX = gain_db_max

        self.MIN_VIRT_GAIN = 1.0
        self.MAX_VIRT_GAIN = 10 ** ((self.GAIN_DB_MAX - self.GAIN_DB_MIN) / 20.0)

        self.MAX_HW_EV = (self.GAIN_DB_MAX - self.GAIN_DB_MIN) / (20.0 * math.log10(2.0))

        self.MIN_EV = math.log2((self.MIN_US * self.MIN_VIRT_GAIN / 1e6) + 1e-9)
        self.MAX_EV = math.log2((self.MAX_US * self.MAX_VIRT_GAIN / 1e6) + 1e-9)

        self.LIMIT_DN = math.log2(1.0 - MAX_LUMA_JUMP_RATIO)
        self.LIMIT_UP = math.log2(1.0 + MAX_LUMA_JUMP_RATIO)

        print("\n=== Adaptive Exposure Engine Initialized ===")
        print(f"[*] Shutter Limits (us)  : Min = {self.MIN_US}, Max = {self.MAX_US}")
        print(f"[*] Physical Gain (Reg)  : Min = {self.REG_MIN}, Max = {self.REG_MAX}")
        print(f"[*] Virtual Gain (Norm)  : Min = {self.MIN_VIRT_GAIN:.4f}, Max = {self.MAX_VIRT_GAIN:.4f}")
        print(f"[*] Dynamic MAX_HW_EV    : {self.MAX_HW_EV:.4f} EV")
        print(f"[*] Absolute EV Range    : Min = {self.MIN_EV:.4f} EV, Max = {self.MAX_EV:.4f} EV")
        print(f"[*] Step Limit (Ratio)   : {MAX_LUMA_JUMP_RATIO*100}% (Up: +{self.LIMIT_UP:.2f} EV, Dn: {-self.LIMIT_UP:.2f} EV)")
        print(f"[*] Soft Damping Range   : {self.MAX_HW_EV / 3.0:.4f} EV (1/3 of Max HW EV)")
        print("============================================\n")

    def _phys_to_virt_gain(self, reg_val):
        reg_val = np.clip(reg_val, self.REG_MIN, self.REG_MAX)
        if self.REG_MAX == self.REG_MIN: return 1.0
        reg_ratio = (reg_val - self.REG_MIN) / (self.REG_MAX - self.REG_MIN)
        db_offset = reg_ratio * (self.GAIN_DB_MAX - self.GAIN_DB_MIN)
        virt_gain = 10 ** (db_offset / 20.0)
        return np.clip(virt_gain, self.MIN_VIRT_GAIN, self.MAX_VIRT_GAIN)

    def _virt_to_phys_gain(self, virt_gain):
        virt_gain = np.clip(virt_gain, self.MIN_VIRT_GAIN, self.MAX_VIRT_GAIN)
        log_gain_ratio = math.log10(virt_gain) / ((self.GAIN_DB_MAX - self.GAIN_DB_MIN) / 20.0)
        reg = self.REG_MIN + log_gain_ratio * (self.REG_MAX - self.REG_MIN)
        return float(np.clip(reg, self.REG_MIN, self.REG_MAX))

    def _measure_luma(self, raw_path, width, height, raw_bits):
        if not os.path.exists(raw_path): return self.target
        try:
            raw_map = np.memmap(raw_path, dtype=np.uint16, mode="r", shape=(height, width))
            ds = raw_map[0::4, 0::4].astype(np.float32)
            luma = np.median(ds) / float((1 << raw_bits) - 1)
            del raw_map
            return np.clip(luma, 1e-4, 1.0)
        except: 
            return self.target

    def _compute_ev_step(self, luma):
        if luma <= self.target:
            dist = (self.target - luma) / max(self.target, 1e-9)
            return (dist ** 0.5) * self.MAX_HW_EV
        else:
            dist = (luma - self.target) / max(1.0 - self.target, 1e-9)
            return -(dist ** 0.5) * self.MAX_HW_EV

    def _update_controller(self, remaining_ev):
        is_downward = remaining_ev < 0
        step_limit = self.LIMIT_UP if not is_downward else abs(self.LIMIT_DN * 0.585)
        ratio = min(abs(remaining_ev) / self.MAX_HW_EV, 1.0)
        curve_gain = ratio ** 1.5
        soft_damping = 1.0 - math.exp(-(abs(remaining_ev) / (self.MAX_HW_EV / 3.0)) ** 1.2)
        move = remaining_ev * (step_limit / (self.MAX_HW_EV * ratio + 1e-9)) * curve_gain * soft_damping
        return move

    def _allocate_energy(self, target_ev):
        total_energy = (2.0 ** target_ev) * 1e6

        min_energy = self.MIN_US * self.MIN_VIRT_GAIN
        max_energy = self.MAX_US * self.MAX_VIRT_GAIN
        total_energy = np.clip(total_energy, min_energy, max_energy)

        if total_energy <= self.MAX_US * self.MIN_VIRT_GAIN:
            next_us = total_energy / self.MIN_VIRT_GAIN
            next_reg = self.REG_MIN
        else:
            next_us = float(self.MAX_US)
            virt_gain = total_energy / (next_us + 1e-9)
            next_reg = self._virt_to_phys_gain(virt_gain)
            
        return np.clip(next_us, self.MIN_US, self.MAX_US), next_reg

    def process_raw_frame(self, raw_path, width, height, current_us, current_reg_gain, raw_bits):
        luma = self._measure_luma(raw_path, width, height, raw_bits)
        current_virt_gain = self._phys_to_virt_gain(current_reg_gain)
        current_ev = math.log2((current_us * current_virt_gain / 1e6) + 1e-9)
        ev_step = self._compute_ev_step(luma) 
        delta = self._update_controller(ev_step)
        target_ev = np.clip(current_ev + delta, self.MIN_EV, self.MAX_EV)
        next_us, next_reg = self._allocate_energy(target_ev)

        return int(next_us), int(round(next_reg)), float(luma), float(ev_step)

_engine = None

def process_ae_logic(raw_path, width, height, current_us, current_reg_gain, max_us_limit, min_us_limit, max_reg_gain, reg_min, gain_db_min, gain_db_max, raw_bits):
    global _engine
    if _engine is None:
        _engine = AdaptiveExposureEngine(
            reg_min=reg_min, 
            reg_max=max_reg_gain, 
            min_us=min_us_limit, 
            max_us=max_us_limit, 
            gain_db_min=gain_db_min, 
            gain_db_max=gain_db_max
        )
        
    return _engine.process_raw_frame(raw_path, width, height, current_us, current_reg_gain, raw_bits)
