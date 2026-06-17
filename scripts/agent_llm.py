#!/usr/bin/env python3
"""LLM helper for agent scripts — 双通道：ask(old hermes -z fallback) + ask_direct(高效直调)"""

import subprocess, os, sys, json, time, urllib.request, urllib.error

# ===== 通道1: 原 hermes -z（保留作为 fallback） =====

def ask(prompt, max_wait=60):
    """Call LLM via hermes -z（超时不重试，其他错误重试一次）"""
    for attempt in range(2):
        try:
            r = subprocess.run(
                ["hermes", "-z", prompt, "--ignore-rules", "--ignore-user-config"],
                capture_output=True, text=True, timeout=max_wait,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if r.returncode == 0:
                return r.stdout.strip()
            if attempt == 0:
                continue
            return f"[LLM Error: {r.stderr[:200]}]"
        except subprocess.TimeoutExpired:
            return "[LLM Timeout]"
        except Exception as e:
            if attempt == 0:
                continue
            return f"[LLM Error: {str(e)[:100]}]"
    return "[LLM Error: 重试耗尽]"


# ===== 通道2: 直调 DeepSeek API（无 Hermes 载荷开销） =====

_DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
_DEEPSEEK_MODEL = "deepseek-v4-flash"

def ask_direct(prompt, system_prompt="", max_wait=60, max_tokens=16384):
    """直调 DeepSeek API，不加载 Hermes 系统提示/工具定义
    
    参数:
        prompt: 用户消息
        system_prompt: 系统提示（角色定义），空字符串时用默认
        max_wait: 超时秒数
        max_tokens: 输出最大 token 数（默认 16384，避免长方案被截断）
    返回:
        响应文本，或 [LLM Error/Timeout/NoKey] 错误串
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        # 从 .env 文件读取（Hermes 主进程也这么干）
        _env_path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), ".env")
        if os.path.exists(_env_path):
            try:
                with open(_env_path, "r") as _f:
                    for _line in _f:
                        _line = _line.strip()
                        if _line.startswith("DEEPSEEK_API_KEY="):
                            api_key = _line.split("=", 1)[1].strip()
                            break
            except Exception:
                pass
    if not api_key:
        return None  # 无 key → 调用方决定是否 fallback
    
    payload = json.dumps({
        "model": _DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "stream": False,
    }).encode("utf-8")
    
    req = urllib.request.Request(
        _DEEPSEEK_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=max_wait) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = data["choices"][0]["message"]["content"]
                return text.strip()
        except urllib.request.HTTPError as e:
            if attempt == 0:
                continue
            body = e.read().decode("utf-8", errors="replace")[:200]
            return f"[LLM Error: HTTP {e.code} - {body}]"
        except (urllib.error.URLError, OSError) as e:
            if attempt == 0:
                continue
            return f"[LLM Error: {str(e)[:100]}]"
        except (KeyError, json.JSONDecodeError) as e:
            return f"[LLM Error: parse - {str(e)[:100]}]"
        except Exception as e:
            if attempt == 0:
                continue
            return f"[LLM Error: {str(e)[:100]}]"
    return "[LLM Error: 重试耗尽]"


# ===== 通道3: 本地 Ollama（零成本，适合低复杂度任务） =====

_OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
_OLLAMA_MODEL = "qwen2.5:7b"

def ask_local(prompt, system_prompt="", max_wait=30):
    """调用本地 Ollama 模型，零 API 成本。
    适合 B 评审、简单摘要、格式化等低复杂度任务。
    不可达时返回 None，由调用方决定降级。"""
    payload = json.dumps({
        "model": _OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "max_tokens": 4096,
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            _OLLAMA_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=max_wait) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = data["choices"][0]["message"]["content"]
            return text.strip()
    except Exception as e:
        return None  # 不可达 → 调用方降级到云端


def search_tavily(query, max_results=5):
    """直调 Tavily Search API，不经过 Hermes 插件系统"""
    api_key = ""
    # 从 .env 读
    _env_path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), ".env")
    if os.path.exists(_env_path):
        try:
            with open(_env_path, "r") as _f:
                for _line in _f:
                    if _line.strip().startswith('TAVILY_API_KEY='):
                        api_key = _line.strip().split('=', 1)[1].strip()
        except Exception:
            pass
    if not api_key:
        api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return None

    payload = json.dumps({
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": "advanced",
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            "https://api.tavily.com/search",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = []
        for item in data.get("results", [])[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("content", ""),
            })
        return results
    except Exception:
        return None


def search_searxng(query, max_results=5):
    """直调 SearXNG JSON API，返回结构化结果
    
    参数:
        query: 搜索关键词
        max_results: 最大结果数
    返回:
        [{"title": str, "url": str, "description": str}, ...] 或 None（未配置/失败）
    """
    searxng_url = os.environ.get("SEARXNG_URL", "")
    if not searxng_url:
        return None  # 未配置 SearXNG
    
    import urllib.parse
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "language": "zh-CN",
        "categories": "general",
        "pageno": 1,
    })
    
    try:
        req = urllib.request.Request(f"{searxng_url}/search?{params}")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        
        results = []
        for item in data.get("results", [])[:max_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "description": item.get("content", ""),
            })
        return results
    except Exception as e:
        return None  # 失败 → 调用方决定 fallback


# ===== 搜索通道: 直调 Hermes web_search_tool（仅加载搜索插件，不进 agent 系统） =====

def hermes_web_search(query, limit=5):
    """直接调用 hermes_tools.web_search（已绕过 plugins.web 路径问题）"""
    try:
        from hermes_tools import web_search as _ws
        raw = _ws(query, limit=limit)
        if raw and raw.get("data", {}).get("web"):
            results = []
            for item in raw["data"]["web"]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": item.get("description", ""),
                })
            return results
        return None
    except Exception:
        return None


# ===== 兼容旧接口（供首次导入不报错） =====
# 原 design/review/code 函数已废弃，改为抛出建议
def design(role, task):
    raise NotImplementedError("design() 已废弃，改用 A handler 直接调 ask_direct(prompt, system_prompt=role_prompts.A)")

def review(role, design_text):
    raise NotImplementedError("review() 已废弃，改用 B handler 直接调 ask_direct(prompt, system_prompt=role_prompts.B)")

def code(role, design_text):
    raise NotImplementedError("code() 已废弃，改用 C handler 直接调 ask_direct(prompt, system_prompt=role_prompts.C)")
