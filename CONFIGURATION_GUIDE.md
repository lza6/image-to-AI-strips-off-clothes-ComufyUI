# 配置指南 - 如何获取和设置各种Token

## 🔐 Telegram Bot Token 获取指南

### 方法一：通过BotFather创建（推荐）

1. **打开Telegram**，搜索并关注官方账号 `@BotFather`
2. **发送命令** `/newbot` 开始创建新机器人
3. **输入Bot名称**（用户可见的显示名称）
4. **输入用户名**（必须以bot结尾，如 `myawesomebot`）
5. **获取Token**：BotFather会回复类似这样的消息：
   ```
   Done! Congratulations on your new bot. You will find it at t.me/yourbotname. 
   You can now add a description, about section and profile picture for your bot, 
   see /help if you want to know more about formatting options.
   
   Use this token to access the HTTP API:
   8678143396:AAHfZ-zMc8hrjbAz_QAt0yMAFWsE-huRAtM
   
   Keep your token secure and store it safely, it can be used by anyone to control your bot.
   ```

### 方法二：获取现有Bot的Token

如果你已经有Bot但忘记了Token：
1. 在BotFather中发送 `/mybots`
2. 选择你要获取Token的Bot
3. 点击"API Token"选项
4. 复制显示的Token

### ⚠️ 安全提醒

- **不要泄露Token**：任何人获得你的Token都可以完全控制你的Bot
- **不要提交到公共仓库**：应该添加到 `.gitignore` 或使用环境变量
- **定期更换**：如果怀疑Token泄露，立即在BotFather中生成新的

## ⚙️ 项目配置步骤

### 1. 修改bot.py配置

找到文件中的配置区域：

```python
# ================= 配置区域 =================
BOT_TOKEN = '你的Telegram Bot Token'  # ← 在这里粘贴你的Token
COMFYUI_SERVER = "127.0.0.1:8000"    # ← ComfyUI服务地址
COMFYUI_DIR = r"D:\C"                 # ← ComfyUI安装目录
```

### 2. 环境变量方式（更安全）

创建 `.env` 文件（记得添加到 `.gitignore`）：

```env
TELEGRAM_BOT_TOKEN=你的实际Token
COMFYUI_SERVER=127.0.0.1:8000
COMFYUI_DIR=D:\\C
```

然后在代码中读取：

```python
import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
```

## 🌐 ComfyUI 配置说明

### 1. 安装ComfyUI

```bash
# 克隆仓库
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI

# 安装依赖
pip install -r requirements.txt
```

### 2. 启动ComfyUI服务

```bash
python main.py --listen 127.0.0.1 --port 8000
```

### 3. 验证服务状态

访问 `http://127.0.0.1:8000` 确认服务正常运行

## 🔧 代理配置指南

### 自动代理检测

程序会自动检测以下常见代理端口：
- **Clash**: 7890
- **V2Ray**: 10809, 10808  
- **Shadowsocks**: 1080

### 手动配置代理

如果自动检测失败，可以在代码中手动设置：

```python
# 在 auto_setup_proxy() 函数中添加自定义端口
test_ports = [7890, 10809, 10808, 1080, 4780, 你的代理端口]
```

或者直接设置：

```python
import telebot
from telebot import apihelper

# 设置HTTP代理
apihelper.proxy = {'https': 'http://127.0.0.1:你的端口号'}
```

## 📊 工作流配置 (workflow_api.json)

### 获取工作流文件

1. 在ComfyUI网页界面中设计你的AI处理流程
2. 点击"导出" → "导出API格式"
3. 将JSON内容保存为 `workflow_api.json`

### 工作流示例结构

```json
{
  "78": {
    "inputs": {
      "image": "placeholder.jpg"
    },
    "class_type": "LoadImage"
  },
  "93": {
    "inputs": {
      "megapixels": 1.0
    },
    "class_type": "ImageScaleBy"
  }
}
```

## 🔧 常见问题解决

### 1. Token验证失败

```
Error: Unauthorized
```
**解决方法**：检查Token是否正确，重新从BotFather获取

### 2. 无法连接到ComfyUI

```
ConnectionError: Failed to connect to ComfyUI
```
**解决方法**：
- 确认ComfyUI服务已启动
- 检查IP地址和端口配置
- 验证防火墙设置

### 3. 代理连接问题

```
TimeoutError: Connection timed out
```
**解决方法**：
- 检查代理软件是否运行
- 验证代理端口配置
- 尝试关闭代理直接连接

### 4. 权限不足

```
PermissionError: [Errno 13] Permission denied
```
**解决方法**：
- 以管理员身份运行程序
- 检查目录访问权限
- 确认ComfyUI目录路径正确

## 🛡️ 安全最佳实践

### 1. Token保护
```python
# ❌ 错误做法 - 直接硬编码
BOT_TOKEN = '123456789:ABCDEF...'

# ✅ 正确做法 - 使用环境变量
import os
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
```

### 2. 敏感文件保护
确保 `.gitignore` 包含：
```
.env
*.env
config.py
secrets.json
```

### 3. 定期安全检查
- 每月更换Bot Token
- 监控Bot使用情况
- 定期更新依赖包

## 📱 测试部署

### 本地测试
```bash
# 1. 启动ComfyUI
python main.py --listen 127.0.0.1 --port 8000

# 2. 启动Bot
python bot.py

# 3. 在Telegram中测试功能
```

### 生产环境部署建议
- 使用Docker容器化部署
- 配置反向代理(Nginx)
- 设置系统服务自启动
- 配置日志轮转
- 监控系统资源使用

---
*配置完成后，你的AI图像处理机器人就可以正式投入使用了！*