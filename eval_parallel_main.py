import json
import asyncio
import os
import time
from datetime import datetime
from dotenv import load_dotenv
from deepeval.dataset import EvaluationDataset
from deepeval.test_case import LLMTestCase
from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
from deepeval.models import LocalModel
from deepeval import evaluate
import traceback
from pymongo import MongoClient
from lib.main import (
    extract_job_listings, 
    find_jobs_page, 
    process_single_company,
    process_batch,
    init_mongodb,
    read_companies_list
)

# Load environment variables
load_dotenv()

# Set the environment variable so Playwright uses your custom browser path
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/media/mats/3c24094c-800b-4576-a390-d23a6d7a02291/workspace/test_ai_gen/browser_use/.playwright-browsers"

class DeepEvalJobScrapingEvaluator:
    """LLM-based evaluator for parallel job scraping implementation using DeepEval"""
    
    def __init__(self):
        self.collection = init_mongodb()
        self.eval_llm = self._setup_evaluation_llm()
        self.metrics = self._setup_metrics()
        
    def _setup_evaluation_llm(self):
        """Setup the evaluation LLM"""
        try:
            eval_llm = LocalModel(
                model="deepseek/deepseek-r1:free",
                base_url="https://openrouter.ai/api/v1",
                api_key=os.getenv('OPENROUTER_API_KEY'),
                temperature=0.3  # Lower temperature for consistent evaluation
            )
            print("✅ Successfully configured LocalModel for evaluation")
            return eval_llm
        except Exception as e:
            print(f"⚠️  Warning: Could not configure LocalModel: {e}")
            return None
    
    def _setup_metrics(self):
        """Setup evaluation metrics"""
        metrics = []
        try:
            if self.eval_llm:
                metrics.append(AnswerRelevancyMetric(model=self.eval_llm))
                # metrics.append(FaithfulnessMetric(model=self.eval_llm))
            else:
                metrics.append(AnswerRelevancyMetric())
                # metrics.append(FaithfulnessMetric())
            print(f"✅ Successfully configured {len(metrics)} evaluation metrics")
        except Exception as e:
            print(f"⚠️  Warning: Could not configure metrics: {e}")
            metrics = [AnswerRelevancyMetric()]  # Fallback to basic metric
        return metrics
    
    def create_test_companies(self):
        """Create a test dataset of companies for evaluation"""
        test_companies = [
            {
                "name": "Google",
                "url": "https://www.google.com/careers",
                "expected_has_jobs": True,
                "expected_jobs_url": "https://www.google.com/careers/jobs/results/",
                "category": "large_tech"
            },
            {
                "name": "DataRobot",
                "url": "https://www.datarobot.com",
                "expected_has_jobs": True,
                "expected_jobs_url": "https://www.datarobot.com/careers/",
                "category": "ai_company"
            },
            {
                "name": "GitHub",
                "url": "https://github.com",
                "expected_has_jobs": True,
                "expected_jobs_url": "https://github.com/about/careers",
                "category": "dev_platform"
            }
        ]
        return test_companies

    async def create_llm_evaluation_dataset_using_main_functions(self):
        """Create dataset for LLM evaluation using existing main.py functions directly"""
        print("\n🤖 Creating LLM Evaluation Dataset Using Existing main.py Functions")
        print("=" * 80)
        
        # Get test companies
        test_companies = self.create_test_companies()
        print(f"Found {len(test_companies)} test companies")
        
        # Clear previous evaluation results for these companies
        if self.collection is not None:
            for company in test_companies:
                self.collection.delete_many({
                    'company_name': company['name'], 
                    'company_url': company['url']
                })
            print("🧹 Cleared previous evaluation results")
        
        # Use the existing batch processing from main.py
        batch_size = 2  # Small batches for evaluation
        batches = [test_companies[i:i + batch_size] for i in range(0, len(test_companies), batch_size)]
        total_batches = len(batches)
        
        print(f"\nStarting batch processing using main.py functions:")
        print(f"📊 Total companies: {len(test_companies)}")
        print(f"📦 Batch size: {batch_size}")
        print(f"🔢 Total batches: {total_batches}")
        print(f"⚡ Using existing process_batch and process_single_company functions")
        
        total_successful = 0
        total_failed = 0
        start_time = datetime.utcnow()
        
        # Process each batch using existing main.py functions
        for i, batch in enumerate(batches, 1):
            batch_start = datetime.utcnow()
            
            # Use the existing process_batch function directly!
            successful, failed = await process_batch(self.collection, batch, i, total_batches)
            
            total_successful += successful
            total_failed += failed
            
            batch_end = datetime.utcnow()
            batch_duration = (batch_end - batch_start).total_seconds()
            print(f"⏱️  Batch {i} took {batch_duration:.1f} seconds")
            
            # Optional: Add delay between batches
            if i < total_batches:
                delay = 1  # seconds
                print(f"⏸️  Waiting {delay} seconds before next batch...")
                await asyncio.sleep(delay)
        
        end_time = datetime.utcnow()
        total_duration = (end_time - start_time).total_seconds()
        
        print(f"\n{'='*80}")
        print(f"🎉 BATCH PROCESSING COMPLETED!")
        print(f"{'='*80}")
        print(f"📈 Summary:")
        print(f"   ✅ Total successful: {total_successful}")
        print(f"   ❌ Total failed: {total_failed}")
        print(f"   📊 Success rate: {(total_successful/(total_successful+total_failed)*100):.1f}%")
        print(f"   ⏱️  Total time: {total_duration:.1f} seconds")
        
        # Now read the results from MongoDB to create evaluation dataset
        return await self._create_dataset_from_mongodb_results(test_companies)
    
    async def _create_dataset_from_mongodb_results(self, test_companies):
        """Create DeepEval dataset from MongoDB results"""
        print("\n📋 Creating DeepEval Dataset from MongoDB Results")
        print("-" * 60)
        
        if self.collection is None:
            print("❌ No MongoDB collection available")
            return EvaluationDataset(), []
        
        dataset = EvaluationDataset()
        all_results = []
        
        for company in test_companies:
            # Query MongoDB for this company's results
            company_result = self.collection.find_one({
                'company_name': company['name'],
                'company_url': company['url']
            })
            
            if company_result:
                print(f"📊 Processing results for {company['name']}")
                all_results.append(company_result)
                
                # Create test case for find_jobs_page functionality
                fjp_test_case = LLMTestCase(
                    input=f"Find jobs page for {company['name']} at {company['url']}",
                    actual_output=json.dumps({
                        'has_jobs_page': company_result.get('has_job_page', False),
                        'jobs_page_url': company_result.get('jobs_page_url', None),
                        'status': company_result.get('status', 'unknown')
                    }),
                    expected_output=f"Should identify if {company['url']} has a careers/jobs page and return the URL if found. Company: {company['name']}, Expected to find jobs page: {company['expected_has_jobs']}"
                )
                dataset.add_test_case(fjp_test_case)
                
                # Create test case for extract_job_listings functionality if jobs were found
                if company_result.get('jobs') and len(company_result['jobs']) > 0:
                    ejl_test_case = LLMTestCase(
                        input=f"Extract job listings for {company['name']} from {company_result.get('jobs_page_url', 'jobs page')}",
                        actual_output=json.dumps({
                            'jobs_found': len(company_result['jobs']),
                            'jobs': company_result['jobs'][:3] if len(company_result['jobs']) > 3 else company_result['jobs'],  # Limit to first 3 for readability
                            'status': company_result.get('status', 'unknown')
                        }),
                        expected_output=f"Should extract job listings with title, location, and URL fields for {company['name']}. Should focus on tech roles like Web, Fullstack, Backend, Software Engineer/Developer. Found {len(company_result['jobs'])} jobs."
                    )
                    dataset.add_test_case(ejl_test_case)
                    
            else:
                print(f"⚠️  No results found in MongoDB for {company['name']}")
        
        print(f"\n📋 Created {len(dataset.test_cases)} test cases for LLM evaluation")
        return dataset, all_results
    
    async def run_llm_evaluation(self, dataset):
        """Run LLM-based evaluation"""
        print("\n🎯 Running LLM Evaluation with DeepEval")
        print("=" * 60)
        
        if not self.metrics:
            print("⚠️  No metrics available for LLM evaluation")
            return None
        
        if len(dataset.test_cases) == 0:
            print("⚠️  No test cases available for evaluation")
            return None
        
        try:
            print(f"📊 Evaluating {len(dataset.test_cases)} test cases...")
            results = evaluate(
                test_cases=dataset.test_cases,
                metrics=self.metrics
            )
            
            print("✅ LLM Evaluation completed!")
            
            # Print detailed results
            print("\n📊 Detailed LLM Evaluation Results:")
            print("-" * 60)
            for i, test_case in enumerate(dataset.test_cases):
                print(f"\nTest Case {i+1}:")
                print(f"  Input: {test_case.input[:80]}...")
                print(f"  Expected: {test_case.expected_output[:80]}...")
                print(f"  Actual: {test_case.actual_output[:80]}..." if test_case.actual_output else "  Actual: None")
                
                # Try to extract scores from results
                try:
                    if hasattr(test_case, 'score') and test_case.score is not None:
                        print(f"  Score: {test_case.score}")
                except:
                    pass
            
            # Summary statistics
            print(f"\n📈 Evaluation Summary:")
            print(f"  Total test cases: {len(dataset.test_cases)}")
            print(f"  Metrics used: {len(self.metrics)}")
            
            return results
            
        except Exception as e:
            print(f"❌ LLM Evaluation failed: {e}")
            traceback.print_exc()
            return None

async def main():
    """Main evaluation function - uses existing main.py functions directly"""
    print("🚀 Starting DeepEval LLM Evaluation Using Existing main.py Functions")
    print("=" * 80)
    
    evaluator = DeepEvalJobScrapingEvaluator()
    
    try:
        # Use existing main.py functions to process companies and create evaluation dataset
        print("\n🔄 Using existing process_batch and process_single_company functions...")
        dataset, processing_results = await evaluator.create_llm_evaluation_dataset_using_main_functions()
        
        if len(dataset.test_cases) > 0:
            # Run LLM evaluation
            await evaluator.run_llm_evaluation(dataset)
            
            print(f"\n🎉 DeepEval evaluation completed successfully!")
            print(f"📊 Processed {len(processing_results)} companies using existing main.py functions")
            print(f"📋 Evaluated {len(dataset.test_cases)} test cases with LLM")
        else:
            print("⚠️  No test cases created for LLM evaluation")
        
    except Exception as e:
        print(f"❌ Evaluation failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main()) 