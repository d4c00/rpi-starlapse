# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os
import subprocess
import fcntl
import videodev2 as v4l2
import numpy as np

SENSOR_NAME = "imx662"
WIDTH, HEIGHT = 1936, 1096
BIT = 12
V4L2_PIXELFORMAT = "RG12" 
MBUS_FORMAT = "SRGGB12_1X12"
EXP_OFFSET = 0 
INIT_SNAP_STR = "0|1000000|34|0|0"

def get_v4l2_ctrls(fd):
    ctrls = {}
    q_ctrl = v4l2.v4l2_queryctrl()
    q_ctrl.id = v4l2.V4L2_CTRL_FLAG_NEXT_CTRL

    while True:
        try:
            fcntl.ioctl(fd, v4l2.VIDIOC_QUERYCTRL, q_ctrl)
        except OSError:
            break

        if not (q_ctrl.flags & v4l2.V4L2_CTRL_FLAG_DISABLED):
            name = bytes(q_ctrl.name).split(b'\x00')[0].decode('utf-8', 'ignore').lower().replace(" ", "_")

            g_ctrl = v4l2.v4l2_control(id=q_ctrl.id)
            try:
                fcntl.ioctl(fd, v4l2.VIDIOC_G_CTRL, g_ctrl)
                val = g_ctrl.value
            except OSError:
                val = q_ctrl.default_value
            
            ctrls[name] = {
                'id': q_ctrl.id, 
                'min': q_ctrl.minimum, 
                'max': q_ctrl.maximum, 
                'val': val
            }
        
        q_ctrl.id |= v4l2.V4L2_CTRL_FLAG_NEXT_CTRL
    return ctrls

def _calculate_phys_exposure(exp_lines, container, mode="min"):
    if not hasattr(container, 'PIXEL_RATE_VAL'):
        raise RuntimeError("PIXEL_RATE_VAL not initialized. Run apply_init first.")
    
    p_rate = container.PIXEL_RATE_VAL
    ctrls = get_v4l2_ctrls(container.s_fd)

    h_blank = ctrls['horizontal_blanking'][mode] if mode in ['min', 'max'] else ctrls['horizontal_blanking']['val']
    
    # Line Time = (Width + H_Blank) / Pixel_Rate
    return (exp_lines * (WIDTH + h_blank)) / float(p_rate)

def apply_init(container):
    sub_name = os.path.basename(container.s_node)
    
    out = subprocess.check_output(f"v4l2-ctl -d {container.s_node} -C pixel_rate", shell=True, text=True)
    container.PIXEL_RATE_VAL = int(out.split(':')[-1].strip())

    with open(f"/sys/class/video4linux/{sub_name}/name", 'r') as f:
        full_entity = f.read().strip()
    
    m_node = None
    for i in range(5):
        m_p = f"/dev/media{i}"
        if os.path.exists(m_p):
            res = subprocess.getoutput(f"media-ctl -d {m_p} -p")
            if SENSOR_NAME in res:
                m_node = m_p
                break
    
    if not m_node:
        raise RuntimeError(f"Could not find media node for {SENSOR_NAME}")

    subprocess.run(f"media-ctl -d {m_node} -V '\"{full_entity}\":0 [fmt:{MBUS_FORMAT}/{WIDTH}x{HEIGHT} field:none]'", shell=True, check=True)

    fmt = v4l2.v4l2_format()
    fmt.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
    fmt.fmt.pix.width = WIDTH
    fmt.fmt.pix.height = HEIGHT
    fmt.fmt.pix.pixelformat = v4l2.v4l2_fourcc(*V4L2_PIXELFORMAT)
    fmt.fmt.pix.field = v4l2.V4L2_FIELD_NONE
    fcntl.ioctl(container.v_fd, v4l2.VIDIOC_S_FMT, fmt)

def apply_runtime(target_us, gain, container):
    if not hasattr(container, 'PIXEL_RATE_VAL'):
        return

    fd = container.s_fd
    ctrls = get_v4l2_ctrls(fd)
    
    p_rate = container.PIXEL_RATE_VAL
    h_min = ctrls['horizontal_blanking']['min']
    v_min = ctrls['vertical_blanking']['min']
    v_max = ctrls['vertical_blanking']['max']

    total_clocks = (target_us * p_rate) / 1000000.0

    v_blank = int(np.clip((total_clocks / (WIDTH + h_min)) - HEIGHT + EXP_OFFSET, v_min, v_max))

    safe_exp = int(np.clip(total_clocks / (WIDTH + h_min), 1, (HEIGHT + v_blank - EXP_OFFSET)))

    for cid, val in [
        (ctrls['horizontal_blanking']['id'], h_min),
        (ctrls['vertical_blanking']['id'], v_blank),
        (ctrls['exposure']['id'], safe_exp),
        (ctrls['analogue_gain']['id'], int(gain))
    ]:
        c = v4l2.v4l2_control(id=cid, value=int(val))
        fcntl.ioctl(fd, v4l2.VIDIOC_S_CTRL, c)