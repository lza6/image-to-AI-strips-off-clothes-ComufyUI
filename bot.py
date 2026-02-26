import sys
import os
import requests
import json
import time
import random
import uuid
import threading
import queue
import websocket
import telebot
import traceback
import re
import io
import glob
from datetime import datetime, timedelta
from PIL import Image
from telebot import apihelper
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ================= 系统环境补丁 =================
# 强制设置标准输出编码为 UTF-8，彻底解决 Windows 控制台 GBK 编码崩溃问题
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["TQDM_DISABLE"] = "1" 
os.environ["TERM"] = "dumb"

from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QTextEdit, QGroupBox, QGridLayout)
from PySide6.QtCore import QThread, Signal, Slot, Qt, QTimer
from PySide6.QtGui import QFont, QColor, QTextCursor

# ================= 配置区域 =================
BOT_TOKEN = '8678143396:AAHfZ-zMc8hrjbAz_QAt0yMAFWsE-huRAtM'
COMFYUI_SERVER = "127.0.0.1:8000"  
COMFYUI_DIR = r"D:\C" 
API_WORKFLOW_FILE = "workflow_api.json"
STATS_FILE = "bot_stats.json"

# 路径计算
INPUT_DIR = os.path.join(COMFYUI_DIR, "input")
OUTPUT_DIR = os.path.join(COMFYUI_DIR, "output")
for d in [INPUT_DIR, OUTPUT_DIR]:
    if not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

# 任务队列与用户锁
task_queue = [] 
queue_lock = threading.Lock()
user_active_tasks = {}  # {user_id: active_task_count}
history_map = {} 
MAX_USER_TASKS = 5  # 每个用户最多同时提交的任务数 

# ================= 智能代理检测 =================

def auto_setup_proxy():
    """自动识别常见的代理端口并配置"""
    test_ports = [7890, 10809, 10808, 1080, 4780] # Clash, V2Ray, SSR 等常用端口
    for port in test_ports:
        proxy_url = f"http://127.0.0.1:{port}"
        try:
            # 尝试通过该代理访问 Telegram API 域名
            requests.get("https://api.telegram.org", proxies={"https": proxy_url}, timeout=2)
            apihelper.proxy = {'https': proxy_url}
            return proxy_url
        except:
            continue
    return None

# ================= 核心工具函数 =================

def format_time(seconds):
    """将秒数转换为人性化的时间描述"""
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}秒"
    elif seconds < 3600:
        m = seconds // 60
        s = seconds % 60
        return f"{m}分{s}秒"
    else:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}小时{m}分"

def clean_local_outputs_recursive(target_id):
    """深度递归清理：扫描 output 文件夹下所有子目录"""
    count = 0
    try:
        for root, dirs, files in os.walk(OUTPUT_DIR):
            for f in files:
                if target_id in f:
                    file_path = os.path.join(root, f)
                    try:
                        os.remove(file_path)
                        count += 1
                    except: pass
        return count
    except: return 0

def prepare_input_image(input_path, output_path):
    with Image.open(input_path) as img:
        if img.mode != 'RGB': img = img.convert('RGB')
        img.save(output_path, format="JPEG", quality=95)

# ================= 统计管理类 =================

class StatsManager:
    def __init__(self, filename):
        self.filename = filename
        self.data = self.load_stats()

    def load_stats(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r', encoding='utf-8') as f:
                    d = json.load(f)
                    # 确保数据结构完整
                    if "daily" not in d: d["daily"] = {}
                    return d
            except: pass
        return {"daily": {}, "total_tasks": 0, "total_seconds": 0, "default_avg": 480}

    def save_stats(self):
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    def record_task(self, seconds):
        if seconds < 10: return # 过滤报错任务
        today = datetime.now().strftime("%Y-%m-%d")
        if today not in self.data["daily"]:
            self.data["daily"][today] = {"count": 0, "time": 0}
        self.data["daily"][today]["count"] += 1
        self.data["daily"][today]["time"] += seconds
        self.data["total_tasks"] += 1
        self.data["total_seconds"] += seconds
        self.save_stats()

    def get_avg_time(self):
        if self.data["total_tasks"] > 0:
            return self.data["total_seconds"] / self.data["total_tasks"]
        return self.data.get("default_avg", 480)

    def get_stats_display(self):
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        
        today_count = self.data["daily"].get(today_str, {}).get("count", 0)
        yesterday_count = self.data["daily"].get(yesterday_str, {}).get("count", 0)
        
        thirty_days_ago = now - timedelta(days=30)
        last_30_total = 0
        for date_str, info in self.data["daily"].items():
            try:
                if datetime.strptime(date_str, "%Y-%m-%d") >= thirty_days_ago:
                    last_30_total += info["count"]
            except: continue
        
        return {
            "today": today_count,
            "yesterday": yesterday_count,
            "yesterday_date": yesterday_str,
            "last_30": last_30_total,
            "avg_time": self.get_avg_time()
        }

stats_mgr = StatsManager(STATS_FILE)

# ================= 线程类 =================

class LogSignal(QThread):
    log_msg = Signal(str, str) 
    stats_refresh = Signal(dict)

class ComfyWorker(QThread):
    finished_signal = Signal(float)
    
    def __init__(self, logger_signal):
        super().__init__()
        self.logger = logger_signal
        self.bot = telebot.TeleBot(BOT_TOKEN)

    def run(self):
        self.logger.log_msg.emit("🟢 系统已就绪，正在监控任务队列...", "green")
        while True:
            task = None
            with queue_lock:
                if len(task_queue) > 0: task = task_queue.pop(0)
            
            if task:
                try:
                    self.process_task(task)
                except Exception as e:
                    self.logger.log_msg.emit(f"💥 任务处理异常: {str(e)}", "red")
                finally:
                    user_id = task.get('user_id')
                    if user_id in user_active_tasks:
                        user_active_tasks[user_id] -= 1
                        if user_active_tasks[user_id] <= 0:
                            del user_active_tasks[user_id]
                    self.logger.stats_refresh.emit(stats_mgr.get_stats_display())
            else: time.sleep(1)

    def process_task(self, task):
        chat_id, file_id, msg_id = task['chat_id'], task['file_id'], task['msg_id']
        client_id = str(uuid.uuid4())
        short_id = client_id[:8]
        proc_fn = f"tg_in_{short_id}.jpg"
        unique_tag = f"BOTID_{short_id}" 
        start_time = time.time()

        try:
            file_info = self.bot.get_file(file_id)
            downloaded_file = self.bot.download_file(file_info.file_path)
            proc_path = os.path.join(INPUT_DIR, proc_fn)
            with open(proc_path, 'wb') as f: f.write(downloaded_file)
            prepare_input_image(proc_path, proc_path)
            self.logger.log_msg.emit(f"📥 处理中: {proc_fn} (用户: {task.get('user_id')})", "cyan")

            with open(API_WORKFLOW_FILE, "r", encoding="utf-8") as f:
                workflow = json.load(f)
            
            # 适配 Qwen 节点
            if "78" in workflow: workflow["78"]["inputs"]["image"] = proc_fn
            if "93" in workflow: workflow["93"]["inputs"]["megapixels"] = 1.0
            if "117" in workflow: workflow["117"]["inputs"]["value"] = random.randint(10**14, 10**15)
            if "102" in workflow:
                if "metadata" in workflow["102"]["inputs"]: del workflow["102"]["inputs"]["metadata"]
                workflow["102"]["inputs"]["filename"] = unique_tag
                workflow["102"]["inputs"]["path"] = "bot_temp"
                workflow["102"]["inputs"]["time_format"] = ""

            ws = websocket.WebSocket()
            ws.connect(f"ws://{COMFYUI_SERVER}/ws?clientId={client_id}", timeout=10)
            p = {"prompt": workflow, "client_id": client_id}
            requests.post(f"http://{COMFYUI_SERVER}/prompt", json=p)

            output_data = None
            while True:
                out = ws.recv()
                if not out: break
                if isinstance(out, bytes): continue 
                raw = json.loads(out)
                if raw.get('type') == 'executing':
                    node = raw['data']['node']
                    if node is None: break 
                    node_title = workflow.get(node, {}).get('_meta', {}).get('title', "处理中")
                    self.logger.log_msg.emit(f"📦 正在执行: {node_title}", "purple")
                elif raw.get('type') == 'executed':
                    if 'output' in raw['data'] and 'images' in raw['data']['output']:
                        img_info = raw['data']['output']['images'][0]
                        view_url = f"http://{COMFYUI_SERVER}/view?filename={img_info['filename']}&subfolder={img_info['subfolder']}&type={img_info['type']}"
                        img_res = requests.get(view_url)
                        if img_res.status_code == 200: output_data = img_res.content
            ws.close()

            if not output_data:
                search_pattern = os.path.join(OUTPUT_DIR, "**", f"*{unique_tag}*")
                found_files = glob.glob(search_pattern, recursive=True)
                if found_files:
                    latest_file = max(found_files, key=os.path.getctime)
                    with open(latest_file, "rb") as f: output_data = f.read()

            if output_data:
                duration = time.time() - start_time
                markup = InlineKeyboardMarkup()
                markup.row(InlineKeyboardButton("🔄 重新生成", callback_data=f"regen_{short_id}"),
                           InlineKeyboardButton("📊 系统状态", callback_data="check_status"))
                self.bot.send_photo(chat_id, output_data, caption=f"✅ 生成成功!\n⏱️ 耗时: {format_time(duration)}", reply_markup=markup)
                history_map[short_id] = file_id
                try: self.bot.delete_message(chat_id, msg_id)
                except: pass
                clean_local_outputs_recursive(unique_tag)
                self.finished_signal.emit(duration)
            else:
                self.logger.log_msg.emit(f"⚠️ 未能获取到图片数据", "red")

        except Exception as e:
            self.logger.log_msg.emit(f"💥 任务异常: {str(e)}", "red")
        finally:
            if os.path.exists(os.path.join(INPUT_DIR, proc_fn)):
                try: os.remove(os.path.join(INPUT_DIR, proc_fn))
                except: pass

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ComfyUI Bot 终极交互版 (智能代理适配)")
        self.resize(1100, 850)
        self.logger = LogSignal()
        self.logger.log_msg.connect(self.append_log)
        self.logger.stats_refresh.connect(self.refresh_ui_stats)
        self.init_ui()
        
        # 立即刷新一次 UI 统计
        self.refresh_ui_stats(stats_mgr.get_stats_display())
        
        # 启动心跳定时器 (每60秒)
        self.heartbeat_timer = QTimer()
        self.heartbeat_timer.timeout.connect(self.send_heartbeat)
        self.heartbeat_timer.start(60000)
        
        self.start_threads()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        stats_group = QGroupBox("📊 运行数据实时统计")
        grid = QGridLayout()
        self.lbl_queue = self.create_stat_label("等待队列", "0", "#4fc1ff")
        self.lbl_today = self.create_stat_label("今日完成", "0", "#4ec9b0")
        self.lbl_yesterday = self.create_stat_label("昨日统计", "0", "#d4d4d4")
        self.lbl_30days = self.create_stat_label("近30天总量", "0", "#c586c0")
        self.lbl_avg_time = self.create_stat_label("平均生成耗时", "0s", "#ce9178")
        grid.addWidget(self.lbl_queue, 0, 0); grid.addWidget(self.lbl_today, 0, 1); grid.addWidget(self.lbl_yesterday, 0, 2)
        grid.addWidget(self.lbl_30days, 1, 0); grid.addWidget(self.lbl_avg_time, 1, 1)
        stats_group.setLayout(grid); main_layout.addWidget(stats_group)
        self.log_text = QTextEdit(); self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: 'Consolas';"); main_layout.addWidget(self.log_text)

    def create_stat_label(self, title, value, color):
        lbl = QLabel(f"{title}: {value}"); lbl.setFont(QFont("微软雅黑", 11, QFont.Bold))
        lbl.setStyleSheet(f"color: {color}; padding: 5px;"); return lbl

    def start_threads(self):
        self.worker = ComfyWorker(self.logger)
        self.worker.finished_signal.connect(self.on_task_done)
        self.worker.start()
        threading.Thread(target=self.run_bot_with_retry, daemon=True).start()

    def send_heartbeat(self):
        """发送心跳日志"""
        self.append_log(f"💓 系统心跳正常 | 队列: {len(task_queue)} | 内存占用正常", "gray")

    def run_bot_with_retry(self):
        # 启动前先检测代理
        self.logger.log_msg.emit("🔍 正在检测系统代理...", "gray")
        proxy = auto_setup_proxy()
        if proxy:
            self.logger.log_msg.emit(f"🌐 已自动识别代理: {proxy}", "blue")
        else:
            self.logger.log_msg.emit("ℹ️ 未检测到本地代理，将尝试直连", "gray")

        while True:
            try:
                self.run_bot_logic()
            except Exception as e:
                self.logger.log_msg.emit(f"📡 TG连接异常: {str(e)}，5秒后重试...", "red")
                time.sleep(5)

    def run_bot_logic(self):
        bot = telebot.TeleBot(BOT_TOKEN)

        def get_status_text(user_id):
            stats = stats_mgr.get_stats_display()
            pos = -1
            with queue_lock:
                for i, t in enumerate(task_queue):
                    if t['user_id'] == user_id: pos = i + 1; break
            
            # 获取用户当前活跃任务数
            current_tasks = user_active_tasks.get(user_id, 0)
            
            msg = f"📊 **系统当前状态**\n━━━━━━━━━━━━━━\n✅ 今日已完成: {stats['today']} 张\n⏱️ 平均速度: {format_time(stats['avg_time'])}/张\n👥 总排队人数: {len(task_queue)} 人\n\n"
            msg += f"👤 **您的任务状态**: {current_tasks}/{MAX_USER_TASKS} 个任务进行中\n\n"
            
            if current_tasks > 0 and pos == -1: 
                msg += f"🚀 **处理状态**: 有任务正在生成中..."
            elif pos != -1: 
                msg += f"⏳ **排队状态**: 排在第 {pos} 位\n🕒 预计还需: {format_time(pos * stats['avg_time'])}"
            else: 
                msg += f"💡 **空闲状态**: 可以继续提交新任务"
            return msg

        @bot.message_handler(commands=['start', 'status'])
        def handle_commands(m):
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📊 刷新状态", callback_data="check_status"))
            try: bot.reply_to(m, get_status_text(m.from_user.id), parse_mode="Markdown", reply_markup=markup)
            except: pass

        @bot.message_handler(content_types=['photo'])
        def handle_photo(m):
            user_id = m.from_user.id
            # 检查用户当前活跃任务数是否达到上限
            current_tasks = user_active_tasks.get(user_id, 0)
            if current_tasks >= MAX_USER_TASKS:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("📊 查看进度", callback_data="check_status"))
                try: bot.reply_to(m, f"⚠️ 您已有 {current_tasks} 个任务在处理中，最多可同时提交 {MAX_USER_TASKS} 个任务！", reply_markup=markup)
                except: pass
                return
            # 增加用户的活跃任务计数
            user_active_tasks[user_id] = current_tasks + 1
            with queue_lock:
                task_queue.append({'user_id': user_id, 'chat_id': m.chat.id, 'file_id': m.photo[-1].file_id, 'msg_id': None})
                pos = len(task_queue)
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔄 刷新排队位置", callback_data="check_status"))
            try:
                reply = bot.reply_to(m, f"📥 **任务已入队**\n🔢 当前位置: 第 **{pos}** 位\n⏳ 预计等待: ~**{format_time(pos * stats_mgr.get_avg_time())}**", reply_markup=markup)
                with queue_lock:
                    for t in task_queue:
                        if t['user_id'] == user_id: t['msg_id'] = reply.message_id
            except: pass
            self.logger.stats_refresh.emit(stats_mgr.get_stats_display())

        @bot.callback_query_handler(func=lambda call: True)
        def handle_query(call):
            user_id = call.from_user.id
            if call.data == "check_status":
                try:
                    bot.edit_message_text(get_status_text(user_id), call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=call.message.reply_markup)
                    bot.answer_callback_query(call.id, "✅ 状态已更新")
                except: pass
            elif call.data.startswith('regen_'):
                short_id = call.data.replace('regen_', '')
                original_file_id = history_map.get(short_id)
                # 检查用户当前活跃任务数是否达到上限
                current_tasks = user_active_tasks.get(user_id, 0)
                if not original_file_id or current_tasks >= MAX_USER_TASKS:
                    bot.answer_callback_query(call.id, f"⚠️ 无法重新生成：您已有 {current_tasks}/{MAX_USER_TASKS} 个任务在处理中", show_alert=True)
                    return
                # 增加用户的活跃任务计数
                user_active_tasks[user_id] = current_tasks + 1
                with queue_lock:
                    task_queue.append({'user_id': user_id, 'chat_id': call.message.chat.id, 'file_id': original_file_id, 'msg_id': None})
                    pos = len(task_queue)
                bot.send_message(call.message.chat.id, f"🔄 **重新生成任务已提交**\n🔢 当前位置: 第 {pos} 位")
                bot.answer_callback_query(call.id, "🚀 任务已入队")

        self.logger.log_msg.emit("🤖 Telegram 机器人已就绪", "blue")
        bot.polling(non_stop=True, timeout=60)

    @Slot(float)
    def on_task_done(self, duration):
        stats_mgr.record_task(duration)
        self.refresh_ui_stats(stats_mgr.get_stats_display())

    @Slot(dict)
    def refresh_ui_stats(self, data):
        self.lbl_queue.setText(f"等待队列: {len(task_queue)}")
        self.lbl_today.setText(f"今日完成: {data['today']}")
        self.lbl_yesterday.setText(f"昨日 ({data['yesterday_date']}): {data['yesterday']}")
        self.lbl_30days.setText(f"近30天总量: {data['last_30']}")
        self.lbl_avg_time.setText(f"平均生成耗时: {format_time(data['avg_time'])}")

    @Slot(str, str)
    def append_log(self, msg, color):
        color_map = {"green": "#4ec9b0", "red": "#f44747", "cyan": "#4fc1ff", "purple": "#c586c0", "blue": "#569cd6", "gray": "#808080"}
        hex_color = color_map.get(color, color)
        self.log_text.append(f'<span style="color: {hex_color};">[{datetime.now().strftime("%H:%M:%S")}] {msg}</span>')
        self.log_text.moveCursor(QTextCursor.End)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("微软雅黑", 9))
    w = MainWindow()
    w.show()
    sys.exit(app.exec())