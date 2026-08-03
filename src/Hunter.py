
import os
import re
import json
import html
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from ddgs import DDGS

ROOT = Path(__file__).resolve().parents[1]
P = json.loads((ROOT / "profile.json").read_text(encoding="utf-8"))
QUERIES = json.loads((ROOT / "search_queries.json").read_text(encoding="utf-8"))
STATE = ROOT / "data" / "seen_jobs.json"

S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 AI-Job-Hunter/3.1 public-job-discovery"
})

SEC = [
    "soc","security operations","cybersecurity","cyber security",
    "information security","siem","splunk","sentinel","elastic security",
    "incident response","threat detection","threat intelligence",
    "network security","firewall","ids","ips","edr","xdr","log analysis",
    "security monitoring","blue team","vulnerability","security incident",
    "wireshark","packet analysis"
]

BAD = [
    "sales","business development","marketing","accountant","accounting",
    "nurse","patient care","medical assistant","content reviewer",
    "data labeling","customer success","customer service","recruiter",
    "human resources","legal","lawyer","finance","copywriter","designer",
    "teacher","caregiver"
]

JUN = [
    "junior","entry level","entry-level","graduate","trainee","intern",
    "internship","apprentice","associate","l1","tier 1","early career",
    "0-1 year","0-2 years","1-2 years","1 year","2 years"
]

HIGHEXP = [
    "3+ years","4+ years","5+ years","6+ years","7+ years","8+ years",
    "10+ years","3 years","4 years","5 years","6 years","7 years",
    "8 years","10 years"
]


def norm(x):
    return re.sub(r"[^a-z0-9+#.]+", " ", (x or "").lower()).strip()


def clean(x):
    x = html.unescape(x or "")
    x = re.sub(r"<script.*?</script>|<style.*?</style>", " ",
               x, flags=re.I | re.S)
    x = re.sub(r"<[^>]+>", " ", x)
    return re.sub(r"\s+", " ", x).strip()


def load_seen():
    try:
        return set(json.loads(STATE.read_text()).get("urls", []))
    except Exception:
        return set()


def save_seen(urls):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(
        json.dumps({"urls": sorted(urls)[-15000:]}, indent=2),
        encoding="utf-8"
    )


def security_score(job):
    t = norm(job.get("title", "") + " " + job.get("description", ""))
    return sum(1 for x in SEC if x in t)


def clearly_bad(job):
    return any(x in norm(job.get("title", "")) for x in BAD)


def web_search():
    out = {}
    try:
        with DDGS() as ddgs:
            for q in QUERIES:
                print("[search]", q)
                try:
                    results = ddgs.text(q, max_results=8)
                    for r in results:
                        u = r.get("href") or r.get("url")
                        if not u or u in out:
                            continue
                        out[u] = {
                            "title": r.get("title", ""),
                            "company": "Unknown",
                            "location": "Unknown",
                            "description": r.get("body", ""),
                            "url": u,
                            "source": "Web/" + urlparse(u).netloc
                        }
                except Exception as e:
                    print("search error:", e)
                time.sleep(0.25)
    except Exception as e:
        print("DDGS error:", e)
    return list(out.values())


def api_jobs():
    out = []

    # Arbeitnow
    try:
        for page in range(1, 4):
            r = S.get(
                "https://www.arbeitnow.com/api/job-board-api",
                params={"page": page}, timeout=20
            )
            r.raise_for_status()
            for x in r.json().get("data", []):
                out.append({
                    "title": x.get("title", ""),
                    "company": x.get("company_name", "Unknown"),
                    "location": x.get("location", ""),
                    "description": clean(x.get("description", "")),
                    "url": x.get("url", ""),
                    "source": "Arbeitnow",
                    "visa": x.get("visa_sponsorship", False)
                })
    except Exception as e:
        print("Arbeitnow:", e)

    # Remotive: security-focused searches instead of unrelated software fallback
    for q in [
        "cybersecurity", "SOC analyst", "security analyst",
        "information security", "SIEM", "incident response",
        "network security", "vulnerability"
    ]:
        try:
            r = S.get(
                "https://remotive.com/api/remote-jobs",
                params={"search": q, "limit": 100}, timeout=20
            )
            r.raise_for_status()
            for x in r.json().get("jobs", []):
                out.append({
                    "title": x.get("title", ""),
                    "company": x.get("company_name", "Unknown"),
                    "location": x.get("candidate_required_location", "Remote"),
                    "description": clean(x.get("description", "")),
                    "url": x.get("url", ""),
                    "source": "Remotive",
                    "visa": False
                })
        except Exception as e:
            print("Remotive:", e)

    # Jobicy
    for geo in ["europe", "canada", "australia", "uk", "usa", "emea"]:
        try:
            r = S.get(
                "https://jobicy.com/api/v2/remote-jobs",
                params={"count": 100, "geo": geo, "industry": "cybersecurity"},
                timeout=20
            )
            r.raise_for_status()
            for x in r.json().get("jobs", []):
                out.append({
                    "title": x.get("jobTitle", ""),
                    "company": x.get("companyName", "Unknown"),
                    "location": x.get("jobGeo", "Remote"),
                    "description": clean(
                        x.get("jobDescription") or x.get("jobExcerpt", "")
                    ),
                    "url": x.get("url", ""),
                    "source": "Jobicy",
                    "visa": False
                })
        except Exception as e:
            print("Jobicy:", e)

    # RemoteOK
    try:
        r = S.get("https://remoteok.com/api", timeout=20)
        r.raise_for_status()
        data = r.json()
        for x in data[1:] if isinstance(data, list) else []:
            tags = " ".join(x.get("tags") or [])
            out.append({
                "title": x.get("position", ""),
                "company": x.get("company", "Unknown"),
                "location": x.get("location", "Remote"),
                "description": clean(x.get("description", "")) + " " + tags,
                "url": x.get("url", ""),
                "source": "RemoteOK",
                "visa": False
            })
    except Exception as e:
        print("RemoteOK:", e)

    return out


def enrich(job):
    try:
        r = S.get(job["url"], timeout=12)
        if r.ok:
            page = clean(r.text)
            job["description"] = (
                job.get("description", "") + " " + page[:18000]
            ).strip()
    except Exception:
        pass
    return job


def fallback_match(job):
    t = norm(job["title"] + " " + job["description"])
    sec = security_score(job)
    junior = any(x in t for x in JUN)
    senior_reasonable = (
        "senior" in norm(job["title"])
        and not any(x in t for x in HIGHEXP)
    )
    if sec >= 2 and (junior or senior_reasonable):
        return {
            "decision": "MATCH",
            "match": min(88, 50 + sec * 5 + (15 if junior else 5)),
            "level": "junior/intern" if junior else "senior-title-but-reasonable",
            "experience": "unclear",
            "remote": "yes" if "remote" in t else "unknown",
            "sponsorship": "yes" if job.get("visa") else "unknown",
            "freshness": "unknown",
            "reason": "Security role with junior/early-career or potentially reasonable requirements.",
            "cv_tip": "Highlight your Home SOC Lab, alert triage, Wireshark, Nmap/Nuclei and MITRE ATT&CK."
        }
    return None


def ai_match(job):
    """
    Uses Gemini 2.5 Flash through the REST API.

    Important: the previous version created a new google-genai Client
    inside every job evaluation. That caused:
        Cannot send a request, as the client has been closed.

    REST avoids that SDK lifecycle problem.
    """
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return fallback_match(job)

    prompt = """You are a STRICT cybersecurity job matching agent.

Candidate:
%s

JOB TITLE: %s
COMPANY: %s
LOCATION: %s
SOURCE: %s
JOB DESCRIPTION:
%s

Rules:
1. MATCH Junior, Entry Level, Graduate, Trainee, Internship, Apprenticeship,
   Associate, L1/Tier 1 and Remote cybersecurity/security roles.
2. Senior/Sr is NOT automatically rejected. Keep it when actual relevant
   experience is <=2 years, equivalent experience is accepted, or requirements
   are realistically attainable.
3. Reject clearly 3+ years of required relevant experience.
4. Reject unrelated jobs such as sales, marketing, HR, accounting, medical,
   customer service, data labeling or content moderation.
5. Never invent sponsorship. "yes" only if explicitly stated; otherwise "unknown".
6. Home SOC Lab is practical hands-on experience, not paid SOC employment.
7. Prioritize SOC, SIEM, alert triage, logs, incident response, threat
   detection, network security, vulnerability analysis, blue team and security automation.
8. Return ONLY valid JSON.

{
 "decision":"MATCH or REJECT",
 "match":0,
 "level":"intern/junior/associate/senior-title-but-reasonable",
 "experience":"0-1/1-2/2-3/3+/unclear",
 "remote":"yes/no/unknown",
 "sponsorship":"yes/no/unknown",
 "freshness":"new/recent/old/unknown",
 "reason":"one sentence",
 "cv_tip":"one sentence"
}
""" % (
        json.dumps(P, ensure_ascii=False),
        job["title"],
        job["company"],
        job["location"],
        job["source"],
        job["description"][:12000]
    )

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 500,
            "responseMimeType": "application/json"
        }
    }

    for attempt in range(4):
        try:
            r = S.post(
                endpoint,
                params={"key": key},
                json=payload,
                timeout=45
            )

            if r.status_code == 429:
                wait = min(60, 10 * (attempt + 1))
                print("Gemini 429; sleeping", wait, "seconds")
                time.sleep(wait)
                continue

            if r.status_code >= 500:
                wait = min(30, 5 * (attempt + 1))
                print("Gemini server error", r.status_code,
                      "; sleeping", wait, "seconds")
                time.sleep(wait)
                continue

            if not r.ok:
                print("Gemini HTTP error:", r.status_code, r.text[:600])
                return None

            data = r.json()
            parts = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [])
            )
            raw = "".join(p.get("text", "") for p in parts).strip()
            raw = re.sub(r"^```json\s*|\s*```$", "", raw,
                         flags=re.I).strip()

            result = json.loads(raw)
            if (
                result.get("decision") == "MATCH"
                and int(result.get("match", 0)) >= 60
            ):
                return result
            return None

        except Exception as e:
            if attempt < 3:
                wait = 5 * (attempt + 1)
                print("Gemini retry:", e, "; sleeping", wait, "seconds")
                time.sleep(wait)
            else:
                print("Gemini failed:", e)

    return None


def send_telegram(jobs):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        raise RuntimeError("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")

    text = "🛡️ <b>AI Job Hunter v3.1 — New Matches</b>\n\n"

    for i, job in enumerate(jobs, 1):
        e = job["evaluation"]
        block = (
            f"<b>{i}. {html.escape(job['title'])}</b>\n"
            f"🏢 {html.escape(job['company'])}\n"
            f"📍 {html.escape(job['location'])}\n"
            f"🎯 Match: <b>{int(e.get('match', 0))}%</b>\n"
            f"👤 Level: {html.escape(str(e.get('level', '')))}\n"
            f"⏳ Experience: {html.escape(str(e.get('experience', '')))}\n"
            f"🌍 Remote: {html.escape(str(e.get('remote', '')))}\n"
            f"🛂 Sponsorship: {html.escape(str(e.get('sponsorship', 'unknown')))}\n"
            f"🆕 Freshness: {html.escape(str(e.get('freshness', 'unknown')))}\n"
            f"💡 {html.escape(str(e.get('reason', '')))}\n"
            f"📄 CV tip: {html.escape(str(e.get('cv_tip', '')))}\n"
            f"🌐 {html.escape(job['source'])}\n"
            f'🔗 <a href="{html.escape(job["url"], quote=True)}">Apply / View Job</a>\n\n'
        )

        if len(text) + len(block) > 3900:
            S.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True
                },
                timeout=20
            ).raise_for_status()
            text = ""

        text += block

    if text:
        S.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=20
        ).raise_for_status()


def candidate_score(job):
    t = norm(job["title"] + " " + job["description"])
    score = security_score(job) * 10

    if any(x in t for x in JUN):
        score += 35
    if "remote" in t:
        score += 15
    if any(x in t for x in ["visa sponsorship", "sponsorship", "relocation"]):
        score += 10
    if any(x in norm(job["title"]) for x in [
        "soc", "security", "cybersecurity", "information security"
    ]):
        score += 15

    # Senior gets a small bonus only when no obvious 3+ year requirement exists.
    if "senior" in norm(job["title"]) and not any(x in t for x in HIGHEXP):
        score += 8

    return score


def main():
    print("=== AI Job Hunter v3.1 ===")

    seen = load_seen()
    jobs = api_jobs() + web_search()

    unique = {
        j["url"]: j
        for j in jobs
        if j.get("url") and j.get("title")
    }

    candidates = []
    for job in unique.values():
        if job["url"] in seen:
            continue
        if clearly_bad(job):
            continue
        if security_score(job) < 1:
            continue
        candidates.append(job)

    candidates.sort(key=candidate_score, reverse=True)

    print("unique:", len(unique))
    print("new security candidates:", len(candidates))

    matches = []
    evaluated = set()

    # Do not burn the free API quota on hundreds of weak results.
    # We rank first, then deeply evaluate the best 100.
    MAX_AI_EVAL = 100

    for idx, job in enumerate(candidates[:MAX_AI_EVAL], 1):
        print(f"[AI {idx}/{min(MAX_AI_EVAL, len(candidates))}] {job['title']}")
        job = enrich(job)
        result = ai_match(job)
        evaluated.add(job["url"])

        if result:
            job["evaluation"] = result
            matches.append(job)

        # Conservative pacing. Active Gemini limits vary by project.
        if idx < MAX_AI_EVAL:
            time.sleep(6)

    matches.sort(
        key=lambda x: int(x["evaluation"].get("match", 0)),
        reverse=True
    )

    save_seen(seen | evaluated)

    print("AI matches:", len(matches))

    if matches:
        send_telegram(matches[:12])
        print("Telegram: sent", min(12, len(matches)), "matches")
    else:
        print("No new qualifying matches.")


if __name__ == "__main__":
    main()
