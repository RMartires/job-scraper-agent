from browser_use import Agent, BrowserSession, Controller
from browser_use.browser import BrowserProfile
import asyncio
from browser_use.llm import ChatOpenRouter  # Import ChatOpenRouter instead of ChatGoogle
from pydantic import SecretStr, BaseModel
import os
from dotenv import load_dotenv
import re
from lmnr import Laminar, Instruments

# Set the environment variable so Playwright uses your custom browser path
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/media/mats/3c24094c-800b-4576-a390-d23a6d7a02291/workspace/test_ai_gen/browser_use/.playwright-browsers"
# Read environment variables
load_dotenv()


# this line auto-instruments Browser Use and any browser you use (local or remote)
Laminar.initialize(project_api_key="tY4nwVIe2BZHVgMQfaVsBXmtLHSBiDF7U7W9FCSumGXXfYJWcsSW3CB51yMcywZd", disable_batch=True, disabled_instruments={Instruments.BROWSER_USE}) # you can also pass project api key here


# Initialize OpenRouter with any model available on their platform
llm = ChatOpenRouter(
    model='deepseek/deepseek-r1-0528-qwen3-8b:free',  # or any model available on OpenRouter
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

class ResultItem(BaseModel):
    page_link: str | None = None
    query: str | None = None
    source_file: str | None = None
    status: str | None = None
    has_jobs: bool | None = None
    jobs: list[ResultJob] | None = None
    jobs_from_snippet: list[ResultJob] | None = None
    content: dict | None = None

class AgentOutput(BaseModel):
    results: list[ResultItem]

# Don't use Controller with output_model - it conflicts with agent actions
# controller = Controller(output_model=AgentOutput)
controller = Controller()
# --- End structured output additions ---


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

async def run_agent(url, task):
    print("Current task: ", task)
    
    # Define initial actions to navigate to Google first
    initial_actions = [
        {'go_to_url': {'url': url, 'new_tab': True}},
    ]
    
    # Create working profile
    bp = BrowserProfile(
        viewport_size={'width': 1280, 'height': 720},
        user_data_dir="./manual-test-profile",
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
        output_model_schema=AgentOutput
    )

    try:
        history = await agent.run()
        # Since we removed output_model, the agent won't return structured JSON
        # Instead, let's create a simple result based on task completion
        result = history.final_result()
        if result:
            parsed: AgentOutput = AgentOutput.model_validate_json(result)

            for res in parsed.results:
                print('\n--------------------------------')
                print(f'has_jobs:            {res.has_jobs}')
                print(f'status:              {res.status}')
                print(f'page_link:         {res.page_link}')
                print(f'content:             {res.content}')
        else:
            print('No result')

        return [result]
    except Exception as e:
        print(f"Agent failed with error: {e}")
        return [{
            "page_link": url,
            "query": f"Job search for {url}",
            "source_file": None,
            "status": "failed",
            "has_jobs": False,
            "jobs": [],
            "jobs_from_snippet": [],
            "content": {"error": str(e)}
        }]

if __name__ == "__main__":
    # Read and print companies list
    print("Reading companies list...")
    companies = read_companies_list()
    
    print(f"\nFound {len(companies)} companies:")
    print("=" * 80)
    
    for i, company in enumerate(companies, 1):
        print("-" * 100)
        print(f"{i:3d}. {company['name']}")
        print(f"     URL: {company['url']}")

        url = company['url']

        results = asyncio.run(run_agent(url, f'''
            Goal: find if {url} has open job listings.
            - Navigate to the careers/jobs/join-us page via header/footer/nav or search.
            - Confirm it's a jobs page (scroll if needed).
            - Extract all matching roles: Web, Fullstack, Backend, Software (Engineer or Developer).
            - Look for job titles, locations, and URLs.
            - Complete the task when you find job listings or confirm none exist.
        '''))

        # Print all results for now (both success and failed)
        if results:
            print(f"Results: {len(results)}")
            for idx, res in enumerate(results, 1):
                print(f"  [{idx}] Status: {res.get('status')} | Page: {res.get('page_link')}")
                if res.get('status') == 'success':
                    jobs = res.get('jobs') or []
                    print(f"       Jobs found: {len(jobs)}")
                    for j in jobs:
                        print(f"       - {j.get('job_title')} -> {j.get('url')} (location={j.get('location')})")
                else:
                    print(f"       Error: {res.get('content', {}).get('error', 'Unknown error')}")
        else:
            print("No results returned")

        print("-" * 100)

        
