### Raspberry Pi starry sky time-lapse photography, but it might not be limited to just the Raspberry Pi, and it might not even be limited to starry skies.

<div align="center">
  <img src="https://github.com/user-attachments/assets/768b157d-196d-4502-bacf-9d13b6f02a91" width="25%" />
  <img src="https://github.com/user-attachments/assets/0ea92a9c-518a-48d5-9285-62515a5b2186" width="25%" />
  <img src="https://github.com/user-attachments/assets/636584fc-1f80-4664-965f-35e0f479bc7c" width="25%" />
</div>

##### The CAD drawing for the acrylic enclosure shown in the examples can be found at: [PMMA_3mm_BLK_Opaque_Matte_260408.dwg](https://github.com/d4c00/rpi-starlapse/raw/refs/heads/main/CAD/PMMA_3mm_BLK_Opaque_Matte_260408.dwg)

---
<br>

### Examples:
Bortle Class 8 city, exposure time 29.85 seconds, gain 34, Milky Way core captured during a no-moon window. There were many clouds, so I could only select 12 frames where the clouds were relatively thin for stacking.
<div align="center">
  <img src="https://github.com/user-attachments/assets/2bd2f249-cacb-420a-9651-b76b8fc18d34" width="77%" />
</div>

> **Video:** [Watch the Full Time-lapse on YouTube](https://youtu.be/KsnQ170sJx0) <br>
> **Star Field Identification:** [Astrometry Results](https://nova.astrometry.net/user_images/15042173)
<br>

### Examples of particularly harsh environments:
In a **Bortle 8** city, I captured a section of the Milky Way between Aquila and Lyra. Even with the interference of **56.8% moonlight** at an angular distance of **18°** from the target and **partly cloudy** skies, and using a ordinary power bank (which introduces significant readout noise), it still managed to capture a number of stars.<br>
The image shows the Milky Way faintly visible under moonlight (with lunar glare in the bottom-left).<br>
Exposure time: 29, gain: 34.<br>
Stacked 64 light frames along with flat frames and dark flats (no dark frames).<br>
<div align="center">
  <img src="https://github.com/user-attachments/assets/36020c35-77c3-42ef-b876-6872854ba693" width="77%" />
</div>

> **Video:** [Watch the Full Time-lapse on YouTube](https://www.youtube.com/watch?v=GwNxKLBiHG8) <br>
> **Star Field Identification:** [Astrometry Results](https://nova.astrometry.net/user_images/15025237)
<br>

---

## Preface

The reason for choosing this combination is to capture clear infrared Milky Way images in light-polluted cities at a low cost.

###### Unit costs for the core components are as follows:
    Raspberry Pi Zero 2W: $18.98
    IMX662 Module: $24.50
    800nm Long-pass Filter + 8mm f/1.2 M12 Lens: $10.89
    Total: $54.37 (excluding SD card, power bank, cables, acrylic enclosure, and aluminum heatsinks).
###### Below is my approximate architecture:
    Sender (Pi) (Supports multiple devices via IDs: 01, 02...)
     ├── capture (v4l2)
     ├── buffer (/dev/shm)
     └── upload (HTTPS)
     
    Receiver (Server)
     ├── upload handler
     ├── RAW processing
     ├── calibration
     └── timelapse rendering
     
<br>
The Zero 2W was selected because it is compact and power-efficient; its performance is modest but sufficient for the task.

I chose the IMX662 because STARVIS 2 offers high QE (Quantum Efficiency) in the infrared spectrum while remaining affordable. However, the 74.25 MHz crystal oscillator I’m using might not be ideal for long exposures; a module with a 24 MHz oscillator—the lowest supported by the IMX662—might be more suitable.

By pairing it with an 800nm long-pass filter, the color sensor can function like a mono sensor (though faint Bayer patterns remain), achieving the same sharpness and clarity as a true mono sensor. The filter is an 8.5mm diameter interference filter attached to the back of the M12 lens (facing the sensor). The filter and lens were pre-assembled by the seller.

<br>

---

### **Call for Hardware Compatibility & Contributions**

Theoretically, as long as you are using a Linux-based device with a camera connected via the **MIPI interface** and controlled by **V4L2 drivers**, your hardware should be compatible. By referring to the file `rpi-starlapse/time-lapse/snippets/sensors/imx662.py` and filling in the **V4L2 control mappings** specific to your sensor's driver, it can be made to work. Other brands of Pi-like development boards may also be compatible.

I do not have additional hardware for testing, but I have done my best to ensure system generality. I would be very happy to receive feedback from users with different hardware.

If you can write a sensor configuration file for hardware different from mine and run it successfully, I would be extremely grateful if you could create a PR to help me support more sensors.

If you have any questions, you are more than welcome to contact me at any time.
<br>
<br>

---

## Explanation

Pure mono workflow — only monochrome (black-and-white) sensors are considered.
<br>
<br>
I also wrote a separate auto-exposure algorithm that bypasses the ISP and supports long exposure. It only pulls up the gain when pulling the shutter time to the upper limit still results in underexposure.
<br>
<br>
One receiver can simultaneously receive and process photos from multiple senders, categorized by device number.<br>
The Raspberry Pi that actually captures and sends the photos acts as the **Client-side (sender)**. Any other Linux device can be used as the **Server-side (receiver)**.<br>
Although it might work with any Linux device that can connect to a camera, I separated it into sender and receiver mainly because my Raspberry Pi Zero2w has poor performance.
<br>
<br>
On the sender side, v4l2 commands are used to grab the .raw files, which are then securely transmitted to the receiver’s server via HTTPS encryption and token authentication.
If the receiver server has unstable network or is completely unreachable, the system intelligently handles retransmissions and temporarily stores the files on disk. You can also choose to skip the receiver entirely and simply copy the files out from the SD card manually using SFTP or a card reader.
<br>
<br>
<br>
For more details, please check the code yourself.

---
<br>

# >> Usage << 
<br>

## 1. Client-side

The current IMX662 configuration file is `time-lapse/snippets/sensors/imx662.py`.  
**It based on the v4l2 driver from: https://github.com/raspberrypi/linux/pull/7239** 

Next, we will begin the installation.
Install the Linux kernel from the 6by9 Pull Request; this PR contains the unmerged imx662 V4L2 driver. The process will be slow, so please be patient.
```bash
sudo rpi-update pulls/7239
```
To manually specify the camera and crystal frequency, and enable HCG: <br>
**If your IMX662 module's frequency differs from mine, please modify the value `clock-frequency=74250000`.** HCG mode is optional.
```bash
sudo grep -q "camera_auto_detect=0" /boot/firmware/config.txt || echo "camera_auto_detect=0" | sudo tee -a /boot/firmware/config.txt
sudo grep -q "dtoverlay=imx662,clock-frequency=74250000" /boot/firmware/config.txt || echo "dtoverlay=imx662,clock-frequency=74250000" | sudo tee -a /boot/firmware/config.txt
grep -q "imx662.hcg_mode" /boot/firmware/cmdline.txt || sudo sed -i '$s/$/ imx662.hcg_mode=1/' /boot/firmware/cmdline.txt
```

A reboot is required after the installation is complete.
```bash
sudo root
```
Then:
```bash
sudo loginctl enable-linger "$USER"
```

```bash
mkdir -p time-lapse && curl -sL https://github.com/d4c00/rpi-starlapse/tarball/main | tar -xz -C time-lapse --strip-components=2 --wildcards "*/time-lapse/"
```

If your shooting interval is greater than 10 minutes, you need to modify the `WatchdogSec=600` parameter in `time-lapse.service`.
```bash
mkdir -p ~/.config/systemd/user/
cd ~/time-lapse
cp time-lapse.service ~/.config/systemd/user/
```

**Please do not use the default `DEVICE_TOKEN`. You must modify it.**  
```bash
nano ~/time-lapse/snippets/config.py
```
Change `UPLOAD_SRV_BASE` to your upload server address.  
`TIME_SOURCE` can be set to any website that can be reached; it is only used to check whether the internet is connected (because adding an RTC module to the Raspberry Pi Zero 2W is very inconvenient). This is to confirm that NTP time synchronization has completed before naming the files.

```bash
sudo apt update
sudo apt install python3-numpy python3-opencv -y
```
Auto-start at boot via systemd
```bash
systemctl --user daemon-reload
systemctl --user enable time-lapse
systemctl --user restart time-lapse
```

If you want to shoot calibration frames (dark and bias):  
```bash
# For example, device ID 01
touch /dev/shm/time-lapse/01/calibration
```
If `CAPTURE_BIAS_FRAMES` in `config.py` is set to `true`, it will shoot both dark and bias frames. If `false`, it will only shoot dark frames.  
After shooting is complete, the camera will be turned off. You need to manually change `CAMERA_ENABLED` back to `True` in `config.py` and run `systemctl --user restart time-lapse` to resume normal shooting.

To monitor logs:  
```bash
sudo journalctl _SYSTEMD_USER_UNIT=time-lapse.service -f
```
<br>

## 2. Server-side
Please ensure that Podman is installed in your current environment.

For example, `/mnt/ssd_data/podman/rpi-upload-srv` is the directory where I plan to store the files.

```bash
mkdir -p rpi-upload-srv && curl -sL https://api.github.com/repos/d4c00/rpi-starlapse/tarball/main | tar -xz -C rpi-upload-srv --strip-components=2 "*/rpi-upload-srv"
cd ~/rpi-upload-srv
```
Remember to change the Volume= mapping in the three `.container` files inside `rpi-upload-srv/quadlet/*` to your actual path.
```bash
cp quadlet/* ~/.config/containers/systemd
systemctl --user daemon-reload
```
```bash
curl -L -o length/vcr_osd_mono.zip "https://dl.dafont.com/dl/?f=vcr_osd_mono" && \
unzip length/vcr_osd_mono.zip -d length/ && \
rm length/vcr_osd_mono.zip
```

```bash
bash build.sh
```
Enter version number: `260410`

I have enabled SELinux, so I need to:
```bash
mkdir -p /mnt/ssd_data/podman/rpi-upload-srv/{conf,fonts,output,uploads}
podman unshare chown -R 3012:3012 /mnt/ssd_data/podman/rpi-upload-srv
sudo setfacl -R -m u:"$USER":rwx /mnt/ssd_data/podman/rpi-upload-srv
sudo setfacl -R -d -m u:"$USER":rwx /mnt/ssd_data/podman/rpi-upload-srv
```
You need to start it once to copy the configuration files to the specified directory.
```bash
systemctl --user restart rpi-upload-srv-2
```
**Please do not use the default `device_token`. You must modify it.**  (If your sensor is not the IMX662, you must simultaneously change the resolution, bit depth, and verification size in the three `.ini` files within `rpi-upload-srv/conf/*`, rather than just modifying the `device_token`.")
```bash
sudo nano /mnt/ssd_data/podman/rpi-upload-srv/conf/rpi-upload-srv.ini
```

It is now ready for use.
The server has three modes, Start them respectively with:  

1. Receiver mode (Auto-start at boot via systemd)
```bash
systemctl --user restart rpi-upload-srv-1
```

2. Package .raw files into JPG and TIF files 
```bash
systemctl --user restart rpi-upload-srv-2
```

3. Generate time-lapse video (with flat-field calibration support)
```bash
systemctl --user restart rpi-upload-srv-3
```

**If this is to be run on the public internet, please use Nginx or another reverse proxy to add a layer of TLS encryption whenever possible.**<br>
Nginx configuration example:
```nginx
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name rpi-upload-srv.example.com;

    ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;
    
    ssl_protocols TLSv1.3;
    ssl_prefer_server_ciphers off;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;

    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;

    location / {
        proxy_pass http://127.0.0.1:3012;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        client_max_body_size 5M;
        proxy_request_buffering on;
        proxy_buffering off;

        proxy_intercept_errors on;
    }
}
```
<br>
<br>


## My Usage

Although there is no dedicated flat-field shooting option, the logic is exactly the same as bright-field shooting, so you don’t need special code to shoot flats either.  
For example, you can set `CAPTURE_BIAS_FRAMES` to `true`, shoot your flat fields first, then start shooting calibration frames. This way you get both flat/dark frames and bias frames. Flats are usually shot together with bias frames and used as a bundle.
<br>
<br>
<br>
For a single sender, the receiver will create a directory named after the device number, such as "01". In the example I'm using, the path `/mnt/ssd_data/podman/rpi-upload-srv/uploads/01` can support four folders, like this:

```
rpi-upload-srv
├── conf
│   ├── convert-tif.ini
│   ├── rpi-upload-srv.ini
│   └── time-lapse-maker.ini
├── fonts
├── output
└── uploads
    └── 01
        ├── biases  <<
        ├── darks   <<
        ├── flats   <<
        └── lights  <<
```

The `lights` folder contains the light frames (the actual images). The `darks`, `flats`, and `biases` are calibration frames. Only **mode 3** of rpi-upload-srv will use the calibration frames (alternatively, you can run `rpi-upload-srv-2` to convert them to TIF and then manually import them into Siril for stacking).

Only the `lights` folder is mandatory. The other three folders are optional — the video can still be generated even if they are missing.

If the exposure time for your flat frames is very short, you usually only need flats + bias frames.  
If the exposure time for your flat frames is very long, you may need dark flats. In that case, you can put the captured dark flats into the `biases` folder and use them as bias frames.

Running `rpi-upload-srv-3` will calibrate each light frame image, overlay the photo information in the top-left corner, and then stitch everything together into a final video.
<br>
<br>
<br>
In actual shooting, to save on mobile data costs, I usually disconnect from the receiver server when outdoors. After powering on, I connect to my phone hotspot just long enough for time synchronization, confirm that the camera is shooting normally and saving files without errors, then leave the device for a few hours.

When shooting is finished, I go back near the device, turn on the hotspot again so the Pi can connect, SSH in and run.
```bash
touch /dev/shm/time-lapse/calibration
```
While the LED is flashing quickly, I cover the lens with the lens cap on-site. After a short wait, it will automatically start shooting dark frames. Except for flat-field shooting, I usually disable bias-frame shooting.

After dark frames are done, the camera will automatically turn off and the camera switch in `config.py` will also be turned off. Then I run `sudo poweroff` to shut down and head home.

Back home, I power the Pi back on, connect it to the internal network that can reach the upload server, and it will automatically start uploading all the captured .raw files. The Server-side will then generate the video and convert files to TIF. Finally I use Siril to stack them and try to create beautiful final photos.

By the way, there was also a time when I went to collect [it] after shooting, only to find that as soon as I started shooting the starry sky, it was covered by thick clouds. Then I directly **took** several hundred frames of ten-plus-second long-exposure clouds **from the shot ones** as flats and put them into the flats folder.
At the same time, I triggered the calibration frame shooting; after covering the lens cap to shoot darks, I put the shot darks into the biases folder.
<br>

---

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
sudo media-ctl -d $M_NODE -V "'$S_NAME':0 [fmt:SRGGB12_1X12/1936x1100 field:none]" && \
sudo media-ctl -d $M_NODE -V "'$S_NAME':0 [crop:(0,0)/1936x1100]" && \
sudo v4l2-ctl -d $V_NODE --set-fmt-video=width=1936,height=1100,pixelformat=RG12 && \
\
v4l2-ctl -d $S_NODE --set-ctrl exposure=20000,analogue_gain=500 && \
v4l2-ctl -d $V_NODE --stream-mmap --stream-count=1 --stream-to=test.raw && \
\
stat -c "Size: %s (Target: 4259200)" test.raw && \
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

---
<br>

###### Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00) <br>
###### Licensed under the MIT License.
