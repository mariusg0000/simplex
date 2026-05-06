# 🤖 Simplex AI

**Simplex AI** is a professional, async-native AI assistant optimized for office and administrative environments. It combines a clean, modern desktop interface with a powerful, model-agnostic engine capable of complex reasoning, document analysis, and autonomous tool usage.

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.11+-green)
![UI](https://img.shields.io/badge/UI-NiceGUI-orange)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## 🌟 General Vision
Simplex AI is designed to hide technical complexity behind a friendly graphical interface. While its "brain" is separate and model-agnostic, the application provides a seamless experience for non-technical users to manage documents, search local files, and automate routine office tasks.

## 🚀 Key Features

### 💻 Native Desktop Experience
*   **Standalone Window:** Runs as a native desktop application using NiceGUI's native mode (built on top of WebView/Qt via internal handlers), providing a seamless experience.
*   **Modern UI:** Built with NiceGUI/Vue for a responsive and intuitive chat experience.
*   **Persistent Settings:** Remembers your working directories and UI preferences across restarts.

### 🧠 Advanced AI Engine
*   **Async-Native Streaming:** Responses stream token-by-token for zero-latency feedback.
*   **Reasoning Process:** Real-time visibility into the AI's "Thinking" process before the final answer.
*   **Sub-agent Architecture:** Uses specialized internal agents (e.g., a **Reranker**) to filter and prioritize data.
*   **Model Agnostic:** Powered by `LiteLLM`—switch between OpenAI, Anthropic, Gemini, or local models (Ollama) via configuration.

### 📂 Intelligent Office Tools
*   **Focused File Search:** Strictly searches within user-defined working directories.
*   **Smart Reranking:** Automatically identifies the most relevant files based on chat context and modification time (Recent First).
*   **Document Reader:** Deep integration for reading and analyzing `.pdf`, `.docx`, `.xlsx`, and plain text files.
*   **Tool Execution Log:** Visual feedback when the AI is performing local operations.

---

## 🛠️ Tech Stack
*   **Core:** Python 3.11+
*   **Package Manager:** [uv](https://github.com/astral-sh/uv) (Extremely fast Python package installer)
*   **UI Framework:** [NiceGUI](https://nicegui.io/)
*   **LLM Integration:** [LiteLLM](https://github.com/BerriAI/litellm)
*   **Desktop Wrapper:** NiceGUI (Native Mode)
*   **Data Processing:** Pandas, PyPDF, python-docx

---

## 📥 Installation

1.  **Install `uv`** (if you haven't already):
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

2.  **Clone the repository:**
    ```bash
    git clone https://github.com/YOUR_USERNAME/Simplex.git
    cd Simplex
    ```

3.  **Sync dependencies:**
    ```bash
    uv sync
    ```

## ⚙️ Configuration

Create a `.env` file in the project root:

```env
# Core Settings
SIMPLEX_MODEL=openai/deepseek-chat
OPENAI_API_KEY=your_api_key_here
# OPENAI_API_BASE=optional_custom_url

# UI Settings
SIMPLEX_NATIVE_MODE=True
SIMPLEX_SYSTEM_PROMPT=You are Simplex AI, a helpful office assistant.
```

## 🚀 Usage

Run the application:
```bash
uv run python main.py
```

1.  **Configure Folders:** Click the **Settings (gear icon)** to add your working directories.
2.  **Search & Read:** Ask the AI to find documents (e.g., *"Find the 2024 tax report"*) and then analyze them (*"Summarize that PDF for me"*).
3.  **Toggle Reasoning:** Use the "Show Reasoning" checkbox to see how the AI arrives at its conclusions.

---

## 🗺️ Roadmap
- [ ] **Phase 3 Extension:** Integration with MCP (Model Context Protocol).
- [ ] **Data Analysis:** Advanced Pandas sub-agent for complex Excel queries.
- [ ] **Email Integration:** Outlook/Gmail drafter tools.
- [ ] **Confidential Mode:** One-click toggle for local-only execution via Ollama.

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
