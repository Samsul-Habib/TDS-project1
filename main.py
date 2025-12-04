from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, HTMLResponse
import json,re
import os, time
import requests, pathlib,httpx
from dotenv import load_dotenv
from github import Github
from pathlib import Path
from github.GithubException import GithubException

# Load secret from .env file
load_dotenv()
MY_SECRET = os.getenv("MY_SECRET")
api_key=os.getenv("API_KEY")

# Load GitHub credentials
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
NONCE_TRACKER_FILE = Path("nonce_tracker.json")

app = FastAPI()

with open("index.html", "r", encoding="utf-8") as f:
    HOME_HTML = f.read()

@app.get("/", response_class=HTMLResponse)
async def home():
    return HOME_HTML


@app.post("/api-endpoint")
async def receive_task(request: Request):
    try:
        data = await request.json()  # Parse JSON request
        print("\n--- New Request Received ---")
        print(json.dumps(data, indent=2))

        # 1️⃣ Verify the secret
        if data.get("secret") != MY_SECRET:
            return JSONResponse({"error": "Invalid secret"}, status_code=403)

        # 2️⃣ Extract important fields
        email = data.get("email")
        task = data.get("task")
        round_num = data.get("round")
        brief = data.get("brief")
        evaluation_url = data.get("evaluation_url")
        attachments = data.get("attachments", [])
        nonce=data.get("nonce")

        print(f"✅ Verified secret for {email}")
        print(f"📋 Task: {task}")
        print(f"🧾 Round: {round_num}")
        print(f"🧠 Brief: {brief}")
        print(f"📦 Attachments: {len(attachments)} file(s)")
        print(f"🧩 Evaluation URL: {evaluation_url}")


        # 3️⃣ Generate app code using LLM
        print("\n🤖 Generating code using LLM...")

        # Load nonce tracker data
        if NONCE_TRACKER_FILE.exists():
            with open(NONCE_TRACKER_FILE, "r", encoding="utf-8") as f:
                nonce_data = json.load(f)
        else:
            nonce_data = {}

        # Check if this nonce already has a repo
        existing_repo_url = None
        commit_sha=None
        if nonce in nonce_data:
            existing_repo_url = nonce_data[nonce]["repo_url"]

        # --- CASE 1️⃣: New nonce → create new repo ---
        if not existing_repo_url:
            print(f"🆕 New nonce detected: creating repo for task {task}")
        
            checks_section=""
            if data.get("checks"):
                checks_section=f"""
                ### EVALUATION CHECKS ###
                The following checks describe how your generated application will be automatically evaluated.
                You MUST implement all features, behaviors, and conditions implied by these checks.
                Do not rewrite or repeat these checks in the output.
                Use them only to guide your implementation and ensure the final app passes them successfully.
                {chr(10).join([f"- {check}" for check in data['checks']])}
                """
            
            attach=""
            if attachments:
                attachment_details="\n".join(
                    [f"- {att['name']}: {att['url']}" for att in attachments]
                )
                attach=f"""
                ### ATTACHMENTS ###
                The following sample files are provided as reference inputs for your task.

                {attachment_details}

                - Each attachment URL is base64-encoded or embedded data. 
                - Use these attachments only when the task brief does NOT provide a direct input (e.g., a ?url parameter). 
                - If the task brief mentions its own file or input, prefer that instead.
                - Do NOT reproduce the attachment content in your output — just reference it logically in your generated code.
                - If the app requires an image or data source, default to these attachments where applicable.
                """

            prompt = f"""
            You are an expert full-stack web developer with years of experience building clean, production-grade applications.

            Based on the following task brief, generate **only the complete and functional code** required — typically limited to:
            - `index.html`
            - `styles.css`
            - `script.js`
            - `README.md`

            Do NOT create any extra files unless they are explicitly required by the task.

            ### TASK ###
            {brief}
            {attach}
            {checks_section}

            ### README REQUIREMENTS ###
            The `README.md` file must:
            1. Be a **pure Markdown file** (not HTML).
            2. Contain a **professional and structured** documentation including:
            - Project Overview
            - Features
            - Setup Instructions
            - Usage Guide
            - Code Structure
            - License (MIT)
            3. Use **Markdown syntax only** — no HTML or JavaScript.
            4. Be saved as a file named exactly `README.md`.

            ### OUTPUT RULES ###
            - Output **only code blocks**, nothing else.
            - Each file must start with ```filename.ext and end with ``` exactly.
            - Filenames must be one of: `index.html`, `styles.css`, `script.js`, or `README.md`.
            - Do NOT output or reference any other filenames (like file_5.html, file_6.html, etc.).
            - Do NOT include explanations or text outside the code blocks.
            - Keep all filenames lowercase and consistent.

            """


            url= "https://aipipe.org/openai/v1/chat/completions"
            headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            }

            payload = {
            "model": "anthropic/claude-sonnet-4.5",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
            }

            response = httpx.post(url, json=payload, headers=headers, timeout=600)
            response.raise_for_status()
            data = response.json()


            generated_code = data["choices"][0]["message"]["content"].strip()

            generated_files = extract_code_blocks(generated_code,brief)

            
            
            # pushing the code in github

            result=push_to_github(task, brief, generated_files,nonce)

            # Handle name conflict gracefully
            if isinstance(result,dict) and result.get("error")=="name_conflict":
                return JSONResponse(
                    {"error": result['message']},
                    status_code=409
                )
            
            repo_url, pages_url,commit_sha=result
            
            # notify the evaluation server about the deployment
            if evaluation_url:
                payload1 = {
                    "email": email,
                    "task": task,
                    "round": round_num,
                    "nonce": nonce,
                    "pages_url": pages_url,
                    "repo_url":repo_url,
                    "commit_sha":commit_sha
                }

                headers = {"Content-Type": "application/json"}
                delay = 1
                for attempt in range(5):
                    try:
                        response = httpx.post(evaluation_url, json=payload1, headers=headers, timeout=60)
                        if response.status_code == 200:
                            print(f"✅ Successfully notified evaluation server: {evaluation_url}")
                            break
                        else:
                            print(f"⚠️ Server responded with {response.status_code}, retrying...")
                    except Exception as e:
                        print(f"⚠️ Notification attempt {attempt+1} failed: {e}")
                    time.sleep(delay)
                    delay *= 2  # exponential backoff
            
            # 3️⃣ Respond OK
            return {"status": "200 ok", 
                    "message": f"Task received successfully. Notification sent to {evaluation_url}",
                    "pages_url": pages_url,
                }
        
        
        
        
        # --- CASE 2️⃣: Existing nonce → update existing repo ---
        else:
            print(f"🔁 Existing nonce found. Updating repo: {existing_repo_url}")
            existing_files = get_existing_code_from_repo(existing_repo_url)

            checks_section=""
            if data.get("checks"):
                checks_section=f"""
                ### EVALUATION CHECKS ###
                The following checks describe how your generated application will be automatically evaluated.
                You MUST implement all features, behaviors, and conditions implied by these checks.
                Do not rewrite or repeat these checks in the output.
                Use them only to guide your implementation and ensure the final app passes them successfully.
                {chr(10).join([f"- {check}" for check in data['checks']])}
                """
            
            attach=""
            if attachments:
                attachment_details="\n".join(
                    [f"- {att['name']}: {att['url']}" for att in attachments]
                )
                attach=f"""
                ### ATTACHMENTS ###
                The following sample files are provided as reference inputs for your task.

                {attachment_details}

                - Each attachment URL is base64-encoded or embedded data. 
                - Use these attachments only when the task brief does NOT provide a direct input (e.g., a ?url parameter). 
                - If the task brief mentions its own file or input, prefer that instead.
                - Do NOT reproduce the attachment content in your output — just reference it logically in your generated code.
                - If the app requires an image or data source, default to these attachments where applicable.
                """
            
            prompt = f"""
            You are an experienced full-stack web developer responsible for updating an existing production-grade web application.

            Your goal is to **modify only the necessary parts** of the existing codebase based on the update instructions below — without rebuilding the project or changing its structure.

            ### EXISTING CODEBASE ###
            Below are all files currently in the application.
            Each file is separated by its filename header.
            Review all code carefully before making changes.

            {chr(10).join([f"--- {name} ---\n{code}" for name, code in existing_files.items()])}

            ### UPDATE INSTRUCTIONS ###
            {brief}
            {attach}
            {checks_section}

            ### RULES ###
            - Do NOT create new files unless the update instructions explicitly require it.
            - Use the **exact same filenames** as shown above.
            - Preserve all existing functionality, layout, and design unless specifically asked to modify.
            - Keep the **project structure identical** (same folders, same file names).
            - Update only the **relevant sections** of each file — do not rewrite the entire file if not needed.
            - Ensure the updated code remains clean, functional, and error-free.
            - Always update the `README.md` file to accurately describe the new changes and reflect the current version.
            - Keep the README.md strictly in Markdown format (no HTML or JS).
            - Return the output as **only valid code blocks**:
            - Each code block must start with ```filename.ext and end with ``` exactly.
            - Do NOT include any text, explanation, or markdown outside code blocks.
            - Filenames must match exactly one of the existing ones (no `file_5.html`, `update.js`, etc.).
            - Maintain consistent indentation and formatting.
            - Ensure compatibility between updated files (e.g., JS selectors match HTML elements).

            """

            payload={
                "model":"anthropic/claude-sonnet-4.5",
                "messages":[
                    {"role":"system","content":"You are a professional web developer with years of experiences."},
                    {"role":"user","content":prompt}
                ]
            }
            url= "https://aipipe.org/openai/v1/chat/completions"
            headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            }
            response = httpx.post(url, json=payload, headers=headers, timeout=600)
            response.raise_for_status()
            data = response.json()

            generated_code = data["choices"][0]["message"]["content"].strip()
            generated_files = extract_code_blocks(generated_code, brief)

            repo_url, pages_url,commit_sha = push_to_github_update(task, brief, generated_files,nonce)

            
            # notify the evaluation server about the deployment
            if evaluation_url:
                payload1 = {
                    "email": email,
                    "task": task,
                    "round": round_num,
                    "nonce": nonce,
                    "pages_url": pages_url,
                    "repo_url":repo_url,
                    "commit_sha":commit_sha
                }

                headers = {"Content-Type": "application/json"}
                delay = 1
                for attempt in range(5):
                    try:
                        response = httpx.post(evaluation_url, json=payload1, headers=headers, timeout=60)
                        if response.status_code == 200:
                            print(f"✅ Successfully notified evaluation server: {evaluation_url}")
                            break
                        else:
                            print(f"⚠️ Server responded with {response.status_code}, retrying...")
                    except Exception as e:
                        print(f"⚠️ Notification attempt {attempt+1} failed: {e}")
                    time.sleep(delay)
                    delay *= 2  # exponential backoff
            
            # 3️⃣ Respond OK
            return {"status": "200 OK", 
                    "message": f"Task received successfully. Notification sent to {evaluation_url}",
                    "pages_url": pages_url,
                }
        
        # Save nonce tracking
        """nonce_data[nonce] = {"task": task, "repo_url": repo_url, "pages_url": pages_url}
            with open(NONCE_TRACKER_FILE, "w", encoding="utf-8") as f:
                json.dump(nonce_data, f, indent=2)

            return repo_url, pages_url,commit_sha"""


    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    


# pushing the genarated code file to GIthub
def push_to_github(task, brief, generated_files, nonce):
    """
    Creates a new GitHub repo, uploads generated files, enables Pages, 
    and returns (repo_url, pages_url, commit_sha).
    """
    try:
        print(f"\n🚀 Starting GitHub repo creation for task: {task}")

        g = Github(GITHUB_TOKEN)
        user = g.get_user()
        repo_name = f"{task}"
        #safe_description = " ".join(brief.split())[:300]

        # --- Create repo ---
        repo = user.create_repo(
            name=repo_name,
            #description=f"Auto-generated project: {safe_description}",
            private=False
        )
        repo_url = repo.html_url
        print(f"✅ Created new repo: {repo_url}")

        commit_sha = None

        # --- Upload generated files ---
        for filename, content in generated_files.items():
            result = repo.create_file(
                path=filename,
                message=f"Add {filename}",
                content=content,
                branch="main"
            )
            commit_sha = result["commit"].sha
            print(f"✅ Uploaded {filename}")

        # --- Add LICENSE (MIT) ---
        license_text = f"""MIT License

Copyright (c) {time.strftime('%Y')} {GITHUB_USERNAME}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
"""
        result = repo.create_file("LICENSE", "Add LICENSE", license_text, branch="main")
        commit_sha = result["commit"].sha
        print(f"✅ Added LICENSE")

        # --- Enable GitHub Pages ---
        pages_api = f"https://api.github.com/repos/{GITHUB_USERNAME}/{repo_name}/pages"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        data = {"source": {"branch": "main", "path": "/"}}
        httpx.post(pages_api, headers=headers, json=data)
        pages_url = f"https://{GITHUB_USERNAME}.github.io/{repo_name}/"
        print(f"🌐 GitHub Pages enabled at: {pages_url}")

        # --- Update nonce tracker ---
        if NONCE_TRACKER_FILE.exists():
            with open(NONCE_TRACKER_FILE, "r", encoding="utf-8") as f:
                nonce_data = json.load(f)
        else:
            nonce_data = {}

        nonce_data[nonce] = {"task": task, "repo_url": repo_url, "pages_url": pages_url}
        with open(NONCE_TRACKER_FILE, "w", encoding="utf-8") as f:
            json.dump(nonce_data, f, indent=2)

        print("✅ Repo successfully created and tracked.")
        return repo_url, pages_url, commit_sha
    
    except GithubException as e:
        if e.status == 422 and "name already exists" in str(e):
            # Safety fallback for duplicate repo creation
            print("❌ Repo creation failed: name already exists.")
            return {
                "error": "name_conflict",
                "message": "Name the task something different — this repo already exists."
            }
        else:
            print(f"❌ GitHub operation failed: {e}")
            raise

    except Exception as e:
        print(f"❌ Error in push_to_github: {e}")
        return None, None, None




def push_to_github_update(task, brief, generated_files, nonce):
    """
    Updates an existing GitHub repo (based on nonce).
    Fetches the repo, updates existing files, adds new ones if needed,
    and returns (repo_url, pages_url, commit_sha).
    """
    try:
        print(f"\n🔁 Updating repo for task: {task}")

        # --- Load nonce tracker ---
        with open(NONCE_TRACKER_FILE, "r", encoding="utf-8") as f:
            nonce_data = json.load(f)

        existing_repo_url = nonce_data[nonce]["repo_url"]
        pages_url = nonce_data[nonce]["pages_url"]
        repo_name = existing_repo_url.split("/")[-1]

        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(f"{GITHUB_USERNAME}/{repo_name}")
        commit_sha = None

        # --- Update or add files ---
        for filename, content in generated_files.items():
            try:
                existing = repo.get_contents(filename)
                result = repo.update_file(
                    path=filename,
                    message=f"Update {filename}",
                    content=content,
                    sha=existing.sha,
                    branch="main"
                )
                commit_sha = result["commit"].sha
                print(f"✅ Updated {filename}")
            except Exception:
                result = repo.create_file(
                    path=filename,
                    message=f"Add new file {filename}",
                    content=content,
                    branch="main"
                )
                commit_sha = result["commit"].sha
                print(f"🆕 Added new file {filename}")

        print(f"✅ Repo updated successfully: {existing_repo_url}")
        print(f"🌐 GitHub Pages URL: {pages_url}")

        return existing_repo_url, pages_url, commit_sha

    except Exception as e:
        print(f"❌ Error in push_to_github_update: {e}")
        return None, None, None
        



# extract only the code blocks and no starter and ending chit chat form the llm
def extract_code_blocks(llm_output: str,brief: str):
    """
    Extracts only code content from the LLM output.
    Returns a dictionary {filename: code}.
    """
    code_blocks = re.findall(r"```(?:([\w\.\-\/]+)?\n)?(.*?)```", llm_output, re.DOTALL)
    files = {}
    file_counter = 1
    for meta, code in code_blocks:
        filename = meta.strip() if meta and "." in meta else f"file_{file_counter}.html"
        files[filename] = code.strip()
        file_counter += 1
    # If no code blocks detected, treat full output as one HTML file
    if not files and llm_output.strip():
        brief_lower = brief.lower()

        if "javascript" in brief_lower or "js" in brief_lower:
            default_name = "script.js"
        elif "css" in brief_lower or "style" in brief_lower:
            default_name = "style.css"
        elif "python" in brief_lower or "py" in brief_lower:
            default_name = "app.py"
        elif "html" in brief_lower or "web page" in brief_lower or "website" in brief_lower:
            default_name = "index.html"
        else:
            default_name = "output.txt"  # generic fallback

        files[default_name] = llm_output.strip()

    return files



# get the existing files from the repo.
def get_existing_code_from_repo(repo_url):
    g = Github(GITHUB_TOKEN)
    repo_name = repo_url.split("/")[-1]
    repo = g.get_repo(f"{GITHUB_USERNAME}/{repo_name}")
    existing_files = {}

    def fetch_contents(path=""):
        contents = repo.get_contents(path)
        for file in contents:
            if file.type == "dir":
                fetch_contents(file.path)  # recursive call
            else:
                existing_files[file.path] = file.decoded_content.decode("utf-8")

    fetch_contents()

    return existing_files
