import json
import time
from deepeval.dataset import EvaluationDataset
from deepeval.test_case import LLMTestCase
from deepeval.metrics import AnswerRelevancyMetric
from deepeval.models import GeminiModel, LocalModel
from deepeval import evaluate
import asyncio
import os
from dotenv import load_dotenv
from lib.main import extract_job_listings, find_jobs_page

# Load environment variables
load_dotenv()

# Set the environment variable so Playwright uses your custom browser path
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/media/mats/3c24094c-800b-4576-a390-d23a6d7a02291/workspace/test_ai_gen/browser_use/.playwright-browsers"

# Configuration for rate limiting
ENABLE_THROTTLING = True  # Set to False to use parallel evaluation
THROTTLE_DELAY_SECONDS = 5  # Delay between evaluations in seconds

def create_test_dataset():
    """Create a simple test dataset for job scraping evaluation"""
    test_cases = [
        {
            "has_job_page_input": "https://www.google.com/careers",
            "extract_jobs_listings_input": "https://www.google.com/careers",
            "has_job_page_expected_output": "Should find if the site has a jobs / careers page",
            "extract_jobs_listings_output": "Should return a list of jobs with url, location and title fields",
            "description": "Test Google careers page for job listings"
        },
        {   
            "has_job_page_input": "https://www.datarobot.com",    
            "extract_jobs_listings_input": "https://www.datarobot.com/careers/open-positions/",
            "has_job_page_expected_output": "Should find if the site has a jobs / careers page",
            "extract_jobs_listings_output": "Should return a list of jobs with url, location and title fields",
            "description": "Test datarobot careers page for job listings"
        },
        # {
        #     "has_job_page_input": "https://www.cencora.com",    
        #     "extract_jobs_listings_input": "https://careers.cencora.com/us/en",
        #     "has_job_page_expected_output": "Should find if the site has a jobs / careers page",
        #     "extract_jobs_listings_output": "Should return a list of jobs with url, location and title fields",
        #     "description": "Test Apple jobs page for job listings"
        # }
    ]
    return test_cases

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
        # eval_llm = GeminiModel(
        #     model_name="gemini-2.0-flash",  # Use the correct model name from deepeval
        #     api_key=os.getenv('GOOGLE_API_KEY')
        # )

        eval_llm = LocalModel(
            model="deepseek/deepseek-r1:free",              # OpenRouter model name
            base_url="https://openrouter.ai/api/v1",        # OpenRouter API endpoint (from docs)
            api_key=os.getenv('OPENROUTER_API_KEY'),        # Your OpenRouter API key
            temperature=0.7                                 # Low temperature for consistent evaluation
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
        print(f"   Processing: {test_item['has_job_page_input']}")
        
        # Get actual output from your LLM app
        fjp_output = await find_jobs_page(test_item['has_job_page_input'], return_string=True)

        # Ensure actual_output is always a string
        fjp_actual_output = str(fjp_output) if fjp_output is not None else "No output generated"

        # Create test case
        fjp_test_case = LLMTestCase(
            input=test_item['has_job_page_input'],
            actual_output=fjp_actual_output,
            expected_output=test_item['has_job_page_expected_output']
        )

        print(f"   Processing: {test_item['extract_jobs_listings_input']}")

        ejl_output = await extract_job_listings(test_item['extract_jobs_listings_input'], return_string=True)

        # Ensure actual_output is always a string
        ejl_actual_output = str(ejl_output) if ejl_output is not None else "No output generated"

        # Create test case
        ejl_test_case = LLMTestCase(
            input=test_item['extract_jobs_listings_input'],
            actual_output=ejl_actual_output,
            expected_output=test_item['extract_jobs_listings_output']
        )
        
        # Add to dataset
        dataset.add_test_case(fjp_test_case)
        dataset.add_test_case(ejl_test_case)
    
    # Step 4: Run evaluation with throttling
    print("4. Running evaluation...")
    try:
        if ENABLE_THROTTLING:
            print("   Using throttled evaluation to avoid rate limits...")
            # Sequential evaluation with delays
            results = []
            for i, test_case in enumerate(dataset.test_cases):
                print(f"   Evaluating test case {i+1}/{len(dataset.test_cases)}...")
                try:
                    result = evaluate(
                        test_cases=[test_case], 
                        metrics=[relevancy]
                    )
                    results.append(result)
                    print(f"   ✅ Test case {i+1} completed")
                except Exception as e:
                    print(f"   ❌ Test case {i+1} failed: {e}")
                    results.append(None)
                
                # Add delay between evaluations
                if i < len(dataset.test_cases) - 1:  # Don't delay after the last one
                    print(f"   ⏳ Waiting {THROTTLE_DELAY_SECONDS} seconds before next evaluation...")
                    time.sleep(THROTTLE_DELAY_SECONDS)
            
            # Filter out failed evaluations
            results = [r for r in results if r is not None]
            
        else:
            print("   Using parallel evaluation...")
            # Parallel evaluation (original behavior)
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