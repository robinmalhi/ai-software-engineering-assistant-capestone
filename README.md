# ai-software-engineering-assistant-capestone
A modular AI Software Engineering Assistant built with the OpenAI Agents SDK that automates repository analysis, requirements gathering, planning, code generation, review, and documentation using a collaborative 5-agent pipeline.
# 🤖 AI Software Engineering Assistant

A multi-agent AI Software Engineering Assistant built with the **OpenAI Agents SDK** to automate software engineering workflows such as GitHub issue analysis, repository understanding, implementation planning, code review, and technical documentation.

---

## 🚀 Overview

AI Software Engineering Assistant simulates a professional software engineering team using multiple specialized AI agents. Instead of relying on a single AI model, the system coordinates independent agents that collaborate to analyze software requirements, generate implementation plans, review code quality, and produce structured engineering reports.

The assistant supports analysis of GitHub Issues, public repositories, local repositories, and raw software requirements through a modular workflow pipeline.

---

## ✨ Features

- 🤖 Multi-Agent AI Architecture
- 📌 GitHub Issue Analysis
- 📂 Public Repository Analysis
- 💻 Local Repository Scanning
- 📝 Software Requirement Analysis
- 📋 Automated Engineering Reports
- 🔄 Sequential Agent Workflow
- ⚡ Command Line Interface (CLI)
- 🛠 Modular Python Project Structure

---

## 🏗️ Architecture

```text
                User
                  │
                  ▼
          Command Line (CLI)
                  │
                  ▼
       Workflow Orchestrator
                  │
   ┌──────────────┼──────────────┐
   ▼              ▼              ▼
Requirements   Planning    Repository Scan
                  │
                  ▼
          Coding Assistant
                  │
                  ▼
          Review & Validation
                  │
                  ▼
      Documentation Generation
                  │
                  ▼
        Markdown Engineering Report
```

---

## 🤖 AI Agents

| Agent | Responsibility |
|-------|----------------|
| Requirements Agent | Analyze software requirements |
| Planning Agent | Generate implementation strategy |
| Coding Agent | Suggest implementation approach |
| Review Agent | Detect bugs and improvements |
| Documentation Agent | Generate structured reports |

---

## 🛠️ Technology Stack

- Python 3.12
- OpenAI Agents SDK
- OpenAI API
- GitHub REST API
- Markdown Reporting
- Modular Python Architecture

---

## 📂 Project Structure

```text
ai-software-engineering-assistant/
│
├── ai_assistant/
│   ├── agents/
│   ├── workflow/
│   ├── prompts/
│   ├── utils/
│   └── config/
│
├── tools/
├── main.py
├── requirements.txt
├── README.md
└── .gitignore
```

---

## ⚙️ Installation

```bash
git clone https://github.com/robinmalhi/ai-software-engineering-assistant-capestone.git

cd ai-software-engineering-assistant

python -m venv .venv

.venv\Scripts\activate

pip install -r requirements.txt
```

---

## 🔑 Environment Variables

Create a `.env` file:

```env
OPENAI_API_KEY=your_api_key
GITHUB_TOKEN=optional
```

---

## ▶️ Usage

### Analyze a GitHub Issue

```bash
python main.py --url https://github.com/owner/repository/issues/1
```

### Analyze a Public Repository

```bash
python main.py --repo-url https://github.com/octocat/Hello-World
```

### Analyze a Requirement

```bash
python main.py "Create a secure authentication system"
```

### CLI Help

```bash
python main.py --help
```

---

## 🔄 Workflow

1. Accept user input
2. Resolve GitHub issue or raw requirement
3. Scan repository context
4. Execute AI agent workflow
5. Generate implementation analysis
6. Produce Markdown engineering report

---

## ✅ Project Status

- ✔ Multi-Agent Workflow
- ✔ GitHub Issue Support
- ✔ Repository Analysis
- ✔ CLI Interface
- ✔ Automated Reporting
- ✔ Modular Architecture

---

## 🚀 Future Improvements

- Web Dashboard
- Docker Support
- Testing Agent
- Git Diff Review
- Multi-LLM Support
- Vercel + Render Deployment

---

## 👨‍💻 Author

**Robin Malhi**

Capstone Project – AI Software Engineering Assistant

Built to demonstrate **Multi-Agent AI Systems**, **Software Engineering Automation**, and **GitHub Repository Intelligence**.