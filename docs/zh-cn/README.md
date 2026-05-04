## 树莓派 星空 延时摄影

<div align="center">
  <h3>
    <a href="/README.md">English</a> &nbsp; | &nbsp; <a href="/docs/zh-cn/README.md">简体中文</a>
  </h3>
</div>

* **自动长曝光**
* **多拍摄、发送端 和 自动上传后端**
* **自动星点对齐、滑动堆栈 并自动生成延时摄影视频**

<div align="center">
  <img src="https://assets.length.cc/media/2026_04_08_1.jpg" width="25%" />
  <img src="https://assets.length.cc/media/2026_04_08_2.jpg" width="25%" />
  <img src="https://assets.length.cc/media/2026_04_08_3.jpg" width="25%" />
</div>

###### 可能不仅限于树莓派，甚至不仅限于星空

Siril 中堆栈 756 张：<br>
<div align="center">
  <img src="https://assets.length.cc/media/2026_04_26.jpg" width="100%" />
</div>

接收器（服务器）模式 3 星形对齐滑动堆栈示例（视频中的单帧，每个堆栈 65 张）：<br>
<div align="center">
  <img src="https://assets.length.cc/media/20260425_212341~20260426_051319.jpg" width="100%" />
</div>

**在油管上观看：** [20260425_212341~20260426_051319.mp4](https://youtu.be/1oTHF_3T_xM)
> **星星识别:** [Astrometry](https://nova.astrometry.net/user_images/15167486) <br>

## 成本：372.47 人民币
###### 选择这种组合的原因是为了在光污染严重的城市中以低成本拍摄清晰的银河红外图像。<br>核心组件的单位成本如下：
    树莓派 Zero 2W：¥ 130.8
    IMX662 模组: ¥ 167
    800nm 长波通滤镜 + 8mm f/1.2 M12 镜头：¥ 74.67
    总计：372.47 人民币（不包括 SD 卡、移动电源、电缆、亚克力外壳和铝制散热片）
###### 以下是我的大致架构图：
    发送端（Pi）（支持通过 ID 区分多个设备：01、02……）
     ├── 捕获 (v4l2)
     ├── 缓存 (/dev/shm)
     └── 上传 (HTTPS)
     
    接收端 (Server)
     ├── 上传处理
     ├── RAW 处理
     ├── 校准
     └── 延时摄影生成

# [ 使用指南 ]

### [安装](installation.md)<br> <sup>如何从零开始设置软件和硬件</sup>

### [技术细节](technical.md)<br> <sup>传感器、逻辑电路以及我选择这些部件的原因</sup>

### [使用流程](workflow.md)<br> <sup>如何在现场使用它并处理照片</sup>

### [问题解答](faq.md)<br> <sup>常见问题的可能解决方式</sup>
<br>

###### 最后更新: 2026-05-04

###### Copyright (c) 2026 length <me@length.cc> (https://github.com/d4c00)<br>Licensed under the MIT License.<br>Font (RedHatMono-Regular.ttf): Designed by MCKL. Licensed under SIL Open Font License 1.1.
