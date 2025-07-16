# 即梦绘图插件

## 说明

简易的即梦绘图插件，支持AI图片生成和文本转语音功能。可以选择比例和模型，每天领取66积分可以画66张图片。画图效果和豆包差不多，同时集成了Azure语音服务进行TTS转换。

## 功能特性

- ✅ AI图片生成（支持多种模型和比例）
- ✅ 文本转语音（TTS）和字幕生成
- ✅ 批量处理飞镜配置
- ✅ 命令行参数控制
- ✅ 数据库存储和图片管理
- ✅ 详细的日志记录

## 效果展示

![631c5d0f523c4e20628c38dffa77ca9](https://github.com/user-attachments/assets/cd1a89db-0edb-4ced-aa9d-7d4d6c085f0f)
![2328c40ececc9734259b513f52c182f](https://github.com/user-attachments/assets/731ed4f1-e4a4-4f7f-9d4c-2f7f0d5503c4)

## 环境配置

### 1. 安装依赖

```bash
# 激活虚拟环境（如果有）
conda activate jimeng

# 安装依赖
pip install azure-cognitiveservices-speech
pip install requests pillow python-dotenv
```

### 2. 配置文件

创建 `config.json` 文件：

```json
{
  "api": {
    "base_url": "https://jimeng.jianying.com",
    "aid": 513695,
    "app_version": "5.8.0",
    "request_delay": 1.0
  },
  "video_api": {
    "cookie": "your_cookie_here",
    "sign": "your_sign_here",
    "msToken": "your_msToken_here",
    "a_bogus": "your_a_bogus_here"
  },
  "params": {
    "default_model": "3.1",
    "default_ratio": "9:16",
    "models": {
      "3.1": {
        "model_req_key": "high_aes_general_v30l_art_fangzhou:general_v3.0_18b",
        "ratios": "v3_ratios"
      }
    },
    "v3_ratios": {
      "9:16": {
        "width": 576,
        "height": 1024
      },
      "16:9": {
        "width": 1024,
        "height": 576
      },
      "1:1": {
        "width": 1024,
        "height": 1024
      }
    }
  },
  "storage": {
    "retention_days": 7
  },
  "generation": {
    "max_retries": 3,
    "retry_delay": 2,
    "timeout": 30
  }
}
```

### 3. 环境变量

设置Azure语音服务（用于TTS功能）：

```bash
export SPEECH_KEY="your_azure_speech_key"
export ENDPOINT="https://your_region.api.cognitive.microsoft.com"
```

## 使用方法

### 命令行参数

```bash
python jimeng.py [选项]
```

#### 功能选项

| 选项 | 说明 |
|------|------|
| `--tts` | 执行飞镜转TTS功能 |
| `--batch` | 执行批量图片生成功能 |
| `--download` | 从数据库下载飞镜图片 |
| `--stats` | 只显示统计信息 |

#### 配置选项

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `--config` | `config.json` | 指定配置文件路径 |
| `--voice` | `zh-CN-YunzeNeural` | 指定TTS语音名称 |
| `--model` | `3.1` | 指定图片生成模型 |
| `--ratio` | `9:16` | 指定图片比例 |
| `--timeout` | `3600` | 图片生成超时时间(秒) |

### 使用示例

#### 1. 只执行TTS功能
```bash
python jimeng.py --tts
```

#### 2. 只执行批量图片生成
```bash
python jimeng.py --batch
```

#### 3. 同时执行TTS和批量生成
```bash
python jimeng.py --tts --batch
```

#### 4. 使用自定义语音
```bash
python jimeng.py --tts --voice zh-CN-XiaoxiaoNeural
```

#### 5. 使用自定义模型和比例
```bash
python jimeng.py --batch --model 2.1 --ratio 16:9
```

#### 6. 设置超时时间
```bash
python jimeng.py --batch --timeout 1800
```

#### 7. 从数据库下载图片
```bash
python jimeng.py --download
```

#### 8. 只查看统计信息
```bash
python jimeng.py --stats
```

#### 9. 默认行为（执行TTS和批量生成）
```bash
python jimeng.py
```

### 飞镜配置文件

创建 `feijing.json` 文件来配置飞镜项目：

```json
[
  {
    "编号": "分镜1",
    "提示词": "一个美丽的风景画",
    "原文": "这是分镜1的文本内容"
  },
  {
    "编号": "分镜2", 
    "提示词": "一只可爱的小猫",
    "原文": "这是分镜2的文本内容"
  }
]
```

## 支持的配置

### 语音选项

- `zh-CN-YunzeNeural` - 云泽（男声，默认）
- `zh-CN-XiaoxiaoNeural` - 晓晓（女声）
- `zh-CN-YunxiNeural` - 云希（男声）
- `zh-CN-XiaoyiNeural` - 晓伊（女声）
- `zh-CN-YunjianNeural` - 云健（男声）

### 图片模型

- `3.1` - 最新模型（默认）
- `3.0` - 稳定版本
- `2.1` - 经典版本
- `2.0` - 基础版本
- `2.0p` - 专业版本

### 图片比例

- `9:16` - 竖屏（默认）
- `16:9` - 横屏
- `1:1` - 正方形
- `4:3` - 传统比例
- `3:4` - 竖屏传统比例

## 输出文件

### TTS输出
- 音频文件：`./downloads/{编号}.mp3`
- 字幕文件：`./downloads/{编号}.srt`

### 图片生成输出
- 图片文件：`./downloads/{编号}_0.jpeg`, `./downloads/{编号}_1.jpeg` 等

## 项目结构

```
jimeng/
├── jimeng.py              # 主程序文件
├── config.json            # 配置文件
├── feijing.json           # 飞镜配置文件
├── module/                # 模块目录
│   ├── __init__.py
│   ├── api_client.py      # API客户端
│   ├── audio_processor.py # 音频处理器
│   ├── image_processor.py # 图片处理器
│   ├── image_storage.py   # 图片存储
│   ├── submaker.py        # 字幕生成器
│   └── token_manager.py   # Token管理器
├── storage/               # 存储目录
├── downloads/             # 下载目录
├── logs/                  # 日志目录
└── temp/                  # 临时目录
```

## 注意事项

1. **积分限制**：每天领取66积分可以画66张图片
2. **网络连接**：确保能够访问即梦API和Azure语音服务
3. **磁盘空间**：确保有足够的磁盘空间存储生成的文件
4. **权限**：确保有写入文件的权限
5. **配额限制**：注意Azure语音服务的配额限制

## 更新计划

1. 增加上传图片参考图生成视频，可以选择模型和比例
2. 修复生图提取模型和比例有错误问题
3. 优化批量处理性能
4. 添加更多语音选项
5. 支持更多图片格式

## 帮助信息

查看完整的帮助信息：
```bash
python jimeng.py --help
```

## 许可证

本项目仅供学习和研究使用。