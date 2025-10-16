# 🤖 LLM Code Deployment System
### *An Autonomous App Builder, Deployer & Evaluator Powered by LLMs*

---

## 📘 Overview
**LLM Code Deployment System** is an intelligent, end-to-end automation pipeline that can **build, deploy, and update** complete web applications using Large Language Models (LLMs).  

It transforms a simple JSON request into a **live, hosted web app** — complete with code generation, GitHub repository creation, automatic deployment to GitHub Pages, and evaluation server notifications.  

This project demonstrates the future of autonomous development — where **LLMs act as full-stack engineers**, capable of coding, versioning, and redeploying apps independently.

---

## ⚙️ Core Features

### 🚀 Build Phase
- Accepts a structured JSON POST request containing:
  - App brief
  - Task name and round number
  - Student email
  - Secret key validation
  - Nonce (unique identifier)
  - Evaluation URL
- Generates a fully functional application using **GPT-4o-mini** (via OpenAI/AiPipe API).
- Creates a new **public GitHub repository** automatically.
- Pushes generated files including:
  - `index.html`, `styles.css`, `script.js`, and `README.md`
- Adds an **MIT License** at the root.
- Enables **GitHub Pages** hosting for live access.

---

### 🔁 Revise / Update Phase
- Receives a new request with the same `nonce` to trigger an update.
- Fetches existing repo files dynamically.
- Uses an **intelligent context-aware prompt** to modify *only* what’s necessary.
- Keeps existing design, functionality, and layout intact.
- Updates or adds files only when required.
- Redeploys seamlessly to the same GitHub Pages URL.

---

### 🧪 Evaluation Phase
- After each deployment or update, the system automatically:
  - Sends repo URL, pages URL, commit SHA, nonce, and metadata to the provided `evaluation_url`.
  - Uses **exponential backoff retries** for reliability.
- Enables instructors or automated evaluators to validate builds programmatically.

---



---

## 🧰 Technology Stack

| Component | Technology |
|------------|-------------|
| **Backend Framework** | FastAPI |
| **Programming Language** | Python 3.10+ |
| **LLM API** | GPT-4o-mini (OpenAI / AiPipe endpoint) |
| **Version Control** | GitHub API |
| **Deployment** | GitHub Pages |
| **Networking** | `httpx` |
| **Environment Variables** | `python-dotenv` |
| **Storage** | JSON-based nonce tracker |

---

## 🛠️ Setup Guide

### 1️⃣ Clone the Repository
```bash
git clone https://github.com/Samsul-Habib/TDS-project1
cd TDS-project1
```

### 2️⃣ Create and Activate a Virtual Environment
```bash
python -m venv venv
source venv/bin/activate   # (Windows: venv\Scripts\activate)
```

### 3️⃣ Install Dependencies
```bash
pip install -r requirements.txt
```

### 4️⃣ Run the fastAPI server
```bash
uvicorn main:app --reload
```

### 🧠 Example Usage
✅ Build a New App
```bash
curl -X POST "http://127.0.0.1:8000/api-endpoint" \
-H "Content-Type: application/json" \
-d '{
  "email": "student@example.com",
  "secret": "my-secret",
  "task": "daily-compliment-app",
  "round": 1,
  "nonce": "compliment-app-001",
  "brief": "Build a minimal web app called Daily Compliment that displays a random compliment each time the user clicks a button. Keep the design simple, responsive, and professional.",
  "evaluation_url": "https://eval.example.com/notify"
}'
```
### The system will:
* Validate your secret
* Generate app code using the LLM
* Create a GitHub repository
* Push files and enable GitHub Pages
* Notify your evaluation server with all metadata

🔁 Update an Existing App
```bash
curl -X POST "http://127.0.0.1:8000/api-endpoint" \
-H "Content-Type: application/json" \
-d '{
  "email": "student@example.com",
  "secret": "my-secret",
  "task": "daily-compliment-app",
  "round": 2,
  "nonce": "compliment-app-001",
  "brief": "Add a greeting message and current date above the compliment. Keep the same design and update README.md accordingly.",
  "evaluation_url": "https://eval.example.com/notify"
}'
```
### The system:
* Detects the existing nonce
* Fetches the repo’s current code
* Generates incremental updates only
* Commits changes and redeploys automatically

### 🧾 License

This project is licensed under the MIT License.
