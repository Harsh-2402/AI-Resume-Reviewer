<div align="center">

# 🤖 AI Resume Reviewer

**Intelligent, agentic resume analysis powered by LangGraph & Google Gemini**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-1C1C1C?style=for-the-badge&logo=langchain&logoColor=white)](https://github.com/langchain-ai/langgraph)
[![Gemini](https://img.shields.io/badge/Gemini_2.5_Flash-Google-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://aistudio.google.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

Upload a resume → get an ATS score → receive AI-driven improvements → repeat until it's great.

</div>

---

## ✨ What It Does

- 📄 **Parses** PDF and DOCX resumes automatically
- 🧠 **Extracts** structured candidate info using Gemini LLM
- 🎯 **Matches** your skills against a job description and flags gaps
- 📊 **Scores** your resume using a weighted ATS formula
- 🔄 **Iterates** — if your score is below 75, it rewrites and re-evaluates (up to 3 cycles)
- 💡 **Delivers** improved bullet points and actionable final feedback

---

## 🏗️ Architecture

The system is a **6-agent LangGraph StateGraph** with an autonomous refinement loop:

```
┌─────────┐    ┌───────────┐    ┌────────────────┐    ┌────────┐
│  START  │───▶│  Parser   │───▶│   Extractor    │───▶│ Skills │
└─────────┘    └───────────┘    └────────────────┘    └───┬────┘
                                                           │
                                                      ┌────▼─────┐
                                                      │  Scorer  │
                                                      └────┬─────┘
                                                           │
                                                    ┌──────▼──────┐
                                           ┌────────│  Evaluator  │────────┐
                                           │        └─────────────┘        │
                                      score ≥ 75                      score < 75
                                           │                               │
                                         ┌─▼──┐                  ┌────────▼─────────┐
                                         │ END│                  │ Improvement Agent │
                                         └────┘                  └────────┬─────────┘
                                                                          │
                                                                 loops back to Scorer
                                                                    (max 3 times)
```

| # | Agent | Uses LLM | Responsibility |
|---|---|:---:|---|
| 1 | **Resume Parser** | — | Extracts raw text from PDF / DOCX |
| 2 | **Information Extractor** | ✅ | Pulls name, email, education, experience |
| 3 | **Skills Analyzer** | ✅ | Matches / gaps skills vs. job description |
| 4 | **ATS Scorer** | — | Weighted formula → numeric ATS score |
| 5 | **Evaluator** | — | Routes to `pass` or `improve` |
| 6 | **Improvement Agent** | ✅ | Rewrites bullets, generates feedback |

> All agents share a single `ResumeState` TypedDict — each reads the full state and returns an updated copy.

---

## 🚀 Quick Start

### 1 — Clone

```bash
git clone https://github.com/<your-username>/AI-Resume-Reviewer.git
cd AI-Resume-Reviewer
```

### 2 — Set up Python environment

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3 — Add your Gemini API key

```bash
cp .env.example .env
# Open .env and paste your key:  GEMINI_API_KEY=your_key_here
```

> 🔑 Get a **free** key at [Google AI Studio](https://aistudio.google.com/app/apikey)

### 4 — Launch

**Streamlit app (recommended)**
```bash
streamlit run app.py
```

**Jupyter notebook**
```bash
jupyter notebook AI_Resume_Reviewer_Complete.ipynb
# Run all cells top-to-bottom — Cell 11 prints live agent logs
```

---

## 📁 Project Structure

```
AI-Resume-Reviewer/
├── 📓 AI_Resume_Reviewer_Complete.ipynb   # Self-contained notebook
├── 🖥️  app.py                             # Streamlit web interface
├── 📋 requirements.txt                    # Python dependencies
├── 🔐 .env.example                        # API key template
├── 📄 sample_resume.docx                  # Sample resume for testing
└── 📘 CLAUDE.md                           # AI coding assistant notes
```

---

## ⚙️ Configuration

| Constant | Default | Description |
|---|:---:|---|
| `PASS_THRESHOLD` | `75` | Minimum ATS score to exit the improvement loop |
| `MAX_ITERATIONS` | `3` | Hard cap on refinement cycles |
| Gemini model | `gemini-2.5-flash` | LLM powering all AI agents |

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Agent Orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) + [LangChain](https://langchain.com/) |
| LLM | [Google Gemini 2.5 Flash](https://aistudio.google.com/) |
| Web UI | [Streamlit](https://streamlit.io/) |
| Resume Parsing | PyPDF2, python-docx |
| Config | python-dotenv |

---

## 🤝 Contributing

Contributions are welcome!

1. Fork the repo
2. Create a feature branch — `git checkout -b feature/my-feature`
3. Commit your changes — `git commit -m "feat: add my feature"`
4. Push to your branch — `git push origin feature/my-feature`
5. Open a Pull Request

---

## 📜 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for details.

---

<div align="center">

Built with ❤️ using LangGraph · Gemini · Streamlit

</div>
