#!/usr/bin/env python3
"""
Coordinator — 自迭代调度器
职责缩小到三件事：A-B 循环、D 报告、E 评估。
A/B/M 都用 ask()/ask_direct 调用，M 自己有完整工具链，自己读文件、自己 patch。
"""

import os, sys, time, json

HERMES = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOOP   = os.path.join(HERMES, "loop")
OUTPUT = os.path.join(LOOP, "output")
SCRIPTS = os.path.join(HERMES, "scripts")
M_HISTORY = os.path.join(HERMES, "loop", "m_history.json")
M_NOTEBOOK = os.path.join(HERMES, "loop", "m_notebook.md")
LIVE_FILE = os.path.join(LOOP, "d_live.md")
os.makedirs(OUTPUT, exist_ok=True)

sys.path.insert(0, SCRIPTS)
from agent_llm import ask_direct, ask, ask_local, search_tavily, search_searxng, hermes_web_search
from role_prompts import A as ROLE_A, B as ROLE_B


# ── M 修改历史 ──

class MHistory:
    def __init__(self):
        if os.path.exists(M_HISTORY):
            try:
                with open(M_HISTORY) as f:
                    self.records = json.load(f)
            except:
                self.records = []
        else:
            self.records = []

    def record(self, entry):
        entry["ts"] = time.time()
        self.records.append(entry)
        with open(M_HISTORY, "w") as f:
            json.dump(self.records[-50:], f, ensure_ascii=False, indent=2)

    def evaluate(self, m):
        if len(self.records) < 2: return "first_run"
        last = None
        for r in reversed(self.records[:-1]):
            if "outcome" in r:
                last = r; break
        if not last: return "first_run"
        lm = last.get("result", {})
        if not lm: return "first_run"
        sc = (100 if m.get("verdict")=="PASS" else 0) - m.get("rounds",3)*10 - m.get("elapsed",300)/10
        sl = (100 if lm.get("verdict")=="PASS" else 0) - lm.get("rounds",3)*10 - lm.get("elapsed",300)/10
        return "improved" if sc > sl else ("worse" if sc < sl else "no_change")

    def trend(self):
        """近5次趋势分析"""
        recent = [r for r in self.records[-5:] if "result" in r]
        if len(recent) < 2:
            return ""
        outcomes = []
        for i, r in enumerate(recent):
            res = r.get("result", {})
            outcomes.append(res.get("verdict") == "PASS")
        pass_n = sum(outcomes)
        pass_rate = round(pass_n / len(outcomes) * 100)
        # 连续worse检测
        worse_count = 0
        for r in reversed(recent):
            if r.get("outcome") == "worse":
                worse_count += 1
            else:
                break
        trend_str = f"E近5: {pass_rate}%PASS"
        if worse_count >= 2:
            trend_str += f" ⚠️ 连续{worse_count}次worse"
        elif pass_rate >= 80:
            trend_str += " ✅ 稳定"
        return trend_str


# ── D 报告 ──

class D:
    def __init__(self, task):
        self.task = task
        self.t0 = time.time()
        with open(LIVE_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n\n## 📋 新任务 {time.strftime('%H:%M:%S')}\n**{task[:150].strip()}**\n\n")

    def log(self, icon, text):
        t = time.time() - self.t0
        line = f"  `+{t:5.1f}s` {icon} {text}"
        with open(LIVE_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        print(line)


# ── d_live 清理 ──

def clean_dlive():
    """保留最新10条任务记录，删除更早的。"""
    if not os.path.exists(LIVE_FILE):
        return
    with open(LIVE_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    marker = "## 📋 新任务"
    sections = content.split(marker)
    if len(sections) <= 11:  # header + <=10 tasks
        return
    header = sections[0]
    tasks = sections[1:]
    kept = marker + marker.join(tasks[-10:])
    with open(LIVE_FILE, "w", encoding="utf-8") as f:
        f.write(header + kept)
    print(f"  [clean_dlive] 保留10条，清理 {len(tasks) - 10} 条旧记录")


# ── A / B / M 调用 ──

# M 持久 Agent：通过 m_agent.py 守护进程通信，首次启动后常驻
M_PROMPT = os.path.join(LOOP, "m_prompt.txt")
M_RESPONSE = os.path.join(LOOP, "m_response.txt")
M_PID = os.path.join(LOOP, "m_agent.pid")

class MAgent:
    def __init__(self):
        self._started = False

    def _ensure(self):
        if self._started:
            return
        # 检查守护进程是否在运行
        if os.path.exists(M_PID):
            try:
                with open(M_PID) as f:
                    pid = int(f.read().strip())
                import psutil
                if psutil.pid_exists(pid):
                    self._started = True
                    return
            except: pass
        # 启动守护进程
        import subprocess as _sp
        _script = os.path.join(SCRIPTS, "m_agent.py")
        _sp.Popen([sys.executable, _script], stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
        # 等待 daemon 就绪（最多 8s）
        _t0 = time.time()
        while time.time() - _t0 < 8:
            if os.path.exists(M_PID):
                try:
                    with open(M_PID) as f:
                        pid = int(f.read().strip())
                    import psutil
                    if psutil.pid_exists(pid):
                        self._started = True
                        return
                except: pass
            time.sleep(0.5)
        print(f"⚠️ M daemon did not start within 8s")

    def chat(self, prompt, system_prompt=""):
        self._ensure()
        full = (system_prompt + "\n\n" + prompt) if system_prompt else prompt
        with open(M_PROMPT, "w") as f:
            f.write(full)
        # 等待响应（轮询）
        import time as _t
        _deadline = _t.time() + 600  # M 不限死，10分钟
        _last_size = 0
        while _t.time() < _deadline:
            if os.path.exists(M_RESPONSE):
                _size = os.path.getsize(M_RESPONSE)
                if _size > 0 and _size == _last_size:
                    # 文件不再增长，认为写入完成
                    with open(M_RESPONSE) as f:
                        resp = f.read().strip()
                    os.remove(M_RESPONSE)
                    return resp if resp else "[M Error: empty response]"
                _last_size = _size
            _t.sleep(0.5)
        return "[LLM Timeout]"

_m_agent = MAgent()


def a_design(task, research=None, history=None, role=ROLE_A):
    # ── 结构优先级：核心任务第一，参考次之 ──
    p = "请根据任务直接输出完整设计方案。\n\n"
    # 1. 核心任务（最高优先级，写在最前面）
    p += f"核心任务：\n{task}\n\n"
    # 2. 参考资料（中优先级，可选参考，非必须覆盖）
    if research:
        # 从 research 中提取关键点（取带有明确结论/数据的段落，而非搜索条目描述）
        lines = research.strip().split("\n")
        key_points = [l.strip() for l in lines if l.strip() and not l.startswith("  - ")]
        ref_text = "\n".join(key_points) if key_points else research
        p += f"参考资料（可选参考，非必须全部覆盖）：\n{ref_text[:800]}\n\n"
    # 3. 历史反馈（低优先级）
    if history:
        p += f"上一轮反馈摘要：\n{history[:300]}\n\n"
    # 4. 格式指令放在最后（离输出最近）
    p += "---\n输出格式：第一行 [摘要] → 中间完整方案 → 最后一行 [精炼]\n直接输出方案："
    t0 = time.time()
    resp = ask_direct(p, system_prompt=role, max_wait=40)  # A 设计 40s
    if resp is None or resp.startswith("[LLM"):
        resp = ask(role + "\n\n" + p, max_wait=40)  # fallback 40s（慢通道更需等够）
        # ── 关键修复：fallback 也可能返回 [LLM Timeout]，必须拦截 ──
        if resp is None or resp.startswith("[LLM"):
            return None, {"elapsed": round(time.time()-t0, 1), "summary": "", "length": 0}
    el = time.time() - t0
    # ── 截断检测：检查是否以 [精炼] 结尾 ──
    if resp:
        lines = resp.strip().split("\n")
        has_refined = any(l.strip().startswith("[精炼]") for l in lines)
        # 如果没找到 [精炼] 且输出超过2000字，很可能被截断 → 尝试补全
        if not has_refined and len(resp) > 2000:
            print(f"  [a_design] ⚠️ 检测到可能截断（{len(resp)}字，无[精炼]），尝试补全...")
            retry_p = f"你之前的输出被截断了。请仅输出遗漏的后半部分，以 [精炼] 结尾。完整性大于长度。\n\n你之前输出的末尾：\n{resp[-800:]}\n\n从断点处继续输出，直到 [精炼]："
            resp2 = ask_direct(retry_p, max_wait=45)
            if resp2 and not resp2.startswith("[LLM"):
                resp = resp + "\n" + resp2
                print(f"  [a_design] ✅ 补全后 {len(resp)}字")
    # ── 截断检测结束 ──
    summary = ""
    for line in (resp or "").split("\n"):
        s = line.strip()
        if s.startswith("[摘要]"): summary = s[4:].strip(); break
    return resp, {"elapsed": round(el,1), "summary": summary, "length": len(resp or "")}

def b_review(design_content, role=ROLE_B):
    p = "请完整评审以下方案。\n\n评审要求：\n1. 从完整性、可行性、可扩展性、遗漏点、安全性、性能、可维护性维度展开\n2. 第一行必须写 [PASS] 或 [REJECT]\n3. 检查开头200字内是否列出了所有主要内容的名字和一句话定义\n4. 检查末尾是否完整、不超长\n5. 检查每个子系统是否有具体实现细节\n6. 输出格式：第一行 [PASS]/[REJECT] + 理由，最后一行 [精炼]\n7. 中间写完整的评审意见\n\n"
    # ── 前置硬规则检查：不依赖 LLM，杜绝 B 标准漂移 ──
    if not design_content or len(design_content.strip()) < 100:
        return f"[REJECT] 方案内容严重不完整（{len(design_content or '')}字），无法进行有效评审。", {"elapsed": 0.1, "verdict": "REJECT", "focus": "REJECT 内容过短"}
    # 检查 [精炼] 标记（硬规则）
    has_refined = any(l.strip().startswith("[精炼]") for l in design_content.split("\n"))
    if not has_refined:
        return f"[REJECT] 方案末尾缺少 [精炼] 总结标记，疑似截断或未完成。", {"elapsed": 0.1, "verdict": "REJECT", "focus": "REJECT 缺[精炼]"}
    # ── 硬规则通过，走 LLM 评审（优先本地 Ollama，省 token）──
    p += f"以下是需要评审的方案内容：\n{design_content[:4000]}\n\n---\n评审意见："
    t0 = time.time()
    resp = ask_local(p, system_prompt=role, max_wait=30)  # 本地先试
    if resp is None:
        resp = ask_direct(p, system_prompt=role, max_wait=20)  # 本地不可达→云端
    if resp is None or resp.startswith("[LLM"): resp = ask(role + "\n\n" + p, max_wait=20)
    el = time.time() - t0
    first = (resp or "").strip().split("\n")[0].strip().upper()
    return resp, {"elapsed": round(el,1), "verdict": "PASS" if "[PASS]" in first else "REJECT", "focus": first[:100]}

def _build_memory_summary():
    """从 m_history.json 提取结构化历史模式摘要，替代原始 JSON dump"""
    try:
        with open(M_HISTORY) as f:
            records = json.load(f)
    except Exception:
        return "(无历史记录)"
    if not records:
        return "(无历史记录)"
    # 提取有内容的 finding
    findings = []
    for r in records:
        ft = (r.get("finding") or "").strip()
        if ft and len(ft) > 10 and not ft.startswith("[LLM"):
            findings.append(ft)
    if not findings:
        return f"(共{len(records)}条记录，无分析结论)"
    # 按关键词聚类
    clusters = {}
    for ft in findings:
        matched = False
        for kw in ["截断", "评审标准", "prompt", "架构", "速度", "M 跳过"]:
            if kw in ft:
                clusters.setdefault(kw, []).append(ft[:120])
                matched = True
        if not matched:
            clusters.setdefault("其他", []).append(ft[:120])
    # 格式化
    lines = ["=== 历史模式摘要 ==="]
    for kw, items in sorted(clusters.items(), key=lambda x: -len(x[1])):
        lines.append(f"\n📌 {kw} (出现{len(items)}次)")
        for item in items[:2]:
            lines.append(f"  - {item}")
    return "\n".join(lines)


def m_reflect(task, designs, reviews, final_design, mh):
    """M 用 ask()（有工具链）自己分析、自己读文件、自己 patch。coordinator 只给上下文。"""
    rounds_s = "\n".join([f"  第{r+1}轮: {len(d)}字符" for r,d in enumerate(designs)])
    review_s = "\n".join([f"  第{r+1}轮评审: {(v or '')[:100]}" for r,v in enumerate(reviews)])
    mh_text = _build_memory_summary()
    
    # 读取 M 工作笔记
    nb_text = ""
    try:
        with open(M_NOTEBOOK) as f: nb_text = f.read()[-2000:]
    except: nb_text = "(无)"

    # 读取关键文件（供 fallback M 使用，它没有工具链）
    _fallback_files = {}
    for _fp, _fn in [(os.path.join(SCRIPTS, "coordinator.py"), "coordinator.py"),
                     (os.path.join(SCRIPTS, "role_prompts.py"), "role_prompts.py")]:
        try:
            with open(_fp) as _f: _fallback_files[_fn] = _f.read()[-1000:]
        except: pass
    
    prompt = f"""你是自迭代系统的元思考者（M）。你的视角不在 A-B 内部，而在系统之上。

任务：{task[:200]}

A-B 结果：{rounds_s}
评审：{review_s}

{mh_text}

你的工作笔记：
{nb_text}

选一个最关键的问题回答（不要全答）：
1. 这次迭代暴露了什么架构性问题？
2. 之前反复出现没根除的问题，根因到底是什么？
3. 有没有更好的架构方案？

决策：发现 prompt 问题 → patch 修改 | 发现架构问题 → 输出 [架构建议]
输出格式：先分析，再决定是否行动。60秒内，只回答最关键的那个问题。"""
    
    resp = _m_agent.chat(prompt, system_prompt="你是自迭代系统的元反思者M，有完整的 Hermes 工具链。输出格式：先做元分析，再决定是否行动。")
    if resp is None or resp.startswith("[LLM"):
        # fallback: M 无工具链，由 coordinator 读取文件后传给 M，M 用 [动作:] 格式输出修改
        _ctx = ""
        for _fn, _fc in _fallback_files.items():
            _ctx += f"\n--- {_fn} (末尾1000字) ---\n{_fc}\n"
        _fb_prompt = prompt + f"\n\n注意：你当前在 fallback 模式，没有工具链。以下是关键文件的末尾内容供参考：\n{_ctx}\n\n如需修改文件，请用以下格式输出：\n[动作: patch <文件路径>|<旧文本>|<新文本>]\n[动作: write <文件路径>|<完整内容>]"
        resp = ask_direct(_fb_prompt, system_prompt="你是自迭代系统的元反思者M（fallback模式）。用 [动作:] 格式输出修改指令，coordinator 会代执行。", max_wait=60)
    
    finding = ""
    for line in (resp or "").split("\n"):
        s = line.strip()
        if s.startswith("[发现]"): finding = s[4:].strip(); break
    if not finding: finding = (resp or "")[:200]
    return resp, {"finding": finding}


# ── 主调度 ──

def run(task, with_search=True, max_rounds=3, with_meta=True):
    mh = MHistory()
    d = D(task)
    
    # 搜索
    research = ""
    if with_search:
        # 从任务中提取搜索关键词
        import re as _re
        _query = task
        _strip = _re.sub(r'^[🔍🎨📋#*\s\[\]]+', '', _query).strip()
        # 取前80字作为搜索关键词（去除非内容开头）
        _kw = _strip[:80] if len(_strip) < len(_query) else _query[:80]
        d.log("🔍", f"S 搜索: \"{_kw}...\"")
        for fn, kw, name in [(hermes_web_search, {"limit": 5}, "Hermes"),
                              (search_tavily, {"max_results": 5}, "Tavily"),
                              (search_searxng, {"max_results": 5}, "SearXNG")]:
            try:
                result = fn(_kw, **kw)
            except Exception as _e:
                d.log("🔍", f"S ⚠️ {name}: {_e}")
                continue
            if isinstance(result, list) and result:
                research = "\n".join(f"  - {r.get('title','')}: {r.get('description','')[:200]}" for r in result)
                d.log("🔍", f"S ✅ {name} {len(result)}条")
                # 从前 2 个 URL 拉全文补充
                urls = [r["url"] for r in result if r.get("url")][:2]
                if urls:
                    try:
                        import urllib.request, re as _re
                        extras = []
                        for _url in urls:
                            try:
                                _req = urllib.request.Request(_url, headers={"User-Agent": "Mozilla/5.0"})
                                with urllib.request.urlopen(_req, timeout=8) as _resp:
                                    _html = _resp.read().decode("utf-8", errors="replace")
                                # 简洁提取：去掉标签，取前500字
                                _txt = _re.sub(r'<[^>]+>', '', _html)
                                _txt = _re.sub(r'\s+', ' ', _txt).strip()[:500]
                                if _txt:
                                    extras.append(f"=== {_url} ===\n{_txt}")
                            except Exception:
                                continue
                        if extras:
                            research += "\n\n" + "\n\n".join(extras)
                            d.log("🔍", f"S 📄 {len(extras)}页全文补充")
                    except Exception as _e2:
                        d.log("🔍", f"S ⚠️ web_extract: {_e2}")
                break
        else:
            d.log("🔍", "S ⚠️ 所有搜索通道均无返回，A将闭门造车")
    
    # A-B 循环
    designs = []; reviews = []; history = ""; final_design = ""; b_meta = {"verdict": "UNKNOWN"}; m_meta = {"finding": ""}

    # -- 任务分类器：判断 A-B 是否适合处理此任务 --
    _skip_ab = False
    _is_simple = False
    _code_kw = ["写代码", "实现", "编写", "修复", "改bug", "写测试", "代码实现", "改代码", "修bug", "bug", "函数", "接口", "实现一个", "写一个", "修复一个", "实现如下"]
    _search_kw = ["搜索", "查找", "查一下", "搜一下", "查询", "google", "搜索互联网", "查资料", "找一下"]
    _simple_kw = ["输出", "测试", "恢复", "ping", "当前时间", "进度", "已恢复", "说一句话"]
    _task_lower = task.lower()
    if any(kw in _task_lower for kw in _code_kw):
        d.log("🔀", f"任务分类: 代码类 → 跳过 A-B，直送 M")
        _skip_ab = True
    elif any(kw in _task_lower for kw in _search_kw):
        d.log("🔀", f"任务分类: 搜索类 → 直送 S+M")
        _skip_ab = True
    elif any(kw in _task_lower for kw in _simple_kw):
        d.log("🔀", f"任务分类: 简单响应 → 跳过 A-B-M")
        _skip_ab = True
        _is_simple = True

    if _skip_ab:
        round_i = 0
        if _is_simple:
            final_design = task
            b_meta = {"verdict": "PASS"}
            d.log("💬", f"简单响应: {task[:100]}")
        elif with_meta:
            m_result, m_meta = m_reflect(task, [], [], "", mh)
            d.log("🧠", f"M: {m_meta.get('finding','')[:200]}")
            final_design = m_result or ""
            b_meta = {"verdict": "PASS" if m_result else "UNKNOWN"}
        else:
            final_design = ""
            b_meta = {"verdict": "UNKNOWN"}
    else:
        for round_i in range(1, max_rounds + 1):
            dt, am = a_design(task, research, history)
            am["round"] = round_i; designs.append(dt or "")
            if not dt: d.log("🔄", f"A ⚠️ 第{round_i}轮失败"); break
            d.log("🎨", f"A 第{round_i}轮 ({am['elapsed']}s {am['length']}字)")
            
            rt, bm = b_review(dt)
            bm["round"] = round_i; reviews.append(rt or ""); b_meta = bm
            em = "✅" if bm["verdict"]=="PASS" else "🔴"
            d.log("🔍", f"B 第{round_i}轮 → {em} {bm['verdict']}")
            
            if bm["verdict"] == "PASS": final_design = dt; break
            history = rt[:300]
    
    if not final_design and designs: final_design = designs[-1]
    
    # M 反思 — 提速策略：
    #   如果 A-B 一轮 PASS 且方案质量好 → 跳过 M（已足够好）
    #   否则用 ask_direct（无 Hermes 载荷开销），M 输出了 [动作] 则 coordinator 执行 patch
    skip_m = (
        with_meta
        and b_meta.get("verdict") == "PASS"
        and round_i <= 2
        and len(final_design) > 500
    )
    if skip_m:
        d.log("🧠", "M ⏭️ 跳过（一轮PASS，质量达标）")
        m_result = "[M 跳过]"
        m_meta = {"finding": "一轮PASS，跳过M"}
    elif with_meta and designs and reviews:
        d.log("🧠", "M 反思中（直调）...")
        m_result, m_meta = m_reflect(task, designs, reviews, final_design, mh)
        d.log("🧠", f"M: {m_meta.get('finding','')[:200]}")
        
        # ── 写入 M 工作笔记（保留完整内容） ──
        _finding = m_meta.get('finding', '')
        if _finding and len(_finding) > 20 and not _finding.startswith('[LLM'):
            try:
                with open(M_NOTEBOOK, "a", encoding="utf-8") as _f:
                    # 智能截断：保留开头+结尾，中间省略
                    _body = _finding[:1500]
                    if len(_finding) > 1500:
                        _body = _finding[:1200] + "\n...（省略中间）...\n" + _finding[-200:]
                    _f.write(f"\n## {time.strftime('%m-%d %H:%M')} | {task[:80]}\n{_body}\n")
            except: pass
        
        # ── 解析 M 的 [动作] 指令并执行（M 无工具链时由 coordinator 代执行）──
        if m_result:
            for line in m_result.split("\n"):
                s = line.strip()
                if s.startswith("[动作:"):
                    # 格式: [动作: patch <file>|<old>|<new>]
                    # 格式: [动作: write <file>|<content>]
                    parts = s[4:-1].strip().split("|", 1)
                    action_type = parts[0].strip()
                    if action_type == "patch" and len(parts) > 1:
                        sub = parts[1].split("|", 2)
                        if len(sub) == 3:
                            try:
                                from hermes_tools import patch as _ht_patch
                                _r = _ht_patch(sub[0], sub[1], sub[2])
                                d.log("📝", f"M 动作: patch {sub[0]} {'✅' if _r.get('success') else '❌'}")
                            except Exception as _e:
                                d.log("📝", f"M 动作: patch {sub[0]} ❌ {_e}")
        
        # ── 报告 M 修改了哪些文件 ──
        import subprocess as _sp
        _diff = _sp.run(["git", "diff", "--name-only"], capture_output=True, text=True, timeout=5, cwd=HERMES).stdout.strip()
        if _diff:
            for _f in _diff.split("\n"):
                if _f.endswith(".py") or _f.endswith(".yaml"):
                    d.log("📝", f"M 修改: {_f}")
        
        # ── 验证：M 决定怎么验证自己的修改 ──
        # M 的输出中可能包含 [验证: immediate|deferred|observe]
        verify_mode = "immediate"  # 默认立即验证
        if m_result:
            for line in m_result.split("\n"):
                s = line.strip().lower()
                if "[验证: immediate" in s: verify_mode = "immediate"; break
                elif "[验证: deferred" in s: verify_mode = "deferred"; break
                elif "[验证: observe" in s: verify_mode = "observe"; break
        
        if verify_mode == "immediate":
            import subprocess as _sp
            changed = _sp.run(["git", "diff", "--name-only"], capture_output=True, text=True, timeout=5, cwd=HERMES).stdout
            if "role_prompts.py" in changed or "coordinator.py" in changed:
                d.log("🔄", "M 选择立即验证，重载模块重跑...")
                import importlib as _il
                import role_prompts as _rp
                _il.reload(_rp)
                _dt, _am = a_design(task, research, "", role=_rp.A)
                if _dt:
                    _rt, _bm = b_review(_dt, role=_rp.B)
                    d.log("📊", f"验证: {_bm.get('verdict','')} ({_am['elapsed']}s/{_bm['elapsed']}s)")
                    if _bm.get("verdict") == "PASS":
                        d.log("✅", "M 修改验证通过")
                        b_meta = _bm
                        final_design = _dt
                        round_i = 1  # M的验证算1轮
        elif verify_mode == "deferred":
            d.log("⏳", "M 选择延后验证，等待后续任务观察效果")
        elif verify_mode == "observe":
            d.log("👀", "M 选择仅观察，不下结论")
    
    # E 评估
    # ── 收集 M 的修改记录用于因果追踪 ──
    m_changes = ""
    if with_meta:
        import subprocess as _sp
        _diff = _sp.run(["git", "diff", "--name-only"], capture_output=True, text=True, timeout=5, cwd=HERMES).stdout.strip()
        m_changes = _diff
    
    metrics = {"verdict": b_meta.get("verdict","UNKNOWN"), "rounds": round_i, "elapsed": round(time.time()-d.t0,1), "final_length": len(final_design)}
    outcome = mh.evaluate(metrics)
    mh.record({"task": task[:100], "finding": m_meta.get("finding","")[:300] if with_meta else "", "outcome": outcome, "result": metrics, "m_changes": m_changes})
    d.log("📊", f"E → {outcome}" + (f" (M改了: {len(m_changes.split(chr(10)))}个文件)" if m_changes else ""))
    
    # ── 生成下一步建议 ──
    suggestion_text = ""
    try:
        _sug_prompt = f"基于以下任务执行结果，给出1-2句可执行的下一步建议，不要空话。\n\n任务: {task[:120]}\n结果: {metrics['rounds']}轮 | {metrics['verdict']} | {metrics['elapsed']}s\n\n下一步建议（一句话）:"
        _sug = ask_direct(_sug_prompt, max_wait=8)
        if _sug and not _sug.startswith("[LLM") and len(_sug.strip()) > 10:
            suggestion_text = _sug.strip()[:150]
            d.log("💡", f"下一步: {suggestion_text}")
    except Exception:
        pass
    
    # D 报告
    refined = ""
    for line in (final_design or "").split("\n"):
        if line.strip().startswith("[精炼]"): refined = line[4:].strip(); break
    d.log("📡", f"D: {round_i}轮 | {b_meta.get('verdict','')} | {len(final_design)}字")
    if refined: d.log("📡", f"精炼: {refined[:200]}")
    
    # 写入文件
    ts = int(time.time())
    out_path = os.path.join(OUTPUT, f"FINAL_{ts}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# 最终方案\n\n## 任务\n{task}\n\n## 方案\n{final_design}\n")
    
    # 判断任务是否完成
    # 严化条件：A-B PASS 且有实质输出，或 M 改了代码文件
    verdict = b_meta.get('verdict','UNKNOWN')
    m_did_work = bool(m_changes)
    m_changed_code = False
    if m_changes:
        for _f in m_changes.split("\n"):
            _f = _f.strip()
            if _f.endswith(".py") or _f.endswith(".yaml"):
                m_changed_code = True
                break
    
    has_output = len(final_design) > 100
    done = (verdict == "PASS" and has_output) or m_changed_code
    icon = "✅" if done else "❌"
    
    # 仲裁标记：真正死锁
    if verdict != "PASS" and not m_changed_code:
        d.log("⚡", "仲裁: A-B未通过且M无修改，需人工介入")
    
    d.log(icon, f"任务完成: {verdict}" + (" (M已修复)" if m_did_work and verdict != "PASS" else "") + f" | {round_i}轮 | {len(final_design)}字 | {round(time.time()-d.t0,1)}s")

    # -- 健康度 + 趋势 --
    try:
        with open(M_HISTORY) as _f:
            _hd = json.load(_f)
        _pass = sum(1 for h in _hd if h.get("result",{}).get("verdict")=="PASS")
        _rate = round(_pass/len(_hd)*100)
        _el = [h.get("result",{}).get("elapsed",0) for h in _hd if h.get("result",{}).get("elapsed")]
        _avg = round(sum(_el)/len(_el)) if _el else 0
        with open(M_NOTEBOOK) as _f:
            _nb = len(_f.read().splitlines())
        _trend = mh.trend()
        _line = f"📊 健康度: PASS率{_rate}% | 平均{_avg}s | M笔记{_nb}行 | 总{len(_hd)}次"
        if _trend:
            _line += f" | {_trend}"
        d.log("📊", _line)
    except: pass

    # 清理 d_live，保留最近10条
    clean_dlive()

    # -- 自动 git commit --
    try:
        import subprocess as _sp
        _diff = _sp.run(["git", "diff", "--name-only"], capture_output=True, text=True, timeout=5, cwd=HERMES).stdout.strip()
        if _diff:
            _sp.run(["git", "add", "-A"], capture_output=True, timeout=5, cwd=HERMES)
            _msg = f"auto: {task[:60].strip()} | {b_meta.get('verdict','')} {round_i}轮 {metrics['elapsed']}s"
            _sp.run(["git", "commit", "-m", _msg, "--quiet"], capture_output=True, timeout=5, cwd=HERMES)
    except Exception:
        pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python coordinator.py <任务> [--no-search] [--rounds N] [--no-meta]")
        sys.exit(1)
    task = sys.argv[1]
    ws = "--no-search" not in sys.argv
    wm = "--no-meta" not in sys.argv
    r = 2
    for i, a in enumerate(sys.argv):
        if a == "--rounds" and i+1 < len(sys.argv): r = int(sys.argv[i+1])
    run(task, with_search=ws, max_rounds=r, with_meta=wm)
