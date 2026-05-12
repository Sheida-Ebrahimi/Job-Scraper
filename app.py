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

def notify_discord(title, link, company_name):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        logger.error("Missing Webhook URL!")
        return
    try:
        data = {"content": f"🚨 **New Role at {company_name}:**\n**{title}**\n{link}"}
        requests.post(webhook_url, json=data, timeout=5)
    except Exception as e:
        logger.error(f"Discord notification failed: {e}")

def get_safe_id(job):
    if job.get('id'):
        return str(job['id'])
    fallback_string = f"{job.get('title', '')}{job.get('link', '')}"
    return hashlib.md5(fallback_string.encode('utf-8')).hexdigest()

def is_target_field(title):
    target_keywords = ["software", "developer", "analyst", "data", "data science", "python", "react", "sql", "machine learning", "agentic", "scientist", "mobile"]
    title_lower = title.lower()
    return any(keyword in title_lower for keyword in target_keywords)

def is_entry_level(title):
    seniority_flags = ["senior", "sr", "lead", "principal", "staff", "manager", "director", "student", "mortgage", "co-op", "bilingual", "head", "management", "ii", "iii", "intern", "chief", "advisor", "cfo"]
    title_lower = title.lower()
    return not any(flag in title_lower for flag in seniority_flags)

def fetch_workday_jobs(company):
    logger.info(f"Fetching Workday: {company['name']}...")
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    session = requests.Session()
    normalized_jobs = []
    limit = 20
    offset = 0
    total = None

    while True:
        payload = {
            **company["payload"],   
            "limit": limit,
            "offset": offset        
        }

        response = session.post(company["url"], json=payload, headers=headers)

        if response.status_code != 200:
            logger.warning(f"{company['name']} returned {response.status_code}, stopping.")
            break

        data = response.json()
        if total is None:
            total = data.get("total")
            logger.info(f"{company['name']}: {total} total jobs found")
            if total == 0:
                break
        batch = data.get("jobPostings", [])

        if not batch:
            break

        for job in batch:
            normalized_jobs.append({
                "id": job.get("externalPath"),
                "title": job.get("title", ""),
                "link": f"{company['base_url']}{job.get('externalPath')}"
            })

        logger.info(f"{company['name']}: fetched {offset + len(batch)} of {total}")
        offset += limit

        if offset >= total:
            break

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
            
            if response.status_code != 200:
                logger.warning(f"{company['name']} returned {response.status_code}, stopping.")
                break
                
            data = response.json()
            if total_hits is None:
                total_hits = data.get('refineSearch', {}).get('totalHits', 0)
            if total_hits == 0:
                break
            
            job_list = data.get('refineSearch', {}).get('data', {}).get('jobs', [])
            total_hits = data.get('refineSearch', {}).get('totalHits', 0)
            
            if not job_list:
                break
                
            for job in job_list:
                job_id = job.get('jobId', '')
                job_link = f"{company['base_url']}/job/{job_id}" 
                
                normalized_jobs.append({
                    "id": str(job_id),
                    "title": job.get('title', ''),
                    "link": job_link
                })
            
            logger.info(f"{company['name']}: fetched {offset + len(job_list)} of {total_hits}")
            offset += limit
            
            if offset >= total_hits:
                break
                
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
        if pages_fetched >= max_pages:
            logger.info(f"Reached max pages limit ({max_pages}) for {company['name']}.")
            break

        url = f"{company['search_url']}&startrow={startrow}"
        
        try:
            response = curl_requests.get(url, impersonate="chrome")
            soup = BeautifulSoup(response.text, 'html.parser')
            
            job_links = soup.select('a.jobTitle-link, a.jobTitle, a.job-title')
            
            if not job_links:
                all_links = soup.find_all('a', href=True)
                for a in all_links:
                    href = a['href']
                    text = a.text.strip()
                    if '/job/' in href and text:
                        if "Save" not in text and "Apply" not in text:
                            job_links.append(a)
            
            seen_hrefs = set()
            valid_links = []
            for link in job_links:
                href = link.get('href')
                if href not in seen_hrefs:
                    seen_hrefs.add(href)
                    valid_links.append(link)
            
            if not valid_links:
                break
                
            for link in valid_links:
                title = link.text.strip()
                href = link.get('href')
                
                clean_href = href.rstrip('/')
                job_id = clean_href.split('/')[-1] 
                
                full_link = href if href.startswith('http') else f"{company['base_url']}{href}"
                
                normalized_jobs.append({
                    "id": job_id,
                    "title": title,
                    "link": full_link
                })
            
            logger.info(f"{company['name']}: fetched {len(valid_links)} jobs from page starting at {startrow}")
            startrow += 25
            pages_fetched += 1
            time.sleep(random.uniform(1.5, 3.0))
            
        except Exception as e:
            logger.error(f"Error fetching {company['name']}: {e}")
            break
            
    return normalized_jobs

def fetch_greenhouse_jobs(company):
    logger.info(f"Fetching Greenhouse: {company['name']}...")
    url = f"https://boards-api.greenhouse.io/v1/boards/{company['board_token']}/jobs"
    try:
        response = requests.get(url, timeout=10) 
        
        if response.status_code != 200:
            logger.warning(f"{company['name']} returned {response.status_code}")
            return []

        data = response.json()
        normalized_jobs = []
        target_locations = company.get('locations')
        
        for job in data.get('jobs', []):
            if target_locations:
                location_name = job.get('location', {}).get('name', '').lower()
                if not any(loc.lower() in location_name for loc in target_locations):
                    continue
                    
            normalized_jobs.append({
                "id": str(job.get('id')),
                "title": job.get('title', ''),
                "link": job.get('absolute_url', '')
            })
            
        logger.info(f"{company['name']}: fetched {len(normalized_jobs)} jobs")
        return normalized_jobs
    except Exception as e:
        logger.error(f"Greenhouse error for {company['name']}: {e}")
        return []

def fetch_eluta():
    logger.info("Fetching Eluta.ca (HTML Scraping)...")
    url = "https://www.eluta.ca/search?q=software+developer+OR+data+analyst&l=Ontario"
    
    try:
        response = curl_requests.get(url, impersonate="chrome")
        soup = BeautifulSoup(response.text, 'html.parser')
        normalized_jobs = []
        
        for job_card in soup.find_all('div', class_='organic-job'): 
            title_element = job_card.find('a', class_='lk-job-title')
            
            if title_element:
                data_url = title_element.get('data-url')
                normalized_jobs.append({
                    "id": data_url,
                    "title": title_element.text.strip(),
                    "link": f"https://www.eluta.ca/{data_url}" 
                })
        return normalized_jobs
    except Exception as e:
        logger.error(f"Failed to bypass Eluta: {e}")
        return []

def process_jobs(jobs, company_name, table): 
    for job in jobs:
        try:
            if not (is_target_field(job['title']) and is_entry_level(job['title'])):
                continue

            job_id = f"{company_name}_{get_safe_id(job)}"

            response = table.get_item(Key={'job_id': job_id})

            if 'Item' not in response:
                logger.info(f"✅ {job['title']} at {company_name}")
                notify_discord(job['title'], job['link'], company_name)
                
                table.put_item(
                    Item={
                        'job_id': job_id,
                        'title': job['title'],
                        'company': company_name,
                        'link': job['link'],
                        'first_seen': time.strftime('%Y-%m-%d %H:%M:%S')
                    }
                )
        except Exception as e:
            logger.error(f"Failed to process job {job.get('title', 'Unknown')} at {company_name}: {e}")

def lambda_handler(event, context):
    table = get_dynamodb_table()

    try:
        with open('companies.json', 'r') as f:
            config = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load companies.json: {e}")
        return {'statusCode': 500, 'body': 'Config error'}

    for company in config.get('workday', []):
        jobs = fetch_workday_jobs(company)
        process_jobs(jobs, company["name"], table)
        time.sleep(random.uniform(2, 4))

    for company in config.get('phenom', []):
        jobs = fetch_phenom_jobs(company)
        process_jobs(jobs, company["name"], table)
        time.sleep(random.uniform(2, 4))

    for company in config.get('successfactors', []):
        jobs = fetch_successfactors_jobs(company, max_pages=10)
        process_jobs(jobs, company["name"], table)
        time.sleep(random.uniform(2, 4))

    for company in config.get('greenhouse', []):
        jobs = fetch_greenhouse_jobs(company)
        process_jobs(jobs, company["name"], table)
        time.sleep(random.uniform(1.5, 3))

    eluta_jobs = fetch_eluta()
    process_jobs(eluta_jobs, "Eluta", table)  

    logger.info("Pipeline execution complete.")
    
    return {
        'statusCode': 200,
        'body': 'Scrape completed successfully'
    }