import os
import requests
import time
import sqlite3
from dotenv import load_dotenv

def setup_db():
    conn = sqlite3.connect('jobs.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS seen_jobs (job_id TEXT PRIMARY KEY)')
    conn.commit()
    return conn, c

def notify_discord(title, link):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    data = {"content": f"🚨 **New Role Found:**\n**{title}**\n{link}"}
    requests.post(webhook_url, json=data)

def fetch_cibc_jobs():
    url = "https://cibc.wd3.myworkdayjobs.com/wday/cxs/cibc/search/jobs"
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    session = requests.Session()
    
    all_jobs = []
    limit = 20
    offset = 0
    total_expected = 0
    
    while True:
        payload = {
            "appliedFacets": {
                "Country": ["a30a87ed25634629aa6c3958aa2b91ea"],
                "City" : ["5a781e4ad9710113e8f4efbb1701cf1a"]
            },
            "limit": limit,
            "offset": offset,
            "searchText": ""
        }
        
        response = session.post(url, json=payload, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            
            current_total = data.get("total", 0)
            if current_total > 0:
                total_expected = current_total
                
            jobs_batch = data.get("jobPostings", [])
            
            if not jobs_batch:
                break
                
            all_jobs.extend(jobs_batch)
            offset += limit
            
            if total_expected > 0 and offset >= total_expected:
                break
                
            time.sleep(1)
        else:
            print(response.status_code, response.text)
            break
            
    return all_jobs

def is_target_field(title):
    target_keywords = ["software", "developer", "data analyst", "data science", "python", "react", "sql", "machine learning", "cloud", "it", "analyst", "android"]
    title_lower = title.lower()
    return any(keyword in title_lower for keyword in target_keywords)

def is_entry_level(title):
    seniority_flags = ["senior", "sr", "lead", "principal", "staff", "manager", "director", "head", "consultant", "co-op"]
    title_lower = title.lower()
    return not any(flag in title_lower for flag in seniority_flags)

def process_jobs(jobs, c, conn):
    for job in jobs:
        title = job.get('title', '')
        
        if is_target_field(title) and is_entry_level(title):
            job_id = job['bulletFields'][0] if job.get('bulletFields') else job['title']
            link = f"https://cibc.wd3.myworkdayjobs.com/en-US/search{job.get('externalPath')}"
            
            c.execute("SELECT 1 FROM seen_jobs WHERE job_id = ?", (job_id,))
            
            if not c.fetchone():
                print(f"New job found: {title}")
                notify_discord(title, link)
                c.execute("INSERT INTO seen_jobs (job_id) VALUES (?)", (job_id,))
                conn.commit()
                time.sleep(1)

def main():
    conn, c = setup_db()
    jobs = fetch_cibc_jobs()
    process_jobs(jobs, c, conn)
    conn.close()

if __name__ == "__main__":
    main()