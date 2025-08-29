from deepeval.dataset import EvaluationDataset
from deepeval.test_case import LLMTestCase
from deepeval.metrics import AnswerRelevancyMetric
from deepeval.models import GeminiModel
from deepeval import evaluate
import asyncio
import os
from dotenv import load_dotenv
from lib.main import extract_job_listings, find_jobs_page

# Load environment variables
load_dotenv()

# Set the environment variable so Playwright uses your custom browser path
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/media/mats/3c24094c-800b-4576-a390-d23a6d7a02291/workspace/test_ai_gen/browser_use/.playwright-browsers"

def create_test_dataset():
    """Create a simple test dataset for job scraping evaluation"""
    test_cases = [
        {
            "input": "https://www.google.com/careers",
            "expected_output": "Should find if the site has a jobs / careers page",
            "description": "Test Google careers page for job listings"
        },
        # {
        #     "input": "https://www.microsoft.com/careers",
        #     "expected_output": "Should find job listings or careers page", 
        #     "description": "Test Microsoft careers page for job listings"
        # },
        # {
        #     "input": "https://www.apple.com/jobs",
        #     "expected_output": "Should find job listings or careers page",
        #     "description": "Test Apple jobs page for job listings"
        # }
    ]
    return test_cases

async def llm_app(input_url):
    """Your LLM app function that processes a URL and returns job listings"""
    try:
        # First, try to find the jobs page
        jobs_page_result = await find_jobs_page(input_url, f'''
            Goal: find if {input_url} has open job listings page
            - Navigate to the careers/jobs/join-us page via header/footer/nav or search.
            - Confirm it's a jobs page (scroll if needed). you should see a list of job listings
            - if it exists return the url of the jobs page
        ''')

        # Convert the result to a string for evaluation
        if jobs_page_result['has_jobs_page']:
            return f"jobs_page_url: {jobs_page_result['jobs_page_url']}, has_jobs_page: {jobs_page_result['has_jobs_page']}"
        else:
            return "jobs_page_url: '', has_jobs_page: False"
        
        # if jobs_page_result['has_jobs_page'] and jobs_page_result['jobs_page_url']:
        #     # If jobs page found, extract job listings
        #     job_listings_result = await extract_job_listings(jobs_page_result['jobs_page_url'], f'''
        #         Goal: find if {jobs_page_result['jobs_page_url']} 
        #         - Confirm it's a jobs page (scroll if needed).
        #         - Extract all matching roles: Web, Fullstack, Backend, Software (Engineer or Developer).
        #         - Look for job titles, locations, and URLs.
        #         - Complete the task when you find job listings or confirm none exist.
        #     ''')
            
        #     if job_listings_result['has_jobs']:
        #         return f"Found {len(job_listings_result['jobs'])} job listings on {input_url}"
        #     else:
        #         return f"No job listings found on {input_url}"
        # else:
        #     return f"No jobs page found for {input_url}"
            
    except Exception as e:
        return f"Error processing {input_url}: {str(e)}"

async def main():
    print("🚀 Starting LLM Evaluation for Job Scraping")
    
    # Step 1: Create a dataset
    print("\n1. Creating test dataset...")
    test_data = create_test_dataset()
    
    # Step 2: Configure LLM for evaluation
    print("2. Setting up evaluation LLM with OpenRouter...")
    
    # Check if OpenRouter API key is available
    if not os.getenv('GOOGLE_API_KEY'):
        print("⚠️  Warning: GOOGLE_API_KEY not found in environment variables")
        return
    
    # Configure deepeval to use OpenRouter for evaluation
    try:
        # Method 1: Try using DeepSeekModel with correct model name
        eval_llm = GeminiModel(
            model_name="gemini-2.0-flash",  # Use the correct model name from deepeval
            api_key=os.getenv('GOOGLE_API_KEY')
        )
        
        # Create metric with the configured LLM
        relevancy = AnswerRelevancyMetric(model=eval_llm)
        print("✅ Successfully configured GeminiModel for evaluation")
        
    except Exception as e:
        print(f"⚠️  Warning: Could not configure DeepSeekModel: {e}")
        
        # Method 2: Try using environment variables approach
        try:
            print("   Trying environment variables approach...")
            # Set environment variables for OpenRouter
            os.environ["OPENAI_API_KEY"] = os.getenv('OPENROUTER_API_KEY')
            os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"
            
            # Use default AnswerRelevancyMetric which should now use OpenRouter
            relevancy = AnswerRelevancyMetric()
            print("✅ Successfully configured OpenRouter using environment variables")
            
        except Exception as e2:
            print(f"⚠️  Warning: Could not configure OpenRouter: {e2}")
            print("   Falling back to default configuration (may require OpenAI API key)")
            relevancy = AnswerRelevancyMetric()
    
    # Step 3: Create test cases and run evaluation
    print("3. Creating test cases and running evaluation...")
    
    # Create dataset object
    dataset = EvaluationDataset()
    
    # Convert test data into test cases
    for test_item in test_data:
        print(f"   Processing: {test_item['input']}")
        
        # Get actual output from your LLM app
        actual_output = await llm_app(test_item['input'])
        
        # Create test case
        test_case = LLMTestCase(
            input=test_item['input'],
            actual_output=actual_output,
            expected_output=test_item['expected_output']
        )
        
        # Add to dataset
        dataset.add_test_case(test_case)
    
    # Step 4: Run evaluation
    print("4. Running evaluation...")
    try:
        results = evaluate(
            test_cases=dataset.test_cases, 
            metrics=[relevancy]
        )
        
        print("\n✅ Evaluation completed!")
        print(f"Results: {results}")
        
        # Print detailed results
        print("\n📊 Detailed Results:")
        for i, test_case in enumerate(dataset.test_cases):
            print(f"\nTest Case {i+1}:")
            print(f"  Input: {test_case.input}")
            print(f"  Expected: {test_case.expected_output}")
            print(f"  Actual: {test_case.actual_output}")
            if hasattr(test_case, 'score') and test_case.score is not None:
                print(f"  Score: {test_case.score}")
                
    except Exception as e:
        print(f"❌ Evaluation failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Run the evaluation
    asyncio.run(main()) 