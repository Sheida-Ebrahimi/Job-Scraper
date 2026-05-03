import requests

def fetch_cibc_jobs():
    url = "https://cibc.wd3.myworkdayjobs.com/wday/cxs/cibc/search/jobs"
    
    payload = {
        "appliedFacets": {
        "Country": ["a30a87ed25634629aa6c3958aa2b91ea"],
        "City" : ["5a781e4ad9710113e8f4efbb1701cf1a"]
            },
            "limit": 20,
            "offset": 0,
            "searchText": ""
    }
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    response = requests.post(url, json=payload, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        return data.get("jobPostings", [])
    else:
        print(response)

    
    return []


jobs = fetch_cibc_jobs()
    
for job in jobs:
    title = job.get("title")
    job_req = job.get("bulletFields", [""])[0]
    link = f"https://cibc.wd3.myworkdayjobs.com/en-US/search{job.get('externalPath')}"
        
    print(f"{title} | {job_req}")
    print(f"{link}\n")