# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.

import os
import subprocess
import fcntl
import videodev2 as v4l2
import numpy as np

INIT_SNAP_STR = "0|1000000|34|0|0"
SENSOR_NAME = "imx662"
WIDTH, HEIGHT = 1936, 1096
BIT = 12
EXACT_RAW_SIZE = WIDTH * HEIGHT * 2 
V4L2_PIXELFORMAT = "RG12" 
MBUS_FORMAT = "SRGGB12_1X12"
EXP_OFFSET = 1 

def find_nodes():
    v_node, s_node = None, None
    base_v4l = "/sys/class/video4linux"
    for dev in sorted(os.listdir(base_v4l)):
        path = os.path.join(base_v4l, dev, "name")
        if os.path.exists(path):
            with open(path, 'r') as f:
                if SENSOR_NAME in f.read():
                    s_node = f"/dev/{dev}"
                    break
    for dev in sorted(os.listdir(base_v4l)):
        if dev.startswith("video"):
            u_path = os.path.join(base_v4l, dev, "device/uevent")
            if os.path.exists(u_path):
                with open(u_path, 'r') as f:
                    if "unicam" in f.read().lower():
                        v_node = f"/dev/{dev}"
                        break
    return v_node, s_node

def get_v4l2_ctrls(fd):
    ctrls = {}
    qctrl = v4l2.v4l2_queryctrl()
    qctrl.id = v4l2.V4L2_CTRL_FLAG_NEXT_CTRL
    while True:
        try:
            fcntl.ioctl(fd, v4l2.VIDIOC_QUERYCTRL, qctrl)
        except OSError:
            break
        raw_name = bytes(qctrl.name).decode('utf-8', 'ignore').strip('\x00')
        name = raw_name.lower().replace(" ", "_")
        cid = qctrl.id
        c = v4l2.v4l2_control()
        c.id = cid
        try:
            fcntl.ioctl(fd, v4l2.VIDIOC_G_CTRL, c)
            val = c.value
        except OSError:
            val = qctrl.default_value
        ctrls[name] = {'id': cid, 'min': qctrl.minimum, 'max': qctrl.maximum, 'val': val}
        qctrl.id |= v4l2.V4L2_CTRL_FLAG_NEXT_CTRL
    return ctrls

def set_v4l2_ctrl(fd, cid, value):
    c = v4l2.v4l2_control()
    c.id = cid
    c.value = int(value)
    try:
        fcntl.ioctl(fd, v4l2.VIDIOC_S_CTRL, c)
    except OSError:
        pass

def v4l2_fourcc(a, b, c, d):
    return ord(a) | (ord(b) << 8) | (ord(c) << 16) | (ord(d) << 24)

_v_n, _s_n = find_nodes()

def _calculate_phys_exposure(exp_lines, mode="min"):
    fd = os.open(_s_n, os.O_RDWR | os.O_NONBLOCK)
    ctrls = get_v4l2_ctrls(fd)
    os.close(fd)
    
    h_blank = ctrls['horizontal_blanking'][mode]
    pixel_rate = ctrls.get('pixel_rate', {}).get('val', 0)
    if not pixel_rate:
        pixel_rate = 112000000 
        
    return (exp_lines * (WIDTH + h_blank)) / float(pixel_rate)

_temp_fd = os.open(_s_n, os.O_RDWR | os.O_NONBLOCK)
_init_ctrls = get_v4l2_ctrls(_temp_fd)
os.close(_temp_fd)

MIN_EXPOSURE = _calculate_phys_exposure(_init_ctrls['exposure']['min'], mode="min")
v_total_max = HEIGHT + _init_ctrls['vertical_blanking']['max']
MAX_EXPOSURE = _calculate_phys_exposure(v_total_max, mode="max")
AE_MIN_US = int(MIN_EXPOSURE * 1e6)

def apply_init(container):
    if not container.s_node: return
    subdev_name = os.path.basename(container.s_node)
    with open(f"/sys/class/video4linux/{subdev_name}/name", 'r') as f:
        full_entity_name = f.read().strip()
    m_node = "/dev/media0"
    for i in range(5):
        if os.path.exists(f"/dev/media{i}"):
            try:
                out = subprocess.check_output(["media-ctl", "-d", f"/dev/media{i}", "-p"], text=True)
                if SENSOR_NAME in out:
                    m_node = f"/dev/media{i}"
                    break
            except: pass
    subprocess.run(["media-ctl", "-d", m_node, "-V", f"\"{full_entity_name}\":0 [fmt:{MBUS_FORMAT}/{WIDTH}x{HEIGHT} field:none]"], check=True)
    fmt = v4l2.v4l2_format()
    fmt.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
    fmt.fmt.pix.width, fmt.fmt.pix.height = WIDTH, HEIGHT
    fmt.fmt.pix.pixelformat = v4l2_fourcc(V4L2_PIXELFORMAT[0], V4L2_PIXELFORMAT[1], V4L2_PIXELFORMAT[2], V4L2_PIXELFORMAT[3])
    fmt.fmt.pix.field = v4l2.V4L2_FIELD_NONE
    fcntl.ioctl(container.v_fd, v4l2.VIDIOC_S_FMT, fmt)
    ctrls = get_v4l2_ctrls(container.s_fd)
    if 'hcg_enable' in ctrls: set_v4l2_ctrl(container.s_fd, ctrls['hcg_enable']['id'], 1)

def apply_runtime(target_us, gain, container):
    ctrls = get_v4l2_ctrls(container.s_fd)
    
    pixel_rate = ctrls.get('pixel_rate', {}).get('val', 0)
    if not pixel_rate:
        pixel_rate = 112000000

    h_min, h_max = ctrls['horizontal_blanking']['min'], ctrls['horizontal_blanking']['max']
    v_min, v_max = ctrls['vertical_blanking']['min'], ctrls['vertical_blanking']['max']
    
    total_clocks = (target_us * pixel_rate) / 1000000.0
    
    line_len_min = WIDTH + h_min
    needed_v_total = total_clocks / line_len_min
    
    if needed_v_total <= (HEIGHT + v_max):
        h_blank = h_min
        v_blank = int(np.clip(needed_v_total - HEIGHT, v_min, v_max))
    else:
        v_blank = v_max
        v_total = HEIGHT + v_blank
        h_blank = int(np.clip((total_clocks / v_total) - WIDTH, h_min, h_max))

    set_v4l2_ctrl(container.s_fd, ctrls['horizontal_blanking']['id'], h_blank)
    set_v4l2_ctrl(container.s_fd, ctrls['vertical_blanking']['id'], v_blank)

    current_line_len = WIDTH + h_blank
    exp_lines = int(np.clip(total_clocks / current_line_len if current_line_len > 0 else 1, 1, (HEIGHT + v_blank - EXP_OFFSET)))
    
    set_v4l2_ctrl(container.s_fd, ctrls['exposure']['id'], exp_lines)
    set_v4l2_ctrl(container.s_fd, ctrls['analogue_gain']['id'], int(gain))# Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)
# Licensed under the MIT License.
import os
import subprocess
import fcntl
import videodev2 as v4l2
import numpy as np

INIT_SNAP_STR = "0|1000000|34|0|0"
SENSOR_NAME = "imx662"
WIDTH, HEIGHT = 1936, 1096
BIT = 12
EXACT_RAW_SIZE = WIDTH * HEIGHT * 2 
V4L2_PIXELFORMAT = "RG12" 
MBUS_FORMAT = "SRGGB12_1X12"
EXP_OFFSET = 0 

def find_nodes():
    v_node, s_node = None, None
    base_v4l = "/sys/class/video4linux"
    for dev in sorted(os.listdir(base_v4l)):
        path = os.path.join(base_v4l, dev, "name")
        if os.path.exists(path):
            with open(path, 'r') as f:
                if SENSOR_NAME in f.read():
                    s_node = f"/dev/{dev}"
                    break
    for dev in sorted(os.listdir(base_v4l)):
        if dev.startswith("video"):
            u_path = os.path.join(base_v4l, dev, "device/uevent")
            if os.path.exists(u_path):
                with open(u_path, 'r') as f:
                    if "unicam" in f.read().lower():
                        v_node = f"/dev/{dev}"
                        break
    return v_node, s_node

def get_v4l2_ctrls(fd):
    ctrls = {}
    qctrl = v4l2.v4l2_queryctrl()
    qctrl.id = v4l2.V4L2_CTRL_FLAG_NEXT_CTRL
    while True:
        try:
            fcntl.ioctl(fd, v4l2.VIDIOC_QUERYCTRL, qctrl)
        except OSError:
            break
        raw_name = bytes(qctrl.name).decode('utf-8', 'ignore').strip('\x00')
        name = raw_name.lower().replace(" ", "_")
        cid = qctrl.id
        c = v4l2.v4l2_control()
        c.id = cid
        try:
            fcntl.ioctl(fd, v4l2.VIDIOC_G_CTRL, c)
            val = c.value
        except OSError:
            val = qctrl.default_value
        ctrls[name] = {'id': cid, 'min': qctrl.minimum, 'max': qctrl.maximum, 'val': val}
        qctrl.id |= v4l2.V4L2_CTRL_FLAG_NEXT_CTRL
    return ctrls

def set_v4l2_ctrl(fd, cid, value):
    c = v4l2.v4l2_control()
    c.id = cid
    c.value = int(value)
    fcntl.ioctl(fd, v4l2.VIDIOC_S_CTRL, c)

def v4l2_fourcc(a, b, c, d):
    return ord(a) | (ord(b) << 8) | (ord(c) << 16) | (ord(d) << 24)

_v_n, _s_n = find_nodes()

def _calculate_phys_exposure(exp_lines, mode="min"):
    fd = os.open(_s_n, os.O_RDWR | os.O_NONBLOCK)
    ctrls = get_v4l2_ctrls(fd)
    os.close(fd)
    h_blank = ctrls['horizontal_blanking'][mode]
    pixel_rate = ctrls.get('pixel_rate', {}).get('val', 0)
    if pixel_rate == 0: pixel_rate = 112000000
    return (exp_lines * (WIDTH + h_blank)) / pixel_rate

_temp_fd = os.open(_s_n, os.O_RDWR | os.O_NONBLOCK)
_init_ctrls = get_v4l2_ctrls(_temp_fd)
os.close(_temp_fd)

MIN_EXPOSURE = _calculate_phys_exposure(_init_ctrls['exposure']['min'], mode="min")
v_total_max = HEIGHT + _init_ctrls['vertical_blanking']['max']
MAX_EXPOSURE = _calculate_phys_exposure(v_total_max, mode="max")
AE_MIN_US = int(MIN_EXPOSURE * 1e6)

def apply_init(container):
    if not container.s_node: return
    subdev_name = os.path.basename(container.s_node)
    with open(f"/sys/class/video4linux/{subdev_name}/name", 'r') as f:
        full_entity_name = f.read().strip()
    m_node = "/dev/media0"
    for i in range(5):
        if os.path.exists(f"/dev/media{i}"):
            try:
                out = subprocess.check_output(["media-ctl", "-d", f"/dev/media{i}", "-p"], text=True)
                if SENSOR_NAME in out:
                    m_node = f"/dev/media{i}"
                    break
            except: pass
    subprocess.run(["media-ctl", "-d", m_node, "-V", f"\"{full_entity_name}\":0 [fmt:{MBUS_FORMAT}/{WIDTH}x{HEIGHT} field:none]"], check=True)
    subprocess.run(["media-ctl", "-d", m_node, "-V", f"\"{full_entity_name}\":0 [crop:(0,0)/{WIDTH}x{HEIGHT} ]"], check=True)
    fmt = v4l2.v4l2_format()
    fmt.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
    fmt.fmt.pix.width, fmt.fmt.pix.height = WIDTH, HEIGHT
    fmt.fmt.pix.pixelformat = v4l2_fourcc(V4L2_PIXELFORMAT[0], V4L2_PIXELFORMAT[1], V4L2_PIXELFORMAT[2], V4L2_PIXELFORMAT[3])
    fmt.fmt.pix.field = v4l2.V4L2_FIELD_NONE
    fcntl.ioctl(container.v_fd, v4l2.VIDIOC_S_FMT, fmt)
    ctrls = get_v4l2_ctrls(container.s_fd)
    if 'hcg_enable' in ctrls: set_v4l2_ctrl(container.s_fd, ctrls['hcg_enable']['id'], 1)

def apply_runtime(target_us, gain, container):
    ctrls = get_v4l2_ctrls(container.s_fd)
    pixel_rate = ctrls.get('pixel_rate', {}).get('val', 112000000)
    h_min, h_max = ctrls['horizontal_blanking']['min'], ctrls['horizontal_blanking']['max']
    v_min, v_max = ctrls['vertical_blanking']['min'], ctrls['vertical_blanking']['max']
    total_clocks_needed = (target_us * pixel_rate) / 1000000.0
    line_min = WIDTH + h_min
    v_total_at_hmin = total_clocks_needed / line_min
    if v_total_at_hmin <= (HEIGHT + v_max):
        h_blank = h_min
        v_blank = int(np.clip(v_total_at_hmin - HEIGHT + EXP_OFFSET, v_min, v_max))
    else:
        v_blank = v_max
        v_total_fixed = HEIGHT + v_blank
        line_needed = total_clocks_needed / v_total_fixed
        h_blank = int(np.clip(line_needed - WIDTH, h_min, h_max))
    current_line_length = WIDTH + h_blank
    current_v_total = HEIGHT + v_blank
    safe_exp = int(np.clip(total_clocks_needed / current_line_length, 1, current_v_total - EXP_OFFSET))
    set_v4l2_ctrl(container.s_fd, ctrls['horizontal_blanking']['id'], h_blank)
    set_v4l2_ctrl(container.s_fd, ctrls['vertical_blanking']['id'], v_blank)
    set_v4l2_ctrl(container.s_fd, ctrls['exposure']['id'], safe_exp)
    set_v4l2_ctrl(container.s_fd, ctrls['analogue_gain']['id'], int(gain))
