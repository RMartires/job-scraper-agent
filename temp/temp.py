from browser_use import Agent, Browser, BrowserConfig
import asyncio
from browser_use.llm import ChatOpenRouter  # Import ChatOpenRouter instead of ChatGoogle
from pydantic import SecretStr
import os
from dotenv import load_dotenv

# Set the environment variable so Playwright uses your custom browser path
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/media/mats/3c24094c-800b-4576-a390-d23a6d7a0229/workspace/test_ai_gen/browser_use/.playwright-browsers"

# Read environment variables
load_dotenv()

# Initialize OpenRouter with any model available on their platform
llm = ChatOpenRouter(
    model='deepseek/deepseek-r1-0528-qwen3-8b:free',  # or any model available on OpenRouter
    api_key=os.getenv('OPENROUTER_API_KEY'),
    temperature=0.7,
)

browser = Browser()

agent = None 

async def run_agent(task):
    print("Current task: ", task)
    global agent
    context = await browser.new_context()
    
    # Define initial actions to navigate to Google first
    initial_actions = [
        {'go_to_url': {'url': 'https://www.google.com', 'new_tab': False}},
    ]
    
    if agent is None:
        agent = Agent(
            task=task,
            llm=llm,
            browser_session=browser,
            initial_actions=initial_actions,
        )
    else:
        agent.add_new_task(task)

    await agent.run()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    # loop.run_until_complete(run_agent('''
    #     go to https://github.com/remoteintech/remote-jobs?tab=readme-ov-file

    #     and go to each company site and check the carrer page, seach if they are hiring for software engineers

    #     once you find a listing just dump the list of sites that have these job listings into a file called output.json
    # '''
    # ))    
    loop.run_until_complete(run_agent('''
        go to this url: https://10up.com/ 
        
        - dirltly load this url in a page

        and check the carrers or jobs or join-us page, try to find similar job pages on the site check the footer or header section if you cant find any

        then after finding a valid carrer page, go through the entire page to find if any lists of jobs are found

        seach for listing for Web , Fullstack, Backend, Software (Engineer or Developer)

        once you find a listing just dump the list of these listings into a file called output.json

        format:
        - job title:
        - url:

        you should end the task after finding the listings or if not found also end the task
    '''
    ))

    loop.close()