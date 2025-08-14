from browser_use import Agent, BrowserSession
from browser_use.browser import BrowserProfile
import asyncio
from browser_use.llm import ChatOpenRouter  # Import ChatOpenRouter instead of ChatGoogle
from pydantic import SecretStr
import os
from dotenv import load_dotenv
import re
import uuid

# Set the environment variable so Playwright uses your custom browser path
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/media/mats/3c24094c-800b-4576-a390-d23a6d7a0229/workspace/test_ai_gen/browser_use/.playwright-browsers"

# Ensure all temp files go to a workspace-backed directory (not /tmp)
os.environ["TMPDIR"] = "/media/mats/3c24094c-800b-4576-a390-d23a6d7a0229/workspace/test_ai_gen/browser_use/.tmp"
os.makedirs(os.environ["TMPDIR"], exist_ok=True)

# Move browser-use config/cache under workspace to avoid using root FS
os.environ["BROWSER_USE_CONFIG_DIR"] = "/media/mats/3c24094c-800b-4576-a390-d23a6d7a0229/workspace/test_ai_gen/browser_use/.browseruse-config"
os.makedirs(os.environ["BROWSER_USE_CONFIG_DIR"], exist_ok=True)

# Prepare browser profile data directories
_base = "/media/mats/3c24094c-800b-4576-a390-d23a6d7a0229/workspace/test_ai_gen/browser_use"
_downloads_dir = os.path.join(_base, ".tmp", "downloads")
_traces_dir = os.path.join(_base, ".tmp", "traces")
_user_data_dir = os.path.join(_base, ".browser-user-data")
for _d in (_downloads_dir, _traces_dir, _user_data_dir):
    os.makedirs(_d, exist_ok=True)

# Read environment variables
load_dotenv()

# Initialize OpenRouter with any model available on their platform
llm = ChatOpenRouter(
    model='deepseek/deepseek-r1-0528-qwen3-8b:free',  # or any model available on OpenRouter
    api_key=os.getenv('OPENROUTER_API_KEY'),
    temperature=0.7,
)

# Configure browser with custom viewport size
browser_profile = BrowserProfile(
    viewport_size={'width': 480, 'height': 270},
    downloads_path=_downloads_dir,
    traces_dir=_traces_dir,
    user_data_dir=_user_data_dir,
)

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
    
    # Create a new agent for each task
    unique_id = uuid.uuid4().hex
    agent_fs_dir = os.path.join(os.environ["TMPDIR"], f"browser_use_agent_{unique_id}")
    os.makedirs(agent_fs_dir, exist_ok=True)

    agent = Agent(
        task=task,
        llm=llm,
        browser_profile=browser_profile,
        initial_actions=initial_actions,
        file_system_path=agent_fs_dir,
        task_id=unique_id,
    )

    await agent.run()

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

        asyncio.run(run_agent(url, f'''
            Goal: to find if this site has open job listings at site: {url}

            - search for the carrers or jobs or join-us page, try to find this page. you can check the footer or header section for links to this page

            this page will have a list of jobs on it, make sure to scroll the entire page to make sure we are on a career page

            - then after finding a valid carrer page, go through the entire list to check for jobs that match            
            Web , Fullstack, Backend, Software (Engineer or Developer)

            once you find a listing just dump the list of these listings into a file called output.json, do not overwrite append it

            format:
            - job title:
            - job listing url:
            - main comany url:

            IMPORTANT: you should end the task after finding the listings or if not found any listings also end the task but do not write anything to the file
        '''))

        print("-" * 100)

    
