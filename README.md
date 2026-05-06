I got tired of looking for newly posted jobs on LinkedIn. They were either not related to what I was looking for, or they already had 100+ applicants. So, I built myself a scraper that runs every 15 minutes on AWS, looks up newly posted jobs, filters them and sends me a notification on Discord.

# Serverless Job Market Extraction Pipeline

An automated, event-driven data extraction pipeline designed to scrape, normalize, and distribute highly targeted job market data from enterprise Applicant Tracking Systems (ATS) and job boards. 

**Architecture:** Serverless (AWS Lambda, DynamoDB (NoSQL), EventBridge)  
**Core Technologies:** Python, `boto3`, `curl_cffi`, `BeautifulSoup`

## Architecture Overview

This project bypasses traditional front-end scraping where possible, utilizing reverse-engineered internal APIs (Workday, Phenom, SuccessFactors) to extract raw JSON data the moment a role goes live. 

*   **Extraction:** Python scripts parse complex DOM structures and mimic browser TLS fingerprints (`curl_cffi`) to bypass enterprise WAFs on aggregate sites like Eluta.
*   **Transformation:** Raw payloads are filtered using Regex and string matching to isolate entry-level Software Developer and Data Analyst roles in the Ontario market.
*   **Load & Cache:** Data is processed through an O(1) lookup via AWS DynamoDB using composite primary keys to prevent duplicate alerting and data collisions.
*   **Automation:** AWS EventBridge triggers the AWS Lambda function autonomously on a recurring schedule.
*   **Delivery:** Verified new roles are transmitted instantly via a Discord Webhook integration.

## Repository Structure

*   `app.py`: The production-ready AWS Lambda handler using `boto3` for DynamoDB integration.
*   `local_test.py`: A local development environment utilizing `sqlite3` for rapid testing and API endpoint debugging without incurring cloud reads/writes.
*   `.github/workflows/deploy.yml`: The CI/CD pipeline for automated AWS deployment.

## Local Development Setup

1. Clone the repository and install the dependencies:
   ```bash
   pip install requests beautifulsoup4 curl_cffi python-dotenv

<img width="1227" height="655" alt="image" src="https://github.com/user-attachments/assets/6d7575c8-969c-482e-8a92-00a7b87bc477" />
