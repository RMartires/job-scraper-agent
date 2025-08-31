import json
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
import logging
import uuid

from sentry_sdk.utils import json_dumps
logging.getLogger('pymongo').setLevel(logging.WARNING)

# Set the environment variable so Playwright uses your custom browser path
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/media/mats/3c24094c-800b-4576-a390-d23a6d7a02291/workspace/test_ai_gen/browser_use/.playwright-browsers"
# Read environment variables
load_dotenv()

# this line auto-instruments Browser Use and any browser you use (local or remote)
# Laminar.initialize(project_api_key=os.getenv('LMNR_PROJECT_API_KEY'), disable_batch=True, disabled_instruments={Instruments.BROWSER_USE})

# Initialize OpenRouter with any model available on their platform
llm = ChatOpenRouter(
    # model='mistralai/mistral-small-3.2-24b-instruct:free',
    model='deepseek/deepseek-r1:free',
    api_key=os.getenv('OPENROUTER_API_KEY'),
    temperature=0.7,
)

def find_chrome():
    base_dir = os.environ["PLAYWRIGHT_BROWSERS_PATH"]
    for name in os.listdir(base_dir):
        if name.startswith("chromium-"):
            chrome_path = os.path.join(base_dir, name, 'chrome-linux', 'chrome')
            if os.path.exists(chrome_path):
                return chrome_path
    return None

CHROME_BIN = find_chrome()

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
        client = MongoClient(os.getenv('MONGO_DB_URI'))
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
        with open('lib/companies_list.md', 'r', encoding='utf-8') as file:
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

async def extract_job_listings(url, return_string=False):
    task = f'''
            Goal: find if {url} 
            - Confirm it's a jobs page (scroll if needed).
            - Extract all matching roles: Web, Fullstack, Backend, Software (Engineer or Developer).
            - Look for job titles, locations, and URLs.
            - Complete the task when you find job listings or confirm none exist.
        '''
    print("Current task: ", task)
    
    # Define initial actions to navigate to Google first
    initial_actions = [
        {'go_to_url': {'url': url, 'new_tab': True}},
    ]
    
    # Create unique profile directory for this operation
    unique_profile = f"./profiles/extract-{uuid.uuid4().hex[:8]}"
    os.makedirs(os.path.dirname(unique_profile), exist_ok=True)
    
    # Create working profile
    bp = BrowserProfile(
        viewport_size={'width': 1280, 'height': 720},
        user_data_dir=unique_profile,
        executable_path=CHROME_BIN,
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
            return []
        
        if return_string:
            return json.dumps(parsed.model_dump_json())

        return parsed.results
    except Exception as e:
        print(f"Agent failed with error: {e}")
        traceback.print_exc()
        return []

async def find_jobs_page(url, return_string=False):
    task = f'''
            Goal: find if {url} has open job listings page
            - Navigate to the careers/jobs/join-us page via header/footer/nav or search.
            - Confirm it's a jobs page (scroll if needed). you should see a list of job listings
            - if it exisits return the url of the jobs page
            '''
    print("Current task: ", task)
    
    # Define initial actions to navigate to Google first
    initial_actions = [
        {'go_to_url': {'url': url, 'new_tab': True}},
    ]
    
    # Create unique profile directory for this operation
    unique_profile = f"./profiles/find-{uuid.uuid4().hex[:8]}"
    os.makedirs(os.path.dirname(unique_profile), exist_ok=True)
    
    # Create working profile
    bp = BrowserProfile(
        viewport_size={'width': 1280, 'height': 720},
        user_data_dir=unique_profile,
        executable_path=CHROME_BIN,
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
            return None
            
        if return_string:
           return json.dumps(parsed.model_dump_json()) 

        return parsed
    except Exception as e:
        print(f"Agent failed with error: {e}")
        traceback.print_exc()
        return None

async def process_single_company(collection, company):
    """Process a single company with both steps"""
    company_name = company['name']
    url = company['url']
    
    print(f"Starting processing for {company_name}")
    
    # Mark as in_progress before starting
    save_company_result(collection, company_name, url, 'in_progress')

    # Step 1: Find jobs page
    try:
        save_company_result(collection, company_name, url, 'find_jobs_page_progress')
        result = await find_jobs_page(url)

        if result != None and result.has_jobs_page:
            print(f"Found jobs page for {company_name}")
            save_company_result(collection, company_name, url, 'find_jobs_page_complete', 
                              jobs=[], 
                              has_job_page=result.has_jobs_page, 
                              jobs_page_url=result.jobs_page_url)
        else:
            print(f"No jobs page found for {company_name}")
            save_company_result(collection, company_name, url, 'find_jobs_page_not_found', 
                              jobs=[], 
                              has_job_page=result.has_jobs_page if result else False, 
                              error_message='No jobs page found')
            return  # Exit early if no jobs page

    except Exception as e:
        print(f"Failed to find jobs page for {company_name}: {e}")
        traceback.print_exc()
        save_company_result(collection, company_name, url, 'find_jobs_page_failed', error_message=str(e))
        return

    # Step 2: Extract job listings (only if jobs page found)
    if result != None and result.has_jobs_page and result.jobs_page_url:
        try:
            save_company_result(collection, company_name, url, 'extract_job_listings_progress')
            job_results = await extract_job_listings(result.jobs_page_url)

            if job_results != None and len(job_results) > 0:
                print(f"Found {len(job_results)} jobs for {company_name}")
                save_company_result(collection, company_name, url, 'extract_job_listings_complete', 
                                  [job.model_dump() for job in job_results])
            else:
                print(f"No job listings found for {company_name}")
                save_company_result(collection, company_name, url, 'extract_job_listings_no_jobs_found', 
                                  [], 'No jobs found')

        except Exception as e:
            print(f"Failed to extract job listings for {company_name}: {e}")
            traceback.print_exc()
            save_company_result(collection, company_name, url, 'extract_job_listings_failed', 
                              error_message=str(e))

async def process_batch(collection, batch, batch_num, total_batches):
    """Process a batch of companies"""
    print(f"\n{'='*80}")
    print(f"Processing batch {batch_num}/{total_batches} with {len(batch)} companies")
    print(f"{'='*80}")
    
    # Create semaphore to limit concurrent operations within the batch
    max_concurrent_per_batch = 2  # Process up to 2 companies simultaneously per batch
    semaphore = asyncio.Semaphore(max_concurrent_per_batch)
    
    async def process_with_semaphore(company):
        async with semaphore:
            return await process_single_company(collection, company)
    
    tasks = []
    for company in batch:
        task = process_with_semaphore(company)
        tasks.append(task)
    
    # Run all tasks in the batch concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Handle exceptions and summary
    successful = 0
    failed = 0
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"❌ Company {batch[i]['name']} failed: {result}")
            failed += 1
        else:
            successful += 1
    
    print(f"\nBatch {batch_num} completed: ✅ {successful} successful, ❌ {failed} failed")
    return successful, failed

async def main():
    """Main function to orchestrate batch processing"""
    # Initialize MongoDB
    collection = init_mongodb()
    
    # Read companies list
    print("Reading companies list...")
    companies = read_companies_list()
    print(f"Found {len(companies)} companies")
    
    if not companies:
        print("No companies found to process.")
        return
    
    # Process in batches
    batch_size = 2  # Adjust based on your system resources
    batches = [companies[i:i + batch_size] for i in range(0, len(companies), batch_size)]
    total_batches = len(batches)
    
    print(f"\nStarting batch processing:")
    print(f"📊 Total companies: {len(companies)}")
    print(f"📦 Batch size: {batch_size}")
    print(f"🔢 Total batches: {total_batches}")
    
    total_successful = 0
    total_failed = 0
    
    start_time = datetime.utcnow()
    
    for i, batch in enumerate(batches, 1):
        batch_start = datetime.utcnow()
        successful, failed = await process_batch(collection, batch, i, total_batches)
        batch_end = datetime.utcnow()
        
        total_successful += successful
        total_failed += failed
        
        batch_duration = (batch_end - batch_start).total_seconds()
        print(f"⏱️  Batch {i} took {batch_duration:.1f} seconds")
        
        # Optional: Add delay between batches to avoid overwhelming servers
        if i < total_batches:
            delay = 2  # seconds
            print(f"⏸️  Waiting {delay} seconds before next batch...")
            await asyncio.sleep(delay)
    
    end_time = datetime.utcnow()
    total_duration = (end_time - start_time).total_seconds()
    
    print(f"\n{'='*80}")
    print(f"🎉 ALL BATCHES COMPLETED!")
    print(f"{'='*80}")
    print(f"📈 Summary:")
    print(f"   ✅ Total successful: {total_successful}")
    print(f"   ❌ Total failed: {total_failed}")
    print(f"   📊 Success rate: {(total_successful/(total_successful+total_failed)*100):.1f}%")
    print(f"   ⏱️  Total time: {total_duration:.1f} seconds")
    print(f"   🚀 Average per company: {total_duration/len(companies):.1f} seconds")


if __name__ == "__main__":
    asyncio.run(main()) 