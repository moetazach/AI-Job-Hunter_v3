import os
import random
import json
import re
import time
import html
import requests
from groq import Groq
from ddgs import DDGS

# استخدام نموذج Llama 3.3 70B السريع والعملاق من Groq
GROQ_MODEL = "llama-3.3-70b-versatile"

MAX_JOBS_TO_EVALUATE = 64  # total candidate jobs considered per run
EVAL_BATCH_SIZE = 8        # jobs sent to Groq per evaluation call

RESUME_SUMMARY = """
Moatez Achouri — Junior SOC Analyst / Cybersecurity Analyst / Blue Team Practitioner.
Doha, Qatar. Open to relocation and remote work. Available immediately.

Core skills: SOC Tier 1 alert triage/prioritization/escalation, log analysis and
cross-event correlation, incident response fundamentals, threat detection and
proactive threat hunting, MITRE ATT&CK framework, IOC analysis and threat intel
interpretation, network traffic monitoring and anomaly detection, vulnerability
and risk assessment fundamentals.

Tools: Wireshark, Nmap, Nuclei, VirusTotal, Shodan, GreyNoise, Microsoft Defender
for Endpoint, Elastic Security, SIEM fundamentals, Kali Linux, Windows/Windows
Server, Python (log parsing & automation), Bash scripting.

Networking/security concepts: TCP/IP, DNS, HTTP/HTTPS, Firewalls, IDS/IPS,
vulnerability assessment, basic malware analysis.

Certifications (2026): Cisco Junior Cybersecurity Analyst Career Path, Cisco
Cybersecurity Defense Analyst Pathway Exam, HackLearn Applied Cybersecurity
Training. Built a home SOC lab in VMware: 60+ Wireshark packet capture analyses,
Nmap/Nuclei scans, 40+ simulated alerts triaged and mapped to MITRE ATT&CK,
incident reports written.

Education: Senior Technician Diploma in Development of Intelligent Systems and
Industrial Computing (2020); Bac+2 in Computer Networking, ISET Tozeur (2017).
No prior professional cybersecurity work experience — actively seeking a first
junior/entry-level role or internship.
"""

SEARCH_QUERIES = [
    "junior SOC analyst remote OR Gulf OR Canada OR Europe",
    "SOC analyst tier 1 entry level hiring",
    "junior blue team analyst remote",
    "junior incident response analyst remote",
    "junior threat hunter entry level",
    "junior threat intelligence analyst remote",
    "junior network security engineer remote",
    "junior vulnerability analyst remote",
    "entry level SIEM analyst remote",
    "junior IT security analyst Gulf Europe",
    "cybersecurity intern python bash scripting",
    "network administrator junior security",
    "junior penetration tester entry level remote",
    "graduate cybersecurity program Gulf Europe Canada",
    "junior MITRE ATT&CK analyst remote",
]

SECURITY_KEYWORDS = [
    "cyber", "security", "soc", "siem", "threat", "vulnerabilit",
    "penetration", "incident response", "network security", "firewall",
    "malware", "iso 27001", "grc", "compliance", "infosec", "blue team",
    "ioc", "mitre", "log analysis", "threat hunt", "threat intel"
]

EXCLUDE_TITLE_WORDS = [
    "sales", "accountant", "nurse", "legal", "hr manager", "director",
    "senior", "lead", "principal", "marketing", "business development",
    "content reviewer", "patient care", "recruiter", "account executive"
]


def send_telegram_message(message):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print("[-] Telegram credentials missing!")
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        print(f"[*] Telegram Response: {res.status_code}")
        if res.status_code != 200:
            print(f"[-] Telegram error body: {res.text}")
            return False
        return True
    except Exception as e:
        print(f"Telegram Error: {e}")
        return False


def is_aggregator_result(title, url):
    t = title.lower()
    aggregator_title_patterns = [
        r"\d+\s*vacanc", r"\d+\s*jobs?\b", r"jobs? in\b.*-\s*(indeed|linkedin|glassdoor|built in)",
        r"^jobs?\b", r"job search", r"search results", r"interview questions for",
        r"salary (guide|report)", r"career (path|guide)",
    ]
    if any(re.search(p, t) for p in aggregator_title_patterns):
        return True
    aggregator_domains = ["indeed.com/q-", "indeed.com/jobs?q=", "/jobs/search", "/job-search"]
    if any(d in url.lower() for d in aggregator_domains):
        return True
    return False


def fetch_ddgs_jobs():
    jobs = []
    skipped_aggregators = 0
    try:
        with DDGS() as ddgs:
            for q in SEARCH_QUERIES:
                print(f"[*] DDGS searching: {q}")
                try:
                    results = list(ddgs.text(q, max_results=6))
                except Exception as qe:
                    print(f"[-] DDGS query failed for '{q}': {qe}")
                    continue
                for r in results:
                    url = r.get("href", "")
                    title = r.get("title", "")
                    body = r.get("body", "")
                    if not url or not title:
                        continue
                    if is_aggregator_result(title, url):
                        skipped_aggregators += 1
                        continue
                    jobs.append({
                        "title": title,
                        "company": "Security Employer",
                        "location": "Global / Remote / Regional",
                        "description": body if body else title,
                        "url": url,
                        "source": "DDGS Search"
                    })
    except Exception as e:
        print(f"[-] DDGS Error: {e}")
    print(f"[*] DDGS: {len(jobs)} jobs ({skipped_aggregators} aggregator pages skipped)")
    return jobs


def fetch_remotive_jobs():
    jobs = []
    try:
        res = requests.get("https://remotive.com/api/remote-jobs?limit=100", timeout=10)
        if res.status_code == 200:
            for item in res.json().get("jobs", []):
                jobs.append({
                    "title": item.get("title"),
                    "company": item.get("company_name", "Remotive"),
                    "location": "Remote",
                    "description": item.get("description", item.get("title")),
                    "url": item.get("url"),
                    "source": "Remotive API"
                })
    except Exception as e:
        print(f"[-] Remotive Error: {e}")
    return jobs


def fetch_remoteok_jobs():
    jobs = []
    try:
        headers = {"User-Agent": "Mozilla/5.0 (JobHunterBot)"}
        res = requests.get("https://remoteok.com/api", headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            for item in data:
                if not isinstance(item, dict) or "position" not in item:
                    continue
                jobs.append({
                    "title": item.get("position"),
                    "company": item.get("company", "RemoteOK"),
                    "location": "Remote",
                    "description": item.get("description", item.get("position", "")),
                    "url": item.get("url") or f"https://remoteok.com{item.get('slug', '')}",
                    "source": "RemoteOK API"
                })
    except Exception as e:
        print(f"[-] RemoteOK Error: {e}")
    return jobs


def fetch_arbeitnow_jobs():
    jobs = []
    try:
        res = requests.get("https://www.arbeitnow.com/api/job-board-api", timeout=10)
        if res.status_code == 200:
            for item in res.json().get("data", []):
                jobs.append({
                    "title": item.get("title"),
                    "company": item.get("company_name", "Arbeitnow"),
                    "location": "Remote" if item.get("remote") else item.get("location", "N/A"),
                    "description": item.get("description", item.get("title", "")),
                    "url": item.get("url"),
                    "source": "Arbeitnow API"
                })
    except Exception as e:
        print(f"[-] Arbeitnow Error: {e}")
    return jobs


def fetch_jobicy_jobs():
    jobs = []
    try:
        res = requests.get("https://jobicy.com/api/v2/remote-jobs?count=50", timeout=10)
        if res.status_code == 200:
            for item in res.json().get("jobs", []):
                jobs.append({
                    "title": item.get("jobTitle", item.get("title", "")),
                    "company": item.get("companyName", "Jobicy"),
                    "location": "Remote",
                    "description": item.get("jobExcerpt", item.get("jobDescription", "")),
                    "url": item.get("url"),
                    "source": "Jobicy API"
                })
    except Exception as e:
        print(f"[-] Jobicy Error: {e}")
    return jobs


def fetch_himalayas_jobs():
    jobs = []
    try:
        res = requests.get("https://himalayas.app/api/jobs?limit=100", timeout=10)
        if res.status_code == 200:
            data = res.json()
            items = data.get("jobs", []) if isinstance(data, dict) else data
            for item in items:
                if not isinstance(item, dict):
                    continue
                jobs.append({
                    "title": item.get("title"),
                    "company": item.get("companyName", item.get("company", "Himalayas")),
                    "location": "Remote",
                    "description": item.get("description", item.get("excerpt", item.get("title", ""))),
                    "url": item.get("applicationLink") or item.get("url"),
                    "source": "Himalayas API"
                })
    except Exception as e:
        print(f"[-] Himalayas Error: {e}")
    return jobs


def fetch_cybersecurity_jobs():
    all_jobs = []

    # DDGS search
    all_jobs.extend(fetch_ddgs_jobs())

    # General APIs with security-keyword filter
    general_sources = (
        fetch_remotive_jobs()
        + fetch_remoteok_jobs()
        + fetch_arbeitnow_jobs()
        + fetch_jobicy_jobs()
        + fetch_himalayas_jobs()
    )

    kept = 0
    for job in general_sources:
        title = (job.get("title") or "")
        desc = (job.get("description") or "")
        blob = (title + " " + desc).lower()
        if any(k in blob for k in SECURITY_KEYWORDS):
            all_jobs.append(job)
            kept += 1

    print(f"[*] General job boards: {kept}/{len(general_sources)} passed keyword filter")

    # Dedup by URL
    seen_urls = set()
    deduped = []
    for job in all_jobs:
        url = job.get("url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            deduped.append(job)

    print(f"[*] Total unique jobs collected: {len(deduped)}")
    return deduped


def ai_batch_evaluate(jobs_batch):
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("[-] GROQ_API_KEY missing — skipping AI evaluation batch.")
        return {}

    listing = ""
    for i, job in enumerate(jobs_batch):
        desc = (job.get("description") or "")[:400]
        listing += f"\n[{i}] Title: {job['title']} | Company: {job.get('company','')}\nDescription: {desc}\n"

    prompt = f"""
    CANDIDATE RESUME:
    {RESUME_SUMMARY}

    Below is a numbered list of {len(jobs_batch)} job postings. For EACH one,
    decide if it's a realistic, worthwhile application for this entry-level/junior candidate.

    RULES:
    1. REJECT (match=false) ONLY if the job is explicitly Senior, Lead, Principal, Manager, Director, or requires 5+ years of experience, or is unrelated (Sales, HR, Marketing).
    2. ACCEPT (match=true) if it's Entry-Level, Junior, Intern, Tier 1, or asks for 0-2 years experience in SOC, Blue Team, Incident Response, Log Analysis, Network Security, Vulnerability Assessment, or SIEM.

    JOB POSTINGS:
    {listing}

    Return ONLY a raw JSON array of objects with no markdown fences:
    [
      {{
        "index": 0,
        "match": true,
        "match_percent": 85,
        "fit_overview": "Good entry-level fit for SOC and network monitoring.",
        "cv_tip": "Highlight home SOC lab and Wireshark skills."
      }}
    ]
    """

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        
        text = response.choices[0].message.content.strip()
        text = re.sub(r"^```(json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
        
        # Extract JSON array safely
        json_match = re.search(r'\[.*\]', text, re.DOTALL)
        if json_match:
            text = json_match.group(0)

        data = json.loads(text)
        
        results = {}
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "index" in item:
                    results[item["index"]] = item
        return results

    except Exception as e:
        print(f"[-] Groq AI Error: {e}")
        return {}


def main():
    print("=== Groq Llama-3.3 AI Job Hunter Started ===")

    all_jobs = fetch_cybersecurity_jobs()
    print(f"[*] Total collected jobs to evaluate: {len(all_jobs)}")

    if not all_jobs:
        send_telegram_message("⚠️ Security Job Hunter ran, but no jobs were found.")
        return

    random.shuffle(all_jobs)
    all_jobs = all_jobs[:MAX_JOBS_TO_EVALUATE]
    all_jobs = [j for j in all_jobs if not any(w in (j.get("title") or "").lower() for w in EXCLUDE_TITLE_WORDS)]
    print(f"[*] Evaluating {len(all_jobs)} jobs with Groq AI in batches of {EVAL_BATCH_SIZE}")

    matched_jobs = []
    for start in range(0, len(all_jobs), EVAL_BATCH_SIZE):
        if len(matched_jobs) >= 5:
            break
        batch = all_jobs[start:start + EVAL_BATCH_SIZE]
        results = ai_batch_evaluate(batch)
        for i, job in enumerate(batch):
            r = results.get(i)
            if r and r.get("match"):
                job["match_percent"] = r.get("match_percent", 0)
                job["evaluation"] = (
                    f"MATCH_PERCENT: {r.get('match_percent', 0)}%\n"
                    f"ASSESSMENT:\n"
                    f"- {r.get('fit_overview', '')}\n"
                    f"- {r.get('cv_tip', '')}"
                )
                matched_jobs.append(job)
                print(f"[+] Matched: {job['title']} ({job.get('match_percent', 0)}%)")
                if len(matched_jobs) >= 5:
                    break
        time.sleep(1)

    if not matched_jobs:
        print("[-] No matching cybersecurity entry-level jobs found.")
        send_telegram_message("⚠️ Security Job Hunter ran, but all jobs were filtered out by AI match.")
        return

    message_blocks = []
    for i, job in enumerate(matched_jobs, 1):
        block = (
            f"<b>{i}. {html.escape(str(job['title']))}</b>\n"
            f"🏢 Company: {html.escape(str(job['company']))}\n"
            f"📍 Location: {html.escape(str(job['location']))}\n"
            f"🌐 Source: {html.escape(str(job['source']))}\n"
            f"🤖 AI Match: {job.get('match_percent', 0)}%\n"
            f'🔗 <a href="{html.escape(str(job["url"]), quote=True)}">Apply Here</a>\n\n'
        )
        message_blocks.append(block)

    header = "🛡️ <b>Cybersecurity & SOC Job Opportunities (Groq Powered)</b> 🛡️\n\n"
    chunks = []
    current = header
    for block in message_blocks:
        if len(current) + len(block) > 3800:
            chunks.append(current)
            current = ""
        current += block
    if current.strip():
        chunks.append(current)

    all_sent = True
    for chunk in chunks:
        if not send_telegram_message(chunk):
            all_sent = False

    if all_sent:
        print("[+] Results successfully sent to Telegram!")
    else:
        print("[-] Telegram delivery failed.")


if __name__ == "__main__":
    main()
