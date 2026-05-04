<h3 align="center">
  <a href="/README.md">Back to Home</a>
</h3>

# 1. Client-side
Although it might work with any Linux device that can connect to a camera, I assume `Raspberry Pi OS` as the default environment.
<br>

The current IMX662 configuration file is `time-lapse/snippets/sensors/imx662.py`.  
**It based on the v4l2 driver from: https://github.com/raspberrypi/linux/pull/7315** 

Next, we will begin the installation.
Install the Linux kernel from the 6by9 and Alexander Pull Request; this PR contains the unmerged imx662 V4L2 driver. The process will be slow, so please be patient.
```bash
sudo rpi-update pulls/7315
```
To manually specify the camera and crystal frequency: <br>
**If your IMX662 module's frequency differs from mine, please modify the value `clock-frequency=74250000`.**
```bash
sudo grep -q "camera_auto_detect=0" /boot/firmware/config.txt || echo "camera_auto_detect=0" | sudo tee -a /boot/firmware/config.txt
sudo grep -q "dtoverlay=imx662,clock-frequency=74250000" /boot/firmware/config.txt || echo "dtoverlay=imx662,clock-frequency=74250000" | sudo tee -a /boot/firmware/config.txt
```

A reboot is required after the installation is complete.
```bash
sudo reboot
```
Then, Install dependencies:
```bash
sudo apt update
sudo apt install python3-numpy python3-opencv python3-videodev2 -y
```
Allow the service to run even when logged out:
```bash
sudo loginctl enable-linger "$USER"
```
Download and extract the code:
```bash
cd ~
mkdir -p time-lapse && curl -sL https://code.length.cc/rpi-starlapse.tar.gz | tar -xz -C time-lapse --strip-components=2 --wildcards "*/time-lapse/"
```
I use systemd to manage the software's running state and have configured the watchdog timer in the `.service` file using `WatchdogSec`.<br>
If `CAPTURE_INTERVAL` in `snippets/config.py` is over `600`, you need to set `WatchdogSec=` in `time-lapse.service` to a value greater than `600`.
<br>

Move the `.service` file to the correct location:
```bash
mkdir -p ~/.config/systemd/user/
cd ~/time-lapse
cp time-lapse.service ~/.config/systemd/user/
```

If you do not want to use a receiver, you can skip setting up config.py.<br>You only need to manually copy the .raw photos from ~/time-lapse/photo after capturing.
<br>

Edit settings in this file, including capture intervals, upload server, and more:
```bash
nano ~/time-lapse/snippets/config.py
```
If you want to use real-time uploading, you must edit at least these 2 options in `snippets/config.py`:

    DEVICE_TOKEN =
    UPLOAD_SRV_BASE =

**Please do not use the default `DEVICE_TOKEN`. You must modify it.** <br>Change `UPLOAD_SRV_BASE` to your upload server address.

If you do not have an RTC module but have a stable network connection, you can set `TIME_CHECK = True` and set `TIME_SOURCE` to any accessible website (e.g., https://google.com).<br>
This ensures the software only begins the capture process once the network is connected and time is synchronized.
<br>

Reload systemd, enable at boot, and start the program:
```bash
systemctl --user daemon-reload
systemctl --user enable time-lapse
systemctl --user restart time-lapse
```
For example, device ID `01`,<br>
After the software starts, the camera is off by default, If you want to turn the camera on or off:
```bash
touch /dev/shm/time-lapse/01/cam_switch
```
If you want to toggle Auto-Exposure on/off:
```bash
touch /dev/shm/time-lapse/01/ae_switch
```
If you want to shoot calibration frames (dark and bias):
```bash
touch /dev/shm/time-lapse/01/calibration
```
If `CAPTURE_BIAS_FRAMES` in `config.py` is set to `true`, it will shoot both dark and bias frames. If `false`, it will only shoot dark frames.  
After shooting is complete, the camera will be turned off. You need to manually change `CAMERA_ENABLED` back to `True` in `config.py` and run `systemctl --user restart time-lapse` to resume normal shooting.

To monitor logs:  
```bash
sudo journalctl _SYSTEMD_USER_UNIT=time-lapse.service -f
```

Disable auto-start at boot and stop the running service:
```bash
systemctl --user disable time-lapse
systemctl --user stop time-lapse
```

<br>
<br>
<br>

# 2. Server-side
The following examples are based on Podman and a Linux system with SELinux enabled.<br>
Of course, this is just my personal preference; you can also use Docker or disable SELinux.

For example, `/mnt/ssd_data/podman/rpi-upload-srv` is the directory where I plan to store the files.

```bash
cd ~
mkdir -p rpi-upload-srv && curl -sL https://code.length.cc/rpi-starlapse.tar.gz | tar -xz -C rpi-upload-srv --strip-components=2 "*/rpi-upload-srv"
curl -L -o rpi-upload-srv/length/RedHatMono-Regular.ttf https://assets.length.cc/fonts/RedHatMono-Regular.ttf
cd rpi-upload-srv
```
Remember to change the Volume= mapping in the three `.container` files inside `rpi-upload-srv/quadlet/*` to your actual path.
```bash
cp quadlet/* ~/.config/containers/systemd
systemctl --user daemon-reload
```

```bash
bash build.sh
```
Enter version number: `260502`

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
**Please do not use the default `device_token` You must modify it.**<br>
(If your sensor is not the IMX662, you must simultaneously change the resolution, bit depth, and verification size in the three `.ini` files within `rpi-upload-srv/conf/*`, rather than just modifying the `device_token`.")
```bash
sudo nano /mnt/ssd_data/podman/rpi-upload-srv/conf/rpi-upload-srv.ini
```
```bash
sudo nano /mnt/ssd_data/podman/rpi-upload-srv/conf/convert-tif.ini
```
```bash
sudo nano /mnt/ssd_data/podman/rpi-upload-srv/conf/time-lapse-maker.ini
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
<h3 align="center">
  <a href="/README.md">Back to Home</a>
</h3>
