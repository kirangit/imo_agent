# Math Olympiad CLI Agent

This agent is a simple **command-line tool** that uses OpenAI models to solve Math Olympiad–style problems.  
It produces not just the **final answer**, but also **step-by-step reasoning**, **chapter classification**, **concepts**, **thinking style**, **difficulty**, and **practice suggestions**.  
The goal is to make contest math more approachable and interactive for students.

---

## ⚙️ Python Version

- **Python 3.13** is recommended.

---

## 📦 Installation

First, create and activate a virtual environment (optional but recommended):

```bash
python3.13 -m venv venv
source venv/bin/activate   # On macOS/Linux
venv\Scripts\activate      # On Windows
```

Install the required packages

```bash
pip install -r requirements.txt
```
---

## 🗂️ .env File

Create a `.env` file in the project root with the following content:

```env
LLM_API_KEY=your-api-key-here
LLM_MODEL=gpt-5
```

---

## ▶️ Usage

### Run interactively
```bash
python agent.py
```
Paste a problem and press:
- `Ctrl-D` (Linux/macOS)  
- `Ctrl-Z` + `Enter` (Windows)

### Run with a problem file
```bash
python agent.py --file problem.txt
```

### Override model at runtime
```bash
python agent.py --model gpt-4.1
```

### Show raw LaTeX (instead of converted Unicode/plaintext)
```bash
python agent.py --latex-raw
```

---

## ▶️ Youtube transcript downloader Usage

```bash
python youtube_transcript_downloader.py "IMO 2024 problem 5" --outdir out
```
---

## 📌 Notes

- LaTeX output from the model is automatically converted to human-readable Unicode for CLI display (using `pylatexenc`).  
- Use `--latex-raw` if you prefer to see the raw LaTeX strings.  
- The tool expects a single problem as input at a time.
