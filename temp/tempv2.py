from browser_use import Agent, BrowserSession, Controller
from browser_use.browser import BrowserProfile
import asyncio
from browser_use.llm import ChatOpenRouter
from pydantic import SecretStr, BaseModel
import os
from dotenv import load_dotenv
import re
from lmnr import Laminar, Instruments
from pymongo import MongoClient
from datetime import datetime
import traceback

# Set the environment variable so Playwright uses your custom browser path
# os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/media/mats/3c24094c-800b-4576-a390-d23a6d7a02291/workspace/test_ai_gen/browser_use/.playwright-browsers"
# Read environment variables
load_dotenv()

# # this line auto-instruments Browser Use and any browser you use (local or remote)
# Laminar.initialize(project_api_key="tY4nwVIe2BZHVgMQfaVsBXmtLHSBiDF7U7W9FCSumGXXfYJWcsSW3CB51yMcywZd", disable_batch=True, disabled_instruments={Instruments.BROWSER_USE})

# Initialize OpenRouter with any model available on their platform
llm = ChatOpenRouter(
    model='deepseek/deepseek-chat-v3.1',
    api_key=os.getenv('OPENROUTER_API_KEY'),
    temperature=0.7,
)

# def find_chrome():
#     base_dir = os.environ["PLAYWRIGHT_BROWSERS_PATH"]
#     for name in os.listdir(base_dir):
#         if name.startswith("chromium-"):
#             chrome_path = os.path.join(base_dir, name, 'chrome-linux', 'chrome')
#             if os.path.exists(chrome_path):
#                 return chrome_path
#     return None

# CHROME_BIN = find_chrome()

# --- Structured output schema & controller ---
class ResultJob(BaseModel):
    job_title: str
    url: str
    location: str | None = None
    company_url: str | None = None

class ExtractJobListingsOp(BaseModel):
    results: list[ResultJob]

class FindJobPage(BaseModel):
    has_jobs_page: bool | None = None
    jobs_page_url: str | None = None

class AgentOutput(BaseModel):
    results: list[ResultJob]

controller = Controller()

# --- MongoDB setup ---
def init_mongodb():
    """Initialize MongoDB connection and return collection"""
    try:
        # Connect to MongoDB (adjust connection string as needed)
        client = MongoClient('mongodb+srv://rohit:1SJc7y1bNZndSsUC@cluster0.3g41pmp.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
        db = client['job_scraper']
        collection = db['company_jobs']
        return collection
    except Exception as e:
        print(f"Error connecting to MongoDB: {e}")
        return None

def save_company_result(collection, company_name, company_url, status, jobs=None, error_message=None, has_job_page=None, jobs_page_url=None):
    """Save company processing result to MongoDB"""
    if collection is None:
        print("MongoDB collection not available, skipping save")
        return
    
    try:
        # Build document with only non-None values
        document = {
            'company_name': company_name,
            'company_url': company_url,
            'status': status,  # 'in_progress', 'complete', 'failed'
            'jobs': jobs if jobs else [],
            'job_count': len(jobs) if jobs else 0,
            'updated_at': datetime.utcnow()
        }
        
        # Only add fields that are not None
        if error_message is not None:
            document['error_message'] = error_message
        if has_job_page is not None:
            document['has_job_page'] = has_job_page
        if jobs_page_url is not None:
            document['jobs_page_url'] = jobs_page_url
            
        # Set processed_at only on first insert
        update_operations = {'$set': document}
        update_operations['$setOnInsert'] = {'processed_at': datetime.utcnow()}
        
        # Update or insert document
        collection.update_one(
            {'company_name': company_name, 'company_url': company_url},
            update_operations,
            upsert=True
        )
        print(f"Saved {company_name} to MongoDB with status: {status}")
        
    except Exception as e:
        print(f"Error saving to MongoDB: {e}")

def read_companies_list():
    """Read the companies list and extract company names and URLs"""
    companies = []
    
    try:
        with open('temp/companies_list.md', 'r', encoding='utf-8') as file:
            lines = file.readlines()
            
        for line in lines:
            line = line.strip()
            # Skip empty lines, headers, and separator lines
            if not line or line.startswith('#') or line.startswith('---') or line.startswith('Name |'):
                continue
                
            # Parse the line to extract company name and URL
            # Format: [Company Name](/company-profiles/company-name.md) | https://website.com | Region
            parts = line.split(' | ')
            if len(parts) >= 2:
                # Extract company name from markdown link format [Company Name](/path)
                company_part = parts[0].strip()
                url_part = parts[1].strip()
                
                # Extract company name using regex
                match = re.match(r'\[([^\]]+)\]', company_part)
                if match:
                    company_name = match.group(1)
                    companies.append({
                        'name': company_name,
                        'url': url_part
                    })
                    
    except FileNotFoundError:
        print("Error: companies_list.md file not found")
    except Exception as e:
        print(f"Error reading file: {e}")
        
    return companies

async def extract_job_listings(url, task):
    print("Current task: ", task)
    
    # Define initial actions to navigate to Google first
    initial_actions = [
        {'go_to_url': {'url': url, 'new_tab': True}},
    ]
    
    # Create working profile
    bp = BrowserProfile(
        viewport_size={'width': 1280, 'height': 720},
        user_data_dir="./manual-test-profile",
        # executable_path=CHROME_BIN,
        headless=False,  # Let's see what's happening
        chromium_sandbox=False,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    )
    
    agent = Agent(
        task=task,
        llm=llm,
        browser_profile=bp,
        initial_actions=initial_actions,
        controller=controller,
        output_model_schema=ExtractJobListingsOp,
        llm_timeout=120
    )

    try:
        history = await agent.run()
        result = history.final_result()
        if result:
            parsed: ExtractJobListingsOp = ExtractJobListingsOp.model_validate_json(result)

            for job in parsed.results:
                print('\n\n--------------------------------')
                print(f'job_title:            {job.job_title}')
                print(f'company_url:              {job.company_url}')
                print(f'location:         {job.location}')
                print(f'url:             {job.url}')
    
        else:
            print('No result')
            return {
                "has_jobs": False,
                "jobs": [],
                "url": url
            }

        return {
            "has_jobs": True,
            "jobs": parsed.results,
            "url": url
        }
    except Exception as e:
        print(f"Agent failed with error: {e}")
        traceback.print_exc()
        return {
            "has_jobs": False,
            "jobs": [],
            "url": url,
            "error": str(e)
        }

async def find_jobs_page(url, task):
    print("Current task: ", task)
    
    # Define initial actions to navigate to Google first
    initial_actions = [
        {'go_to_url': {'url': url, 'new_tab': True}},
    ]
    
    # Create working profile
    bp = BrowserProfile(
        viewport_size={'width': 1280, 'height': 720},
        user_data_dir="./manual-test-profile",
        # executable_path=CHROME_BIN,
        headless=False,  # Let's see what's happening
        chromium_sandbox=False,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    )
    
    agent = Agent(
        task=task,
        llm=llm,
        browser_profile=bp,
        initial_actions=initial_actions,
        controller=controller,
        output_model_schema=FindJobPage,
        llm_timeout=120
    )

    try:
        history = await agent.run()
        result = history.final_result()
        if result:
            parsed: FindJobPage = FindJobPage.model_validate_json(result)

            print('\n\n----------find jobs page------------')
            print(f'has_job_page:            {parsed.has_jobs_page}')
            print(f'jobs_page_url:              {parsed.jobs_page_url}')
    
        else:
            print('No result')

        return {
            "has_jobs_page": parsed.has_jobs_page,
            "jobs_page_url": parsed.jobs_page_url
        }
    except Exception as e:
        print(f"Agent failed with error: {e}")
        traceback.print_exc()
        return {
            "has_jobs_page": False,
            "jobs_page_url": None
        }


if __name__ == "__main__":
    # Initialize MongoDB
    collection = init_mongodb()
    
    # Read and print companies list
    print("Reading companies list...")
    companies = read_companies_list()
    
    print(f"\nFound {len(companies)} companies:")
    print("=" * 80)
    
    for i, company in enumerate(companies, 1):
        print("-" * 100)
        print(f"{i:3d}. {company['name']}")
        print(f"     URL: {company['url']}")

        company_name = company['name']
        url = company['url']
        
        # Mark as in_progress before starting
        save_company_result(collection, company_name, url, 'in_progress')

        # step 1
        try:
            save_company_result(collection, company_name, url, 'find_jobs_page_progress')

            result = asyncio.run(find_jobs_page(url, f'''
                Goal: find if {url} has open job listings page
                - Navigate to the careers/jobs/join-us page via header/footer/nav or search.
                - Confirm it's a jobs page (scroll if needed). you should see a list of job listings
                - if it exisits return the url of the jobs page
            '''))

            # Print all results for now (both success and failed)
            if result['has_jobs_page']:
                print(f"Found jobs page for {company_name}")
                print(result['jobs_page_url'])
                # Save progress - found jobs page
                save_company_result(collection, company_name, url, 'find_jobs_page_complete', 
                                  jobs=[], 
                                  has_job_page=result['has_jobs_page'], 
                                  jobs_page_url=result['jobs_page_url'])
            else:
                print("No jobs page found")
                # Save as complete but no jobs page found
                save_company_result(collection, company_name, url, 'find_jobs_page_not_found', 
                                  jobs=[], 
                                  has_job_page=result['has_jobs_page'], 
                                  error_message='No jobs page found')

        except Exception as e:
            print(f"Failed to process {company_name}: {e}")
            traceback.print_exc()
            # Save as failed
            save_company_result(collection, company_name, url, 'find_jobs_page_failed', error_message=str(e)) 

        if result['has_jobs_page'] and result['jobs_page_url']:
            try:
                save_company_result(collection, company_name, url, 'extract_job_listings_progress')

                result = asyncio.run(extract_job_listings(url, f'''
                    Goal: find if {result['jobs_page_url']} 
                    - Confirm it's a jobs page (scroll if needed).
                    - Extract all matching roles: Web, Fullstack, Backend, Software (Engineer or Developer).
                    - Look for job titles, locations, and URLs.
                    - Complete the task when you find job listings or confirm none exist.
                '''))

                # Print all results for now (both success and failed)
                if result['has_jobs']:
                    print(f"Found {len(result['jobs'])} jobs for {company_name}")
                    save_company_result(collection, company_name, url, 'extract_job_listings_complete', [job.model_dump() for job in result['jobs']])
                else:
                    print("No results returned")
                    # Save as complete but no jobs found
                    error_msg = result.get('error', 'No jobs found')
                    save_company_result(collection, company_name, url, 'extract_job_listings_no_jobs_found', [], error_msg)

            except Exception as e:
                print(f"Failed to process {company_name}: {e}")
                traceback.print_exc()
                # Save as failed
                save_company_result(collection, company_name, url, 'extract_job_listings_failed', error_message=str(e)) 