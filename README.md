# Agent Self-Evolve

> An AI agent that improves its own code. A(Designer) B(Reviewer) M(Meta-thinker) E(Evaluator) D(Reporter) pipeline for autonomous self-iteration.
>
> 一个会自己改代码的 AI agent 系统。A(方案设计)B(评审)M(元思考)E(评估)D(报告) 全自动自迭代流水线。

---

## English

Agent Self-Evolve is a production-grade self-iteration system for AI agents using a multi-role pipeline.

### Pipeline

User Task S(Search) A(Design) B(Review) M(Meta-think) E(Evaluate) D(Report) git commit

| Role | Function | Model |
|------|----------|-------|
| S | Internet search (optional) | Google/Tavily/SearXNG |
| A | Generates solutions and architectures | DeepSeek/Claude/GPT |
| B | Reviews and validates | Local qwen2.5:1.5b (free) |
| M | Meta-thinker with full toolchain | Hermes AIAgent daemon |
| E | Trend tracking, pass rates, health metrics | Pure logic |
| D | Real-time reporter + auto git commit | File writer |

### Key Features

- **Zero-cost review:** B runs locally via Ollama (CPU mode, ~13s per review)
- **Smart routing:** Auto-classifies tasks: design / code / search / simple response
- **Auto git commit:** Every iteration commits changes automatically
- **Health dashboard:** Tracks pass rates, trends, alerts on consecutive degradation
- **M daemon:** Persistent meta-thinker with full file/tool access
- **Task classifier:** Code/search/simple tasks skip A-B, go directly to M

### Quick Start

```
pip install hermes-tools
ollama pull qwen2.5:1.5b
ollama serve
python scripts/coordinator.py "Design a logging module with level filtering"
```

### Cost Efficiency

Estimated 60% token savings compared to cloud-only pipelines. B review runs locally for free.

---

## 中文

Agent Self-Evolve 是一个生产级的 AI agent 自迭代系统。

### 流水线

用户任务 S(搜索) A(方案设计) B(评审) M(元思考) E(评估) D(报告) 自动提交

| 角色 | 职责 | 使用模型 |
|------|------|---------|
| S | 互联网搜索（可选） | Google/Tavily/SearXNG |
| A | 输出设计方案和架构 | DeepSeek/Claude/GPT |
| B | 评审方案，给出 PASS/REJECT | 本地 qwen2.5:1.5b（免费） |
| M | 元思考，有完整工具链可改代码 | Hermes AIAgent 守护进程 |
| E | 趋势分析、通过率追踪 | 纯逻辑计算 |
| D | 实时报告 + 自动 git 提交 | 文件写入 |

### 核心特性

- 零成本评审：B 使用本地 Ollama 运行，完全免费
- 智能路由：自动识别任务类型，分配不同处理路径
- 自动 git 提交：每次迭代结束自动提交代码改动
- 健康仪表盘：追踪通过率、平均耗时、连续退化告警
- 任务分类器：代码/搜索/简单任务跳过 A-B 直送 M

### 快速开始

```
pip install hermes-tools
ollama pull qwen2.5:1.5b
ollama serve
python scripts/coordinator.py "设计一个支持按级别过滤的日志模块"
---

## License

MIT
