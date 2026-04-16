# Copyright (c) 2026 length <me@length.cc>
# Licensed under the MIT License.

import os
import subprocess
import fcntl
import videodev2 as v4l2

SENSOR_NAME = "imx662"

WIDTH, HEIGHT = 1936, 1096
BIT = 12

V4L2_PIXELFORMAT = "RG12"
MBUS_FORMAT = "SRGGB12_1X12"

EXP_OFFSET = 0
INIT_SNAP_STR = "0|1000000|34|0|0"


def apply_init(self):
    sub_name = os.path.basename(self.s_node)

    out = subprocess.check_output(
        f"v4l2-ctl -d {self.s_node} -C pixel_rate",
        shell=True, text=True
    )
    self.PIXEL_RATE_VAL = int(out.split(":")[-1])

    with open(f"/sys/class/video4linux/{sub_name}/name") as f:
        entity = f.read().strip()

    m_node = next(
        (f"/dev/media{i}" for i in range(5)
         if os.path.exists(f"/dev/media{i}") and
         SENSOR_NAME in subprocess.getoutput(f"media-ctl -d /dev/media{i} -p")),
        None
    )
    if not m_node:
        raise RuntimeError(f"media node not found for {SENSOR_NAME}")

    subprocess.run(
        f"media-ctl -d {m_node} -V '\"{entity}\":0 [fmt:{MBUS_FORMAT}/{WIDTH}x{HEIGHT} field:none]'",
        shell=True, check=True
    )

    fmt = v4l2.v4l2_format()
    fmt.type = v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE
    fmt.fmt.pix.width = WIDTH
    fmt.fmt.pix.height = HEIGHT
    fmt.fmt.pix.pixelformat = v4l2.v4l2_fourcc(*V4L2_PIXELFORMAT)
    fmt.fmt.pix.field = v4l2.V4L2_FIELD_NONE
    fcntl.ioctl(self.v_fd, v4l2.VIDIOC_S_FMT, fmt)

    try:
        HCG_ID = 0x00986f20  # from v4l2-ctl
        ctrl = v4l2.v4l2_control(id=HCG_ID, value=1)
        fcntl.ioctl(self.s_fd, v4l2.VIDIOC_S_CTRL, ctrl)
    except Exception:
        pass

def apply_runtime(target_us, gain, container):
    if not hasattr(container, "PIXEL_RATE_VAL"):
        return

    ctrls = container.ctrls
    p_rate = container.PIXEL_RATE_VAL

    h = ctrls["horizontal_blanking"]["min"]
    v_min = ctrls["vertical_blanking"]["min"]
    v_max = ctrls["vertical_blanking"]["max"]

    total = (target_us * p_rate) / 1e6

    v_blank = int(max(v_min, min(v_max,
        (total / (WIDTH + h)) - HEIGHT + EXP_OFFSET
    )))

    exp = int(max(1, min(
        total / (WIDTH + h),
        HEIGHT + v_blank - EXP_OFFSET
    )))

    for name, val in [
        ("horizontal_blanking", h),
        ("vertical_blanking", v_blank),
        ("exposure", exp),
        ("analogue_gain", int(gain)),
    ]:
        container.set_ctrl(name, val)