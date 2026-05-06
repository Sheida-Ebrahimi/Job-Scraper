import os
import time
import random
import logging
import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests
import hashlib
import boto3

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
    target_keywords = ["software", "developer", "data analyst", "data science", "python", "react", "sql", "machine learning", "agentic", "scientist", "mobile"]
    title_lower = title.lower()
    return any(keyword in title_lower for keyword in target_keywords)

def is_entry_level(title):
    seniority_flags = ["senior", "sr", "lead", "principal", "staff", "manager", "director", "student", "mortgage", "co-op", "bilingual", "head", "management", "ii", "iii", "intern", "chief", "advisor", "CFO"]
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

    WORKDAY_COMPANIES = [
        {
            "name": "CIBC",
            "url": "https://cibc.wd3.myworkdayjobs.com/wday/cxs/cibc/search/jobs",
            "base_url": "https://cibc.wd3.myworkdayjobs.com/en-US/search",
            "payload": {"appliedFacets":{"timeType":["382086945f8001182c270bf1860a7f00"],"Country":["a30a87ed25634629aa6c3958aa2b91ea"],"City":["5a781e4ad9710113e8f4efbb1701cf1a","b95eb8c55e341001547de090da5d0000","5a781e4ad97101047818f3db1701363b","5a781e4ad97101140319dbb517015508","5a781e4ad9710142c57479dc17012a3d","5a781e4ad97101be1db246dc17017b3c"]},"limit":20,"offset":0,"searchText":""}
        },
        {
            "name": "TD Bank",
            "url": "https://td.wd3.myworkdayjobs.com/wday/cxs/td/TD_Bank_Careers/jobs",
            "base_url": "https://td.wd3.myworkdayjobs.com/en-US/TD_Bank_Careers",
            "payload": {"appliedFacets":{"timeType":["14c9322ea8e3014f4096d9d2dc025400"],"locationCountry":["a30a87ed25634629aa6c3958aa2b91ea"],"locations":["dafbf576c2d2100094503f8698660000","dafbf576c2d2100094539f216ab80000","dafbf576c2d210009450432084160000","dafbf576c2d2100094507c2260ea0000"]},"limit":20,"offset":0,"searchText":""}
        },
        {
            "name": "BMO",
            "url": "https://bmo.wd3.myworkdayjobs.com/wday/cxs/bmo/External/jobs",
            "base_url": "https://bmo.wd3.myworkdayjobs.com/en-US/External",
            "payload": {"appliedFacets":{"timeType":["027a38bd0f0901102412b6de9c095800"],"Country":["a30a87ed25634629aa6c3958aa2b91ea"],"State__Region__Province":["218a720b28a74c67b5c6d42c00bdadfa"],"Location":["c3170091f3cd01dec314cd815f01e2bd","c3170091f3cd012415f62c805f01e3b7","c3170091f3cd01d5f0354a805f0156b8","c3170091f3cd0103127b9d815f0133bd","c3170091f3cd01ad2d6aa3815f014cbd","c3170091f3cd01fb537039805f0110b8","c3170091f3cd01e24be626805f01d4b7","c3170091f3cd0153f61737805f0106b8","c3170091f3cd0140501721805f01bbb7","c3170091f3cd01974d8225805f01cfb7","c3170091f3cd01b6477d40805f012eb8","c3170091f3cd013d8503b07d5f01baae","c3170091f3cd01c2179175815f01a7bc","c3170091f3cd01561deeff805f01e5ba","c3170091f3cd01dcfa59da7f5f01c6b6"]},"limit":20,"offset":0,"searchText":""}
        },
        {
            "name": "Manulife",
            "url": "https://manulife.wd3.myworkdayjobs.com/wday/cxs/manulife/MFCJH_Jobs/jobs",
            "base_url": "https://manulife.wd3.myworkdayjobs.com/MFCJH_Jobs",
            "payload": {"appliedFacets":{"locations":["90905028607c019c77b34f1f8257fee2","619830580a890128c79fff273301b3ea","f4f0c297dfca4db48066e45d00ca3910","0a7b3e391e784b38a983c4361ecba51c","83a764f8e3b448af8d701dd00641d398","c36bf68faa714152ae93b4e33a796b78","2c3065029f424702a9f2e6dad0d0c72c","8d41c303346b498d8e79ebbcd5a607d0"],"timeType":["37bbc660cc294a08b29221afba09224f"],"Location_Country":["a30a87ed25634629aa6c3958aa2b91ea"]},"limit":20,"offset":0,"searchText":""}
        },
        {
            "name": "Sun Life",
            "url": "https://sunlife.wd3.myworkdayjobs.com/wday/cxs/sunlife/Experienced/jobs",
            "base_url": "https://sunlife.wd3.myworkdayjobs.com/en-US/Experienced",
            "payload": {"appliedFacets":{"primaryLocation":["07092c6e50bc0134d3a5a00a192d6813","07092c6e50bc0127378d190c192de914","7b5336816d4310d054d2c9e19854324d","07092c6e50bc0196a39a9c09192d5a12"],"timeType":["902e0bbe2cc64592936970c0054c6369"],"Location_Country":["a30a87ed25634629aa6c3958aa2b91ea"]},"limit":20,"offset":0,"searchText":""}
        }
    ]

    PHENOM_COMPANIES = [
        {
            "name": "RBC",
            "api_url": "https://jobs.rbc.com/widgets",
            "base_url": "https://jobs.rbc.com/ca/en",
            "payload": {
                "country": "ca", "lang": "en_ca", "deviceType": "desktop",
                "ddoKey": "refineSearch", "siteType": "external",
                "jobs": True, 
                "selected_fields": {"state": ["Ontario"]}
            }
        },
        {
            "name": "Bell",
            "api_url": "https://jobs.bell.ca/widgets",
            "base_url": "https://jobs.bell.ca/ca/en",
            "payload": {
                "country": "ca", "lang": "en_ca", "deviceType": "desktop",
                "ddoKey": "refineSearch", "siteType": "external",
                "jobs": True, 
                "selected_fields": {"state": ["Ontario"]}
            }
        }
    ]

    SUCCESSFACTORS_COMPANIES = [
        {
            "name": "Scotiabank",
            "search_url": "https://jobs.scotiabank.com/search/?q=&locationsearch=Toronto",
            "base_url": "https://jobs.scotiabank.com"
        }
    ]

    for company in WORKDAY_COMPANIES:
        jobs = fetch_workday_jobs(company)
        process_jobs(jobs, company["name"], table)
        time.sleep(random.uniform(2, 4))

    for company in PHENOM_COMPANIES:
        jobs = fetch_phenom_jobs(company)
        process_jobs(jobs, company["name"], table)
        time.sleep(random.uniform(2, 4))

    for company in SUCCESSFACTORS_COMPANIES:
        jobs = fetch_successfactors_jobs(company, max_pages=10)
        process_jobs(jobs, company["name"], table)
        time.sleep(random.uniform(2, 4))

    eluta_jobs = fetch_eluta()
    process_jobs(eluta_jobs, "Eluta", table)  

    logger.info("Done.")
    
    return {
        'statusCode': 200,
        'body': 'Scrape completed successfully'
    }