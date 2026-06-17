#!/usr/bin/env python3
"""
M Agent Daemon — 持久的 Hermes AIAgent。
从 loop/m_prompt.txt 读任务，用持久 AIAgent 实例处理，结果写 loop/m_response.txt。
第二次起零启动开销（AIAgent 实例常驻内存）。
"""

import os, sys, time, yaml, signal

HERMES = os.path.expandvars(r'%LOCALAPPDATA%\hermes')
AGENT_DIR = os.path.join(HERMES, "hermes-agent")
LOOP = os.path.join(HERMES, "loop")
PROMPT_FILE = os.path.join(LOOP, "m_prompt.txt")
RESPONSE_FILE = os.path.join(LOOP, "m_response.txt")
PID_FILE = os.path.join(LOOP, "m_agent.pid")
CONFIG = os.path.join(HERMES, "config.yaml")
DOT_ENV = os.path.join(HERMES, ".env")

# 只加 agent_dir 到 sys.path，不加 hermes_cli/（避免 plugins.py 文件遮蔽 plugins/ 目录）
sys.path.insert(0, AGENT_DIR)

# 清理旧 PID
if os.path.exists(PID_FILE):
    try:
        with open(PID_FILE) as f:
            old_pid = int(f.read().strip())
        os.kill(old_pid, 0)
        sys.exit(0)
    except (OSError, ValueError, ProcessLookupError):
        pass

with open(PID_FILE, "w") as f:
    f.write(str(os.getpid()))

# 读取配置
with open(CONFIG) as f:
    cfg = yaml.safe_load(f)

model_cfg = cfg.get("model", {})
provider = model_cfg.get("provider", "deepseek")
model = model_cfg.get("default", "deepseek-v4-flash")
base_url = model_cfg.get("base_url", "https://api.deepseek.com/v1")

# API key
api_key = os.environ.get("DEEPSEEK_API_KEY", "")
if not api_key and os.path.exists(DOT_ENV):
    with open(DOT_ENV) as f:
        for line in f:
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                api_key = line.split("=", 1)[1].strip()

os.environ["HERMES_INFERENCE_MODEL"] = model
os.environ["HERMES_YOLO_MODE"] = "1"
os.environ["HERMES_ACCEPT_HOOKS"] = "1"

# 创建持久 AIAgent（仅一次）
from run_agent import AIAgent

agent = AIAgent(
    api_key=api_key,
    base_url=base_url,
    provider=provider,
    model=model,
    enabled_toolsets=None,
    quiet_mode=True,
    platform="cli",
)

print(f"M Agent ready (pid={os.getpid()})", file=sys.stderr)

last_mtime = 0
running = True

def _stop(sig, frame):
    global running
    running = False

signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)

while running:
    try:
        if os.path.exists(PROMPT_FILE):
            mtime = os.path.getmtime(PROMPT_FILE)
            if mtime > last_mtime:
                with open(PROMPT_FILE, "r") as f:
                    prompt = f.read().strip()
                if prompt == "stop":
                    break
                if prompt:
                    resp = agent.chat(prompt)
                    with open(RESPONSE_FILE, "w") as f:
                        f.write(resp or "")
                last_mtime = mtime
        time.sleep(1)
    except KeyboardInterrupt:
        break
    except Exception as e:
        with open(RESPONSE_FILE, "w") as f:
            f.write(f"[M Error: {e}]")
        time.sleep(5)

if os.path.exists(PID_FILE):
    os.remove(PID_FILE)
