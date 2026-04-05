## Preface

Raspberry Pi starry sky time-lapse photography, but it might not be limited to just the Raspberry Pi, and it might not even be limited to starry skies.

What I’m currently using is the **Raspberry Pi Zero 2W + IMX662 module with 74.25 MHz crystal oscillator + 800 nm long-pass filter + 8 mm f/1.2 M12 lens**. This exact setup runs perfectly. Other development boards and sensors can very likely be made to work too after some minor modifications.

That said, I’ve already prepared the groundwork for supporting even more sensors. You can add additional support directly in `time-lapse/snippets/sensors`. I really hope users with different hardware will also jump in and help me try writing the code.

## Explanation

Pure mono workflow — only monochrome (black-and-white) sensors are considered.

I also wrote a separate auto-exposure algorithm that bypasses the ISP and supports long exposure. It only pulls up the gain when pulling the shutter time to the upper limit still results in underexposure.

One receiver can simultaneously receive and process photos from multiple senders, categorized by device number.

The Raspberry Pi that actually captures and sends the photos acts as the **Client-side (sender)**. Any other Linux device can be used as the **Server-side (receiver)**.

On the sender side, v4l2 commands are used to grab the .raw files, which are then securely transmitted to the receiver’s server via HTTPS encryption and token authentication.

If the receiver server has unstable network or is completely unreachable, the system intelligently handles retransmissions and temporarily stores the files on disk. You can also choose to skip the receiver entirely and simply copy the files out from the SD card manually using SFTP or a card reader.

For more details, please check the code yourself.

## Usage

### Server-side

Please ensure that Podman is installed in your current environment.

For example, `/mnt/ssd_data/podman/rpi-upload-srv` is the directory where I plan to store the files.

```bash
mkdir -p rpi-upload-srv && curl -sL https://api.github.com/repos/d4c00/rpi-starlapse/tarball/main | tar -xz -C rpi-upload-srv --strip-components=2 "*/rpi-upload-srv"
cd ~/rpi-upload-srv
```
Remember to change the Volume= mapping in the three .container files inside rpi-upload-srv/quadlet/ to your actual path.
```bash
cp quadlet/* ~/.config/containers/systemd
```
```bash
curl -L -o length/vcr_osd_mono.zip "https://dl.dafont.com/dl/?f=vcr_osd_mono" && \
unzip length/vcr_osd_mono.zip -d length/ && \
rm length/vcr_osd_mono.zip
```

```bash
bash build.sh
```
Enter version number: `260405`

**Please do not use the default `device_token`. You must modify it.**  
```bash
nano /mnt/ssd_data/podman/rpi-upload-srv/rpi-upload-srv.ini
```

```bash
podman unshare chown -R 3012:3012 /mnt/ssd_data/podman/rpi-upload-srv
sudo setfacl -R -m u:"$USER":rwx /mnt/ssd_data/podman/rpi-upload-srv
sudo setfacl -R -d -m u:"$USER":rwx /mnt/ssd_data/podman/rpi-upload-srv
```

```bash
systemctl --user daemon-reload
```

The server has three modes, Start them respectively with:  

1. Receiver mode
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

Nginx configuration example:
```nginx
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    http2 on;
    server_name api.example.com;

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

### Client-side

The current IMX662 configuration file is `time-lapse/snippets/sensors/imx662.py`.  
I wrote it based on the v4l2 driver from https://github.com/will127534/imx662-v4l2-driver and set `MAX_EXPOSURE` according to the 74.25 MHz crystal oscillator frequency. You can adjust it as needed.

In the future it may be rewritten based on https://github.com/raspberrypi/linux/pull/7239 or the merged official v4l2 driver.

```bash
sudo loginctl enable-linger "$USER"
```
```bash
mkdir -p time-lapse && curl -sL https://github.com/d4c00/rpi-starlapse/tarball/main | tar -xz -C time-lapse --strip-components=2 "*/time-lapse/"
```

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

```bash
systemctl --user daemon-reload
systemctl --user enable time-lapse
systemctl --user restart time-lapse
```

If you want to shoot calibration frames (dark and bias):  
```bash
touch /dev/shm/time-lapse/calibration
```
If `CAPTURE_BIAS_FRAMES` in `config.py` is set to `true`, it will shoot both dark and bias frames. If `false`, it will only shoot dark frames.  
After shooting is complete, the camera will be turned off. You need to manually change `CAMERA_ENABLED` back to `True` in `config.py` and run `systemctl --user restart time-lapse` to resume normal shooting.

To monitor logs:  
```bash
sudo journalctl _SYSTEMD_USER_UNIT=time-lapse.service -f
```

## My Usage

Although there is no dedicated flat-field shooting option, the logic is exactly the same as bright-field shooting, so you don’t need special code to shoot flats either.  
For example, you can set `CAPTURE_BIAS_FRAMES` to `true`, shoot your flat fields first, then start shooting calibration frames. This way you get both flat/dark frames and bias frames. Flats are usually shot together with bias frames and used as a bundle.

If the exposure time is very long, you may need dark flats. In that case you can use Siril to create a master flat yourself, then put the pre-processed flat into the receiver’s `uploads/flats` folder.  
If the exposure time is short, you usually only need flats + bias frames.

In actual shooting, to save on mobile data costs, I usually disconnect from the receiver server when outdoors. After powering on, I connect to my phone hotspot just long enough for time synchronization, confirm that the camera is shooting normally and saving files without errors, then leave the device for a few hours.

When shooting is finished, I go back near the device, turn on the hotspot again so the Pi can connect, SSH in and run:  
```bash
touch /dev/shm/time-lapse/calibration
```
While the LED is flashing quickly, I cover the lens with the lens cap on-site. After a short wait, it will automatically start shooting dark frames. Except for flat-field shooting, I usually disable bias-frame shooting.

After dark frames are done, the camera will automatically turn off and the camera switch in `config.py` will also be turned off. Then I run `sudo poweroff` to shut down and head home.

Back home, I power the Pi back on, connect it to the internal network that can reach the upload server, and it will automatically start uploading all the captured .raw files. The Server-side will then generate the video and convert files to TIF. Finally I use Siril to stack them and try to create beautiful final photos.

## Frequently Asked Questions

**Q** Why is my sensor listed in the supported sensors, but it still fails to match and be used?  
**A** If you are using a third-party sensor, you need to manually specify it in `/boot/firmware/config.txt`.  
You can check what `.ko` files are available in `/usr/lib/modules/$(uname -r)/kernel/drivers/media/i2c`. If your sensor is not there, you will need to find a community open-source driver, write one yourself, or try something like `sudo rpi-update pulls/7239` (this is 6by9’s v4l2 driver PR for IMX662; at the time of writing this document, the PR was still in Draft status).

**Q** Why does it print “Camera verified READY.” in the console but then stop and not continue taking photos?  
**A** Please check whether `CAMERA_ENABLED` in `snippets/config.py` is set to `True`.  
If it is already `True` but still doesn’t work, it is likely that the camera connector is loose. Try re-inserting the FPC cable firmly and reinforcing it with tape or similar methods.

**Q** Why does the log keep printing “[CLEANUP] All zeros: {path}. Deleting.”? What’s going on?  
**A** This is still most likely caused by a loose cable or incorrect crystal oscillator frequency setting.

## License
Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)  
Licensed under the MIT License.
