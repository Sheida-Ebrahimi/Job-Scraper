# Serverless Job Market Extraction Pipeline

An automated, event-driven data extraction pipeline designed to scrape, normalize, and distribute highly targeted job market data from enterprise Applicant Tracking Systems (ATS) and job boards. 

**Architecture:** Serverless (AWS Lambda, DynamoDB(NoSQL), EventBridge)  
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