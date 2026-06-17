# 自迭代系统项目知识图谱

> 自动生成于 2026-06-17。供新加入者（或agent）快速理解全系统。

---

## 1. 文件关系图

```
                     用户任务
                        │
                        ▼
              ┌───────────────────┐
              │  scripts/          │
              │  coordinator.py    │  ← 主调度器（529行）
              └────────┬──────────┘
                       │
          ┌────────────┼────────────┐
          │            │            │
          ▼            ▼            ▼
┌──────────────┐ ┌──────────┐ ┌──────────┐
│ agent_llm.py │ │m_agent.py│ │role_     │
│ LLM调用+搜索 │ │ M守护进程 │ │prompts.py│
│ (229行)      │ │ (105行)  │ │ A/B角色  │
└──────────────┘ └──────────┘ └──────────┘
                       │
                       ▼
              ┌───────────────────┐
              │  loop/ 运行时数据  │
              │ ├ d_live.md      │ ← D实时报告
              │ ├ m_history.json │ ← M修改历史
              │ ├ m_notebook.md  │ ← M工作笔记（145行）
              │ ├ m_agent.pid    │ ← daemon进程ID
              │ ├ 待解决问题.md   │ ← 问题跟踪（已清零）
              │ └ output/        │ ← 最终产出
              └───────────────────┘
```

## 2. 数据流向

```
用户输入任务
    │
    ▼
┌──────────────┐
│ coordinator  │
│   .run()     │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  S 搜索      │ ← hermes_web_search/Tavily/SearXNG
│  (可选)      │   搜索结果→research字符串
└──────┬───────┘
       │
       ▼
┌──────────────┐     ┌──────────────┐
│  A 设计      │────→│  B 评审      │← 循环至PASS或满N轮
│  ask_direct  │     │  ask_direct  │
│  40s超时     │     │  20s超时     │
└──────────────┘     └──────┬───────┘
                            │
                 PASS / 满3轮
                            │
                            ▼
                   ┌──────────────┐
                   │  M 元思考     │ ← 有Hermes工具链
                   │  AIAgent常驻  │ ← m_agent.py守护
                   │  m_notebook   │ ← 记录发现
                   └──────┬───────┘
                          │
                          ▼
                   ┌──────────────┐
                   │  E 评估       │ ← 对比m_history
                   │  improved/   │
                   │  worse       │
                   └──────┬───────┘
                          │
                          ▼
                   ┌──────────────┐
                   │  D 报告       │ → d_live.md
                   │  下一步建议   │
                   │  清理旧记录   │
                   └──────┬───────┘
                          │
                          ▼
                   输出到output/
                   + git commit
```

## 3. 组件职责边界

| 组件 | 做什么 | 不能做 | 用什么工具 |
|:----|:-------|:-------|:----------|
| S（搜索） | 搜索互联网返回research | 修改代码/文件 | web_search/Tavily |
| A（设计） | 输出设计方案 | 执行/修改代码 | ask_direct（裸LLM） |
| B（评审） | 评审方案给PASS/REJECT | 修改代码 | ask_direct（裸LLM） |
| M（元思考） | 读文件→分析→修改代码 | 改m_history/d_live自身 | Hermes工具链+AIagent |
| E（评估） | 对比历史记录判断进退 | 修改代码 | 纯逻辑+json |
| D（报告） | 写d_live.md+清理 | 改其他文件 | 文件追加 |

## 4. 关键参数

| 参数 | 值 | 说明 |
|:----|:---|:-----|
| A timeout | 40s | ask_direct主通道 |
| A fallback timeout | 40s | 降级到hermes -z |
| B timeout | 20s | 快审 |
| M timeout (daemon) | 600s | AIAgent常驻，不限死 |
| M timeout (fallback) | 60s | 无工具链，coordinator传文件上下文 |
| max_rounds | 3 | A-B循环上限 |
| max_tokens | 16384 | 输出长度上限 |

## 6. 改进日志 (2026-06-17)

| # | 改动 | 影响 |
|---|------|------|
| 1 | role_prompts.py: 清理A/B中旧6-agent架构残留（"D是调度中枢"、"路由给C"） | 减少prompt噪声约40% |
| 2 | 任务分类器: 代码/搜索类任务跳过A-B，直送M | 节省2-3轮A-B浪费 |
| 3 | 自动git commit: run()末尾自动提交改动 | 防止改动堆积 |
| 4 | M prompt精简: 5方向→3方向，聚焦 | 提升M输出质量 |
| 5 | E评估增强: 近5次PASS率+连续worse检测 | 健康度更有参考价值 |
| 6 | M fallback增强: 无工具链时coordinator传文件+[动作:]代执行 | fallback不再裸奔 |

## 5. 文件追踪状态

| 文件 | 行数 | 状态 | 最后修改者 |
|:----|:----|:-----|:----------|
| scripts/coordinator.py | ~529 | 活跃开发 | M + 我 |
| scripts/agent_llm.py | 229 | 稳定 | 我 |
| scripts/m_agent.py | 105 | 稳定 | 我 |
| scripts/role_prompts.py | 80 | 稳定 | M |
| loop/m_notebook.md | 145 | 持续增长 | M |
| loop/d_live.md | 动态 | 实时更新 | D |
| loop/待解决问题.md | 已清零 | 归档 | 我 |
| scripts/agent_entry.py | — | 已删除 | 我 |

---

*此图谱基于自迭代系统的自我分析生成。更新时请同步更新此图。*
