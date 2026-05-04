<h3 align="center">
  <a href="README.md">回到主页</a>
</h3>

# 1. 客户端
###### （用于拍照，上传照片）
可能适用于任何可以连接摄像头的 Linux 设备，但我假设默认环境为 `Raspberry Pi OS`
<br>

当前的 IMX662 配置文件是 `time-lapse/snippets/sensors/imx662.py`（理论上其他摄像头参考这个文件编写配置文件，成功运行应该不难），
**我使用的 IMX662 的 v4l2 驱动来自于未合并的 PR：https://github.com/raspberrypi/linux/pull/7315** 

说明结束，接下来开始安装
请安装来自 6by9 和 Alexander Pull Request 的 Linux 内核；此 PR 包含尚未合并的 imx662 V4L2 驱动程序。安装过程会比较慢，请耐心等待
```bash
sudo rpi-update pulls/7315
```
手动指定摄像头和晶振频率： <br>
**如果您的 IMX662 模块频率与我的不同，请修改 `clock-frequency=74250000` 的数值**
```bash
sudo grep -q "camera_auto_detect=0" /boot/firmware/config.txt || echo "camera_auto_detect=0" | sudo tee -a /boot/firmware/config.txt
sudo grep -q "dtoverlay=imx662,clock-frequency=74250000" /boot/firmware/config.txt || echo "dtoverlay=imx662,clock-frequency=74250000" | sudo tee -a /boot/firmware/config.txt
```

安装完成后需要重启
```bash
sudo reboot
```
然后，安装依赖：
```bash
sudo apt update
sudo apt install python3-numpy python3-opencv python3-videodev2 -y
```
允许服务在用户注销后运行：
```bash
sudo loginctl enable-linger "$USER"
```
下载并解压代码：
```bash
cd ~
mkdir -p time-lapse && curl -sL https://code.length.cc/rpi-starlapse.tar.gz | tar -xz -C time-lapse --strip-components=2 --wildcards "*/time-lapse/"
```
我使用 systemd 管理软件的运行状态，并在 `.service` 文件中使用 `WatchdogSec` 配置了看门狗定时器，<br>
如果 `snippets/config.py` 中的 `CAPTURE_INTERVAL` 大于 `600`，则需要在 `time-lapse.service` 中将 `WatchdogSec=` 设置为大于 `600` 的值
<br>

将 `.service` 文件移动到正确的位置：
```bash
mkdir -p ~/.config/systemd/user/
cd ~/time-lapse
cp time-lapse.service ~/.config/systemd/user/
```

如果您不想使用接收器，可以跳过设置 `config.py`。<br>拍摄完成后，您只需手动从 `~/time-lapse/photo` 复制 `.​​raw` 照片即可。
<br>

编辑此文件中的设置，包括捕获间隔、上传服务器等：
```bash
nano ~/time-lapse/snippets/config.py
```
如果要使用实时上传功能，则必须至少编辑 `snippets/config.py` 文件中的以下两个选项：

    DEVICE_TOKEN =
    UPLOAD_SRV_BASE =

**请勿使用默认的 `DEVICE_TOKEN`。您必须对其进行修改。** <br>将 `UPLOAD_SRV_BASE` 更改为您的上传服务器地址<br>
如果您没有时钟模块 (RTC) 但网络连接稳定，您可以将 `TIME_CHECK = True` 设置为真，并将 `TIME_SOURCE` 设置为任何可访问的网站（例如 https://baidu.com ）<br>
这样可以确保软件仅在网络连接建立且时间同步后才开始捕获过程。
<br>

重载 systemd 读取新的配置文件，启用开机启动，然后启动程序：
```bash
systemctl --user daemon-reload
systemctl --user enable time-lapse
systemctl --user restart time-lapse
```
例如，默认是设备 ID `01`（如果你有多设备，可以更改设备 ID）<br>
软件启动后，相机默认处于关闭状态。如需开启或关闭相机，请执行以下操作：
```bash
touch /dev/shm/time-lapse/01/cam_switch
```
如需 开启/关闭 自动曝光，请执行以下操作：
```bash
touch /dev/shm/time-lapse/01/ae_switch
```
如需拍摄校准帧（暗场和偏置帧），请执行以下操作：
```bash
touch /dev/shm/time-lapse/01/calibration
```
如果 `config.py` 中的 `CAPTURE_BIAS_FRAMES` 设置为 `true`，则会拍摄暗场和偏置帧。如果设置为 `false`，则只会拍摄暗场。<br>
拍摄完成后，相机将自动关闭。您需要在 `config.py` 中手动将 `CAMERA_ENABLED` 改回 `True`，然后运行 ​​`systemctl --user restart time-lapse` 以恢复正常拍摄。

要查看日志： 
```bash
sudo journalctl _SYSTEMD_USER_UNIT=time-lapse.service -f
```

禁用开机自动启动并停止正在运行的服务：
```bash
systemctl --user disable time-lapse
systemctl --user stop time-lapse
```

<br>
<br>
<br>

# 2. 服务端
###### （用于接收照片、处理照片、输出延时视频）
以下示例基于 Podman 和启用了 SELinux 的 Linux 系统；<br>
当然，这只是我的个人偏好；您也可以使用 Docker 或禁用 SELinux

例如，`/mnt/ssd_data/podman/rpi-upload-srv` 是我使用的目录，请根据你的目录情况更改命令
```bash
cd ~
mkdir -p rpi-upload-srv && curl -sL https://code.length.cc/rpi-starlapse.tar.gz | tar -xz -C rpi-upload-srv --strip-components=2 "*/rpi-upload-srv"
curl -L -o rpi-upload-srv/length/RedHatMono-Regular.ttf https://assets.length.cc/fonts/RedHatMono-Regular.ttf
cd rpi-upload-srv
```
请记住将 `rpi-upload-srv/quadlet/*` 中的三个 `.container` 文件中的 Volume= 映射更改为您的实际路径
```bash
cp quadlet/* ~/.config/containers/systemd
systemctl --user daemon-reload
```

```bash
bash build.sh
```
Enter version number: `260502`

因为我启用了 SELinux，所以我需要：（没开的话只需要运行第一行 和 `sudo chown -R 3012:3012 /mnt/ssd_data/podman/rpi-upload-srv`）
```bash
mkdir -p /mnt/ssd_data/podman/rpi-upload-srv/{conf,fonts,output,uploads}
podman unshare chown -R 3012:3012 /mnt/ssd_data/podman/rpi-upload-srv
sudo setfacl -R -m u:"$USER":rwx /mnt/ssd_data/podman/rpi-upload-srv
sudo setfacl -R -d -m u:"$USER":rwx /mnt/ssd_data/podman/rpi-upload-srv
```

您需要启动一次，将配置文件复制到指定目录
```bash
systemctl --user restart rpi-upload-srv-2
```
**请勿使用默认的 `device_token`，您必须对其进行修改。**<br>
（如果您的传感器不是 IMX662，则必须同时修改 `rpi-upload-srv/conf/*` 目录下的三个 `.ini` 文件中的分辨率、位深度和验证大小，而不仅仅是修改 `device_token`。）
```bash
sudo nano /mnt/ssd_data/podman/rpi-upload-srv/conf/rpi-upload-srv.ini
```
```bash
sudo nano /mnt/ssd_data/podman/rpi-upload-srv/conf/convert-tif.ini
```
```bash
sudo nano /mnt/ssd_data/podman/rpi-upload-srv/conf/time-lapse-maker.ini
```

现在已准备就绪，可以使用了。
服务器有三种模式，请分别使用以下命令启动： 
1. 接收器模式（通过 systemd 在启动时自动启动）
```bash
systemctl --user restart rpi-upload-srv-1
```

2. 将 .raw 文件打包成 JPG 和 TIF 文件
```bash
systemctl --user restart rpi-upload-srv-2
```

3. 生成延时视频（支持各种校准场校准）
```bash
systemctl --user restart rpi-upload-srv-3
```

**如果要在公共互联网上运行，请尽可能使用 Nginx 或其他反向代理来添加 TLS 加密层。**<br>
Nginx 配置示例：
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
  <a href="README.md">回到主页</a>
</h3>