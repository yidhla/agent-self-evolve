# Agent Self-Evolve

A production-grade **AI agent self-iteration system** with an A(Designer) → B(Reviewer) → M(Meta-thinker) → E(Evaluator) → D(Reporter) pipeline for autonomous code improvement.

## Architecture

```
User Task
    │
    ▼
┌──────────────┐
│  coordinator │
│   .run()     │
└──────┬───────┘
       │
       ▼
┌──────────────┐     ┌──────────────┐
│  A (Design)  │────→│  B (Review)  │← loop until PASS or N rounds
│  LLM-based   │     │  Local Ollama│(zero API cost for review)
└──────────────┘     └──────┬───────┘
                            │
                   ┌──────────────┐
                   │  M (Meta)    │← Hermes AIAgent with full toolchain
                   │  m_agent.py  │  persistent daemon
                   └──────┬───────┘
                          │
                   ┌──────────────┐
                   │  E (Eval)    │← Trend tracking, pass rates
                   │  D (Report)  │  real-time d_live.md + auto git commit
                   └──────────────┘
```

## Key Features

- **Self-iteration loop:** A designs → B reviews → M meta-thinks → E evaluates → D reports
- **Local Ollama integration:** B (reviewer) runs via local qwen2.5:7b, saving API costs
- **Smart task classifier:** Automatically routes code/search/simple tasks to appropriate handlers
- **Auto git commit:** Every iteration commits changes automatically
- **Health metrics:** Tracks pass rates, trends, consecutive degradation detection
- **M daemon:** Persistent meta-thinker with full toolchain access

## Quick Start

1. Install dependencies: `pip install hermes-tools`
2. Start local Ollama: `ollama pull qwen2.5:7b && ollama serve`
3. Run: `python scripts/coordinator.py "your task description"`

## Cost Efficiency

| Component | Model | Cost |
|-----------|-------|------|
| A (Design) | DeepSeek/Claude/GPT | API cost |
| B (Review) | Local qwen2.5:7b | Free |
| M (Meta) | Full Hermes agent | API cost (skipped when A-B passes) |
| Simple tasks | Direct response | Free |

## File Structure

```
scripts/
├── coordinator.py   # Main scheduler (A-B-M-E-D pipeline)
├── agent_llm.py     # LLM helpers (cloud + local Ollama)
├── role_prompts.py  # A/B role definitions
└── m_agent.py       # M daemon (persistent AIAgent)
loop/
├── d_live.md        # Real-time reports
├── m_history.json   # M modification history
├── m_notebook.md    # M working notes
└── system-arch.md   # Architecture knowledge graph
```
