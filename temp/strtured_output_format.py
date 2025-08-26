"""
Show how to use custom outputs.

@dev You need to add OPENAI_API_KEY to your environment variables.
"""

import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv


from pydantic import BaseModel

from browser_use import Agent, ChatOpenAI
from browser_use.llm import ChatOpenRouter  # Import ChatOpenRouter instead of ChatGoogle
from browser_use.browser import BrowserProfile


os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/media/mats/3c24094c-800b-4576-a390-d23a6d7a02291/workspace/test_ai_gen/browser_use/.playwright-browsers"

load_dotenv()

class Post(BaseModel):
    post_title: str
    post_url: str
    num_comments: int
    hours_since_post: int


class Posts(BaseModel):
    posts: list[Post]


def find_chrome():
    base_dir = os.environ["PLAYWRIGHT_BROWSERS_PATH"]
    for name in os.listdir(base_dir):
        if name.startswith("chromium-"):
            chrome_path = os.path.join(base_dir, name, 'chrome-linux', 'chrome')
            if os.path.exists(chrome_path):
                return chrome_path
    return None

CHROME_BIN = find_chrome()



async def main():
    task = 'Go to hackernews show hn and give me the first  5 posts'
    
    llm = ChatOpenRouter(
        model='deepseek/deepseek-r1-0528-qwen3-8b:free',  # or any model available on OpenRouter
        api_key=os.getenv('OPENROUTER_API_KEY'),
        temperature=0.7,
    )

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
        output_model_schema=Posts
    )

    history = await agent.run()

    result = history.final_result()
    if result:
        parsed: Posts = Posts.model_validate_json(result)

        for post in parsed.posts:
            print('\n--------------------------------')
            print(f'Title:            {post.post_title}')
            print(f'URL:              {post.post_url}')
            print(f'Comments:         {post.num_comments}')
            print(f'Hours since post: {post.hours_since_post}')
    else:
        print('No result')


if __name__ == '__main__':
    asyncio.run(main())