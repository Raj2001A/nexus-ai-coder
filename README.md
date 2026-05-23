# NexusAI: Agentic Code Orchestrator ⚡

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-Orchestration-orange)](https://github.com/langchain-ai/langgraph)

**NexusAI** is a production-grade, multi-agent system designed to autonomously ingest codebases, reason about complex developer tasks, and implement verified code changes. 

Unlike generic chatbots, NexusAI utilizes a **stateful graph-based workflow** to orchestrate specialized agents (Planner, Executor, Reviewer) through a rigorous RAG-enhanced development lifecycle.

---

## 🏗️ Architectural Deep Dive

### 1. Stateful Multi-Agent Orchestration (LangGraph)
The core logic is implemented as a **Directed Acyclic Graph (DAG)** using LangGraph. This ensures deterministic control flow and state persistence across agent handoffs.
- **Node-based Execution**: Each agent operates as a discrete node with specific input/output contracts.
- **Conditional Routing**: The system utilizes a "Reviewer Loop" that automatically triggers re-execution if the implementation fails verification (max 3 iterations).

### 2. Hybrid RAG Pipeline (ChromaDB + Gemini)
To provide deep context, NexusAI implements a sophisticated retrieval pipeline:
- **Semantic + Keyword Search**: Combines vector similarity with BM25-style keyword matching to catch exact function/variable names.
- **Reciprocal Rank Fusion (RRF)**: Industry-standard re-ranking algorithm to merge results from multiple retrieval strategies.
- **Language-Aware Chunking**: Uses AST-aware separators for Python, JS, and TS to preserve code block integrity.

### 3. Production-Ready Tooling & Safety
- **Sandbox-lite Execution**: Multi-runtime execution (Python, Node.js) with strict path-traversal protection.
- **Atomic File Operations**: Targeted patching and atomic writes to prevent project corruption.
- **Real-time Observability**: WebSocket-based event streaming for live agent tracing and metric visualization.

---

## 🛠️ Tech Stack

- **LLM**: Google Gemini 1.5 Pro (Planning/Review) & Flash (Execution)
- **Orchestration**: LangGraph + CrewAI
- **Database**: ChromaDB (Vector Store)
- **Backend**: FastAPI (Async REST + WebSockets)
- **Frontend**: Vanilla JS + CSS3 (Glassmorphism UI)
- **Infrastructure**: Docker & Docker Compose

---

## 🚀 Key Features

- **Automated Ingestion**: Support for local directory scanning and ZIP uploads.
- **Agentic Review Loop**: Automated test execution and code quality validation.
- **Self-Improvement Insights**: Aggregated run analytics that suggest system prompt optimizations.
- **Trust Metrics**: Real-time git-state tracking and verification logs.

---

## 📂 Repository Structure

```text
backend/
  agents/      # Specialized agent definitions (CrewAI)
  graph/       # LangGraph state & workflow logic
  rag/         # Ingestion, hybrid retrieval, and RRF re-ranking
  tools/       # Safe file ops, code runners, and documentation search
  api/         # FastAPI endpoints and WebSocket handlers
frontend/      # Premium dark-mode UI (No-framework dependency)
tests/         # Comprehensive test suite (40+ cases)
```

---

## 🚦 Getting Started

### Prerequisites
- Python 3.12+
- Node.js 24+ (for TS execution)
- Gemini API Key

### Installation
1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Configure environment: `cp .env.example .env` (Add your API keys)
4. Start the server: `uvicorn backend.api.main:app --reload`

---

## 🧪 Verification
The project includes a robust test suite covering API flows, path safety, and workflow logic.
```bash
python -m pytest tests
```

---

## 💡 Why this project?
This project was built to demonstrate proficiency in **LLM Orchestration**, **System Design**, and **Applied AI Engineering**. It solves the "hallucination problem" in coding assistants by enforcing a deterministic workflow, rigorous verification, and high-fidelity RAG.

---
*Created by Raja Rajeswaran for the Portfolio Showcase.*
