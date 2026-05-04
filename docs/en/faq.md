## Frequently Asked Questions

**Q.** Why is my sensor listed in the supported sensors, but it still fails to match and be used?  
**A.** If you are using a third-party sensor, you need to manually specify it in /boot/firmware/config.txt and reboot.
Then, you can use the following commands to quickly determine if the sensor is working; (The following example shows how I check my IMX662; you may modify it according to your actual sensor.)
```bash
M_NODE=$(for i in /dev/media*; do media-ctl -d $i -p 2>/dev/null | grep -q "imx662" && echo $i && break; done); \
S_NODE=$(grep -l "imx662" /sys/class/video4linux/v4l-subdev*/name | head -n1 | awk -F'/' '{print "/dev/"$5}'); \
V_NODE=$(grep -l "unicam" /sys/class/video4linux/video*/device/uevent | head -n1 | awk -F'/' '{print "/dev/"$5}'); \
S_NAME=$(cat /sys/class/video4linux/$(basename $S_NODE)/name 2>/dev/null); \
\
sudo media-ctl -d $M_NODE -V "'$S_NAME':0 [fmt:SRGGB12_1X12/1936x1096 field:none]" && \
sudo media-ctl -d $M_NODE -V "'$S_NAME':0 [crop:(0,0)/1936x1096]" && \
sudo v4l2-ctl -d $V_NODE --set-fmt-video=width=1936,height=1096,pixelformat=RG12 && \
\
v4l2-ctl -d $S_NODE --set-ctrl exposure=20000,analogue_gain=100 && \
v4l2-ctl -d $V_NODE --stream-mmap --stream-count=1 --stream-to=test.raw && \
\
stat -c "Size: %s (Target: 4243712)" test.raw && \
python3 -c "import numpy as np; d=np.fromfile('test.raw', dtype='u2'); print(f'Pixels: {len(d)} | Mean: {d.mean():.1f} | Max: {d.max()} | Min: {d.min()}'); exit(0 if d.max()>0 else 1)" && \
head -c 64 test.raw | hexdump -C
```
If configured correctly, it will output something like this:
```bash
<
Size: 4259200 (Target: 4259200)
Pixels: 2129600 | Mean: 904.9 | Max: 2140 | Min: 65
00000000  d2 02 6c 02 57 02 fe 02  2c 02 ef 02 02 03 59 03  |..l.W...,.....Y.|
00000010  53 03 98 02 7f 02 a5 02  72 02 7f 03 ff 02 d5 03  |S.......r.......|
00000020  cb 02 1f 03 fd 02 ae 02  96 03 df 02 ca 02 d9 03  |................|
00000030  40 03 84 02 41 03 1f 02  a1 02 c1 02 3c 03 b7 02  |@...A.......<...|
00000040
```
To verify the image, import test.raw into ImageJ via Import > Raw using: `16-bit Unsigned`, `1936x1100`, and `Little-endian`.<br>
If it fails to work, please ask the seller for the crystal oscillator frequency of the IMX662 module, or check if the frequency is printed on the module's PCB. If it still doesn't work, please check if the MIPI interface pinout is compatible. I am not entirely sure about the feasibility, but you might be able to get it running by modifying the Device Tree files.

<br>

**Q.** Why does it print “Camera verified READY.” in the console but then stop and not continue taking photos?  
**A.** Please check whether `CAMERA_ENABLED` in `snippets/config.py` is set to `True`.  
If it is already `True` but still doesn’t work, it is likely that the camera connector is loose. Try re-inserting the FPC cable firmly and reinforcing it with tape or similar methods.

<br>

**Q.** Why does the log keep printing “[CLEANUP] All zeros: /dev/shm/time-lapse/tmp/w_01.raw.lights_tmp. Deleting.”? What’s going on?  
**A.** This is still most likely caused by a loose cable or incorrect crystal oscillator frequency setting.
