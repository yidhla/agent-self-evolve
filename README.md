# Agent Self-Evolve · AI 自进化系统

> 一个会自己改代码的 AI agent。从方案设计到代码提交，全自动自迭代。
>
> An AI agent that improves its own code. Fully autonomous self-iteration pipeline.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-green.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-active-brightgreen.svg)]()

---

## 中文

### 这是什么

Agent Self-Evolve 是一个**生产级** AI agent 自迭代系统。它用多角色流水线让 AI 自己发现问题、设计方案、评审改进、改代码、提交 git——全程无须人工干预。

**已持续运行 64 轮自迭代，通过率 59%，运行在 DeepSeek + 本地 Ollama 混合架构上。**

### 流水线

```
任务 → S(搜索) → A(方案设计) → B(评审) → M(元思考) → E(评估) → D(报告) → git commit
```

| 角色 | 职责 | 模型 | 成本 |
|------|------|------|------|
| S | 互联网搜索 | Hermes/Tavily/SearXNG | 免费 |
| A | 设计实现方案 | DeepSeek V4 Flash | ~2K token/轮 |
| B | 评审方案，给出 PASS/REJECT | 本地 qwen2.5:1.5b (Ollama) | **免费** |
| M | 元思考，读文件/改代码/写笔记 | DeepSeek V4 / Hermes CLI | ~3K token/轮 |
| E | 趋势追踪、健康度分析 | 纯 Python 逻辑 | 免费 |
| D | 实时报告 + 自动 git commit | 文件写入 | 免费 |

### 核心特性

- **零成本评审**：B 用本地 Ollama（CPU 模式），每次评审 ~15s，完全免费
- **智能路由**：代码/搜索类任务跳过 A-B 直送 M，减少无效消耗
- **M 探索循环**：M 不依赖 Hermes CLI，两轮自主探索——先主动读取需要的文件，再根因分析+改代码
- **熔断保护**：Ollama 不可达时自动降级（B 缓存模式 / 直送 M），不卡流程
- **自动 git commit**：每次迭代结束自动提交，支持回滚
- **健康仪表盘**：PASS 率 / 平均耗时 / 连续 worse 告警 / 趋势曲线

### 快速开始

```bash
# 1. 装依赖
pip install requests

# 2. 设 API key
echo "DEEPSEEK_API_KEY=sk-xxx" > .env
echo "OLLAMA_HOST=http://localhost:11434" >> .env

# 3. 启动本地 Ollama（可选，不启动则走云端降级）
ollama pull qwen2.5:1.5b && ollama serve

# 4. 跑第一轮
python scripts/coordinator.py "设计一个支持按级别过滤的日志模块"
```

### 架构文档

- [系统知识图谱](loop/system-arch.md) — 文件关系图 / 数据流向 / 组件职责
- [待解决问题](loop/待解决问题.md) — 已全部解决，留作参考
- [M 工作笔记](loop/m_notebook.md) — 204 行，64 轮迭代的元分析记录

### 实际数据（截至 2026-06-18）

```
总迭代次数: 64 轮
累计 PASS: 59%
平均耗时: 120s/轮
M 笔记行数: 204 行
近 5 轮 PASS 率: 100%
系统规模: coordinator.py 785 行 / agent_llm.py 261 行
```

---

## English

### What is this

Agent Self-Evolve is a production-grade self-iteration system for AI agents. A multi-role pipeline lets the AI autonomously discover issues, design solutions, review improvements, modify code, and commit to git — all without human intervention.

**64 self-iteration cycles completed with 59% pass rate, running on DeepSeek + local Ollama hybrid architecture.**

### Pipeline

```
Task → S(Search) → A(Design) → B(Review) → M(Meta-think) → E(Evaluate) → D(Report) → git commit
```

### Key Features

- **Zero-cost review:** B runs locally via Ollama (CPU mode), ~15s per review, completely free
- **Smart routing:** Code/search tasks skip A-B and go directly to M, reducing waste
- **M explore loop:** M doesn't need Hermes CLI — two-round autonomous exploration (reads needed files first, then root-cause analysis + code changes)
- **Circuit breaker:** Automatic degradation when Ollama is unreachable (B cache mode / skip to M), no blocking
- **Auto git commit:** Every iteration commits changes, with rollback support
- **Health dashboard:** Pass rate / average time / consecutive degradation alerts

### Quick Start

```bash
pip install requests
echo "DEEPSEEK_API_KEY=sk-xxx" > .env
echo "OLLAMA_HOST=http://localhost:11434" >> .env
ollama pull qwen2.5:1.5b && ollama serve
python scripts/coordinator.py "Design a logging module with level filtering"
```

### Real-world Stats (as of 2026-06-18)

```
Total iterations: 64
Overall pass rate: 59%
Average time: 120s/cycle
M notebook: 204 lines
Last 5 pass rate: 100%
Codebase: 785 lines (coordinator) + 261 lines (agent_llm)
```

---

## 协同部署（腾锐 D2000）

支持将 coordinator 部署到 ARM64 物理机（飞腾 D2000 · 麒麟 V10 · 8GB）上 24h 常驻运行，笔记本保留本体 + Ollama 推理。详见 `deploy_tengrui.sh`。

```
腾锐 D2000 (24h) → coordinator.py [A→B→M→E]
                     ├── A 设计 → DeepSeek API (付费)
                     ├── B 评审 → 笔记本 Ollama (免费, 内网)
                     └── M 探索 → DeepSeek API (付费)

笔记本 Win11 → Hermes Agent + Ollama + 本地推理
```

---

## License

MIT
