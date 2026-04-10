# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import numpy as np
import math
import os
from snippets.sensors import sensor
from snippets.config import AE_TARGET_LUMA


class AdaptiveExposureEngine:
    def __init__(self, reg_min, reg_max, virt_min, virt_max):
        self.target = AE_TARGET_LUMA
        self.ev = None
        self.ev_vel = 0.0
        self.min_energy = 1e-4

        self.kf_p = 1.0
        self.base_q = 0.005
        self.q_scale = 0.1
        self.kf_r = 0.5

        self.REG_MIN = reg_min
        self.REG_MAX = reg_max
        self.VIRT_GAIN_MIN = virt_min
        self.VIRT_GAIN_MAX = virt_max

    def _phys_to_virt_gain(self, reg_val):
        return 1.0 + (reg_val - self.REG_MIN) * (self.VIRT_GAIN_MAX - self.VIRT_GAIN_MIN) / (self.REG_MAX - self.REG_MIN)

    def _virt_to_phys_gain(self, virt_gain):
        reg = self.REG_MIN + (virt_gain - self.VIRT_GAIN_MIN) * (self.REG_MAX - self.REG_MIN) / (self.VIRT_GAIN_MAX - self.VIRT_GAIN_MIN)
        return int(np.clip(reg, self.REG_MIN, self.REG_MAX))

    def process_raw_frame(self, raw_path, width, height, current_us, current_reg_gain, max_us, max_reg_gain):
        current_virt_gain = self._phys_to_virt_gain(current_reg_gain)
        if not os.path.exists(raw_path):
            self.ev_vel = 0.0
            return int(current_us), float(current_reg_gain), self.target, 0.0

        try:
            raw_map = np.memmap(raw_path, dtype=np.uint16, mode='r', shape=(height, width))
            stride = 8
            ds_raw = (raw_map[0::stride, 0::stride] >> 4).astype(np.float32)
            h, w = ds_raw.shape

            if self.ev is None:
                self.ev = math.log2(max(self.min_energy, (current_us * current_virt_gain) / 1e6) + 1e-9)

            bg = np.median(ds_raw)
            mad = np.median(np.abs(ds_raw - bg))
            noise = 1.4826 * mad

            luma = np.clip(bg / 255.0, 1e-4, 1.0)

            snr = bg / (noise + 1e-6)
            target_snr = 4.0

            snr_err = target_snr - snr

            snr_term = math.tanh(snr_err / 2.0)
            dark_term = 0.5 * math.exp(-bg / 6.0)

            luma_err = self.target - luma
            luma_term = math.tanh(luma_err * 3.0)

            err_ev = snr_term + dark_term + luma_term

            err_ev = math.tanh(err_ev * math.tanh(noise / 8.0 + 0.5))

            step = 1.2 * math.tanh(err_ev)

            dynamic_q = self.base_q + self.q_scale * (math.tanh(abs(err_ev) * 4.0) ** 4)
            ev_predict = self.ev + self.ev_vel
            p_predict = self.kf_p + dynamic_q
            k_gain = p_predict / (p_predict + self.kf_r)
            next_ev_raw = self.ev + step
            residual = next_ev_raw - ev_predict

            self.ev = ev_predict + k_gain * residual
            self.ev_vel = self.ev_vel * 0.5 + (k_gain * 0.3) * residual 
            self.kf_p = (1.0 - k_gain) * p_predict

            limit_virt_gain_max = self._phys_to_virt_gain(max_reg_gain)
            min_ev = math.log2(self.min_energy)
            max_ev = math.log2((float(max_us) * limit_virt_gain_max) / 1e6)

            if self.ev > max_ev or self.ev < min_ev:
                self.ev_vel *= 0.1

            self.ev = np.clip(self.ev, min_ev, max_ev)

            total_energy_us = (2.0 ** self.ev) * 1e6

            if total_energy_us <= max_us:
                next_us = max(1.0, total_energy_us / self.VIRT_GAIN_MIN)
                next_virt_gain = self.VIRT_GAIN_MIN
            else:
                next_us = float(max_us)
                next_virt_gain = min(limit_virt_gain_max, total_energy_us / (next_us + 1e-9))

            next_reg_gain = self._virt_to_phys_gain(next_virt_gain)

            del raw_map
            return int(next_us), float(next_reg_gain), luma, float(err_ev)

        except Exception as e:
            print(f"[AE] RAW Process Error: {e}")
            self.ev_vel = 0.0
            if 'raw_map' in locals(): del raw_map
            return int(current_us), float(current_reg_gain), self.target, 0.0

_engine = None

def process_ae_logic(raw_path, width, height, current_us, current_reg_gain, max_us_limit, max_reg_gain, reg_min):
    global _engine
    if _engine is None:
        _engine = AdaptiveExposureEngine(reg_min, max_reg_gain, 1.0, 16.0)
    return _engine.process_raw_frame(raw_path, width, height, current_us, current_reg_gain, max_us_limit, max_reg_gain)
