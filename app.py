import os
import time
import random
import logging
import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests
import hashlib
import boto3
import json

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_dynamodb_table():
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    return dynamodb.Table('seenJobs')

def notify_discord(title, link, company_name, persona):
    if persona == "me":
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        prefix = "🚨 **New Role:**"
    else:
        webhook_url = os.getenv("FRIEND_WEBHOOK_URL")
        prefix = "🤝 **New Role:**"

    if not webhook_url:
        logger.error(f"Missing Webhook URL for {persona}!")
        return

    try:
        data = {"content": f"{prefix} at {company_name}\n**{title}**\n{link}"}
        requests.post(webhook_url, json=data, timeout=5)
    except Exception as e:
        logger.error(f"Discord notification failed: {e}")

def get_safe_id(job):
    if job.get('id'):
        return str(job['id'])
    fallback_string = f"{job.get('title', '')}{job.get('link', '')}"
    return hashlib.md5(fallback_string.encode('utf-8')).hexdigest()

def check_personas(title):
    title_lower = title.lower()
    personas = []
    my_keywords = ["software", "developer", "analyst", "data", "data science", "python", "react", "sql", "machine learning", "agentic", "scientist", "mobile"]
    if any(keyword in title_lower for keyword in my_keywords):
        personas.append("me")
    friend_keywords = ["financial services back office","payment", "operations", "back office", "transaction", "qa", "software engineer in test", "sdet", "quality assurance", "data entry", "fraud", "aml", "helpdesk", "service desk", "claims", "compliance", "coordinator"]
    if any(keyword in title_lower for keyword in friend_keywords):
        personas.append("friend")
    return personas

def is_entry_level(title):
    seniority_flags = ["intermediate","senior", "sr", "lead", "principal", "staff", "manager", "director", "student", "mortgage", "co-op", "bilingual", "head", "management", "ii", "iii", "intern", "chief", "advisor", "cfo", "supervisor", "vp"]
    title_lower = title.lower()
    return not any(flag in title_lower for flag in seniority_flags)

def fetch_job_description(link):
    try:
        response = curl_requests.get(link, impersonate="chrome", timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup.get_text(separator=' ', strip=True).lower()
    except Exception as e:
        logger.error(f"Could not fetch description for {link}: {e}")
        return ""

def has_forbidden_experience_in_text(text):
    forbidden_patterns = ["5+ years", "5 years of experience", "5+ years of experience",  "minimum 3 years", "minimum 4 years", "minimum 5 years", "3+ years", "4+ years"]
    return any(pattern in text for pattern in forbidden_patterns)

def fetch_workday_jobs(company):
    logger.info(f"Fetching Workday: {company['name']}...")
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    session = requests.Session()
    normalized_jobs = []
    limit = 20
    offset = 0
    total = None
    while True:
        payload = {**company["payload"], "limit": limit, "offset": offset}
        response = session.post(company["url"], json=payload, headers=headers)
        if response.status_code != 200:
            logger.warning(f"{company['name']} returned {response.status_code}, stopping.")
            break
        data = response.json()
        if total is None:
            total = data.get("total")
            if total == 0: break
        batch = data.get("jobPostings", [])
        if not batch: break
        for job in batch:
            normalized_jobs.append({"id": job.get("externalPath"), "title": job.get("title", ""), "link": f"{company['base_url']}{job.get('externalPath')}"})
        offset += limit
        if offset >= total: break
        time.sleep(random.uniform(1.2, 2.5))
    return normalized_jobs

def fetch_phenom_jobs(company):
    logger.info(f"Fetching Phenom: {company['name']}...")
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    session = requests.Session()
    normalized_jobs = []
    limit = 10
    offset = 0
    total_hits = None
    while True:
        payload = company["payload"].copy()
        payload["from"] = offset
        payload["size"] = limit
        try:
            response = session.post(company["api_url"], json=payload, headers=headers)
            if response.status_code != 200: break
            data = response.json()
            if total_hits is None: total_hits = data.get('refineSearch', {}).get('totalHits', 0)
            job_list = data.get('refineSearch', {}).get('data', {}).get('jobs', [])
            if not job_list: break
            for job in job_list:
                job_id = job.get('jobId', '')
                normalized_jobs.append({"id": str(job_id), "title": job.get('title', ''), "link": f"{company['base_url']}/job/{job_id}"})
            offset += limit
            if offset >= total_hits: break
            time.sleep(random.uniform(1.5, 3.0))
        except Exception as e:
            logger.error(f"Error fetching {company['name']}: {e}")
            break
    return normalized_jobs

def fetch_successfactors_jobs(company, max_pages=10):
    logger.info(f"Fetching SuccessFactors: {company['name']}...")
    normalized_jobs = []
    startrow = 0
    pages_fetched = 0
    while True:
        if pages_fetched >= max_pages: break
        url = f"{company['search_url']}&startrow={startrow}"
        try:
            response = curl_requests.get(url, impersonate="chrome")
            soup = BeautifulSoup(response.text, 'html.parser')
            job_links = soup.select('a.jobTitle-link, a.jobTitle, a.job-title')
            seen_hrefs = set()
            valid_links = []
            for link in job_links:
                href = link.get('href')
                if href not in seen_hrefs:
                    seen_hrefs.add(href)
                    valid_links.append(link)
            if not valid_links: break
            for link in valid_links:
                href = link.get('href')
                full_link = href if href.startswith('http') else f"{company['base_url']}{href}"
                normalized_jobs.append({"id": href.rstrip('/').split('/')[-1], "title": link.text.strip(), "link": full_link})
            startrow += 25
            pages_fetched += 1
            time.sleep(random.uniform(1.5, 3.0))
        except Exception: break
    return normalized_jobs

def fetch_greenhouse_jobs(company):
    logger.info(f"Fetching Greenhouse: {company['name']}...")
    url = f"https://boards-api.greenhouse.io/v1/boards/{company['board_token']}/jobs"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200: return []
        data = response.json()
        normalized_jobs = []
        target_locations = company.get('locations')
        for job in data.get('jobs', []):
            if target_locations:
                location_name = job.get('location', {}).get('name', '').lower()
                if not any(loc.lower() in location_name for loc in target_locations): continue
            normalized_jobs.append({"id": str(job.get('id')), "title": job.get('title', ''), "link": job.get('absolute_url', '')})
        return normalized_jobs
    except Exception as e:
        logger.error(f"Greenhouse error: {e}")
        return []

def fetch_careerbeacon():
    import re
    logger.info("Fetching CareerBeacon...")
    query = "Payment Processing Analyst,Operations Analyst,Back Office Operations Associate,Banking Operations Coordinator,Transaction Processing Specialist,QA,Software Engineer in Test"
    url = f"https://www.careerbeacon.com/en/search?q={requests.utils.quote(query)}&l=Ontario"
    try:
        response = curl_requests.get(url, impersonate="chrome")
        soup = BeautifulSoup(response.text, 'html.parser')
        normalized_jobs = []
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href', '')
            title = a_tag.text.strip()
            if re.search(r'/job-\d+/', href) and len(title) > 5:
                full_link = href if href.startswith('http') else f"https://www.careerbeacon.com{href}"
                normalized_jobs.append({"id": hashlib.md5(full_link.encode('utf-8')).hexdigest(), "title": title, "link": full_link})
        return list({job['id']: job for job in normalized_jobs}.values())
    except Exception as e:
        logger.error(f"Error fetching CareerBeacon: {e}")
        return []

def process_jobs(jobs, company_name, table): 
    for job in jobs:
        try:
            if not is_entry_level(job['title']): continue
            personas = check_personas(job['title'])
            if not personas: continue
            description = fetch_job_description(job['link'])
            if has_forbidden_experience_in_text(description): continue
            job_id = f"{company_name}_{get_safe_id(job)}"
            if 'Item' not in table.get_item(Key={'job_id': job_id}):
                for persona in personas:
                    notify_discord(job['title'], job['link'], company_name, persona)
                table.put_item(Item={'job_id': job_id, 'title': job['title'], 'company': company_name, 'link': job['link'], 'first_seen': time.strftime('%Y-%m-%d %H:%M:%S')})
                time.sleep(random.uniform(1.0, 2.0))
        except Exception as e:
            logger.error(f"Failed to process job {job.get('title', 'Unknown')} at {company_name}: {e}")

def lambda_handler(event, context):
    table = get_dynamodb_table()
    try:
        with open('companies.json', 'r') as f: config = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load companies.json: {e}")
        return {'statusCode': 500, 'body': 'Config error'}
    for company in config.get('workday', []):
        process_jobs(fetch_workday_jobs(company), company["name"], table)
    for company in config.get('phenom', []):
        process_jobs(fetch_phenom_jobs(company), company["name"], table)
    for company in config.get('successfactors', []):
        process_jobs(fetch_successfactors_jobs(company), company["name"], table)
    for company in config.get('greenhouse', []):
        process_jobs(fetch_greenhouse_jobs(company), company["name"], table)
    process_jobs(fetch_careerbeacon(), "CareerBeacon", table)
    return {'statusCode': 200, 'body': 'Scrape completed'}