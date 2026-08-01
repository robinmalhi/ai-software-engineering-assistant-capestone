# 🤖 AI Software Engineering Assistant

<p align="center">

**A Multi-Agent AI Software Engineering Assistant built with the OpenAI Agents SDK to automate software engineering workflows from GitHub Issues, Repository Analysis, and Software Requirements.**

![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python)
![OpenAI](https://img.shields.io/badge/OpenAI-Agents-green?style=for-the-badge)
![GitHub](https://img.shields.io/badge/GitHub-API-black?style=for-the-badge&logo=github)
![Status](https://img.shields.io/badge/Status-Completed-success?style=for-the-badge)

</p>

---

# 📌 Project Overview

AI Software Engineering Assistant is a **multi-agent AI system** designed to simulate a professional software engineering team. Instead of relying on a single AI model, the project coordinates multiple specialized agents that collaboratively analyze requirements, create implementation plans, assist in development, review code quality, and generate documentation.

The assistant supports analysis of GitHub Issues, GitHub repositories, and raw software requirements while producing structured engineering reports.

---

# ✨ Features

- 🤖 Multi-Agent AI Architecture
- 📌 GitHub Issue URL Analysis
- 📂 Public GitHub Repository Analysis
- 💻 Local Repository Scanning
- 📝 Software Requirement Analysis
- 📊 Repository Context Builder
- 📄 Automated Markdown Report Generation
- ⚡ Modular Workflow Pipeline
- 🖥️ Command Line Interface (CLI)
- 🔄 Sequential Agent Collaboration

---

# 🏗️ System Architecture

```
                User
                  │
                  ▼
            Command Line
              (main.py)
                  │
                  ▼
         Workflow Orchestrator
                  │
      Repository Context Builder
                  │
 ┌─────────────────────────────────┐
 │ Requirements Analysis Agent     │
 │ Implementation Planning Agent   │
 │ Coding Assistant Agent          │
 │ Review & Bug Investigation      │
 │ Documentation Agent             │
 └─────────────────────────────────┘
                  │
                  ▼
       Markdown Engineering Report
```

---

# 🤖 AI Agents

## 1️⃣ Requirements Analysis Agent

- Extracts functional requirements
- Identifies constraints
- Understands project scope

---

## 2️⃣ Implementation Planning Agent

- Breaks requirements into tasks
- Suggests project architecture
- Creates implementation roadmap

---

## 3️⃣ Coding Assistant Agent

- Generates implementation suggestions
- Assists with feature development
- Recommends best coding practices

---

## 4️⃣ Review & Bug Investigation Agent

- Reviews generated solutions
- Detects possible bugs
- Suggests improvements

---

## 5️⃣ Documentation Agent

- Produces structured documentation
- Generates Markdown reports
- Summarizes project findings

---

# ⚙️ Technology Stack

| Technology | Purpose |
|------------|---------|
| Python 3.12 | Core Programming Language |
| OpenAI Agents SDK | Multi-Agent Framework |
| OpenAI API | AI Reasoning |
| GitHub API | Repository & Issue Analysis |
| Rich | CLI Interface |
| Pydantic | Data Validation |
| Markdown | Report Generation |

---

# 📂 Project Structure

```text
ai-software-engineering-assistant/
│
├── ai_assistant/
│   ├── agents/
│   ├── workflow/
│   ├── prompts/
│   ├── config/
│   └── utils/
│
├── main.py
├── requirements.txt
├── README.md
└── .env
```

---

# 🚀 Installation

```bash
git clone https://github.com/robinmalhi/ai-software-engineering-assistant-capestone.git

cd ai-software-engineering-assistant-capestone

python -m venv .venv

.venv\Scripts\activate

pip install -r requirements.txt
```

---

# 🔑 Environment Variables

Create a `.env` file and add:

```env
OPENAI_API_KEY=your_api_key
GITHUB_TOKEN=optional
```

---

# 💻 Usage

### Analyze a GitHub Issue

```bash
python main.py --url https://github.com/owner/repo/issues/1
```

### Analyze a Public Repository

```bash
python main.py --repo-url https://github.com/octocat/Hello-World
```

### Analyze Software Requirement

```bash
python main.py "Implement JWT Authentication"
```

### Help

```bash
python main.py --help
```

---

# 🔄 Workflow

1. Accept user input
2. Parse GitHub Issue or Requirement
3. Scan Repository
4. Build Repository Context
5. Execute Multi-Agent Workflow
6. Generate Engineering Report

---

# ✅ Verified Components

- CLI Interface
- Workflow Pipeline
- GitHub Issue Parser
- Repository URL Parser
- Repository Scanner
- Markdown Report Generator
- Configuration Loader

---

# 📈 Future Enhancements

- 🌐 Web Dashboard
- 🐳 Docker Support
- 🧪 Automated Testing Agent
- 🔀 Git Diff Review
- ☁️ Multi-LLM Support
- 📊 Interactive Visual Reports

---

# 📚 Documentation

This project includes:

- Project Documentation
- Architecture Diagram
- Presentation Slides
- Demo Video
- GitHub Repository

---

# 👨‍💻 Author

**Robin Malhi**

**AI Software Engineering Assistant**

Capstone Project demonstrating:

- Multi-Agent AI Systems
- Software Engineering Automation
- GitHub Repository Intelligence
- AI-assisted Development Workflow

---

# ⭐ Support

If you found this project useful, consider giving the repository a **⭐ Star**.

---

## 📄 License

This project is developed for **academic and educational purposes**.