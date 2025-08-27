# Job Scraper Agent

A Python-based job scraping agent that uses browser automation to extract job listings from company websites.

## Features

- Automated browser navigation using `browser-use`
- Job listing extraction from company career pages
- MongoDB integration for data storage
- Support for multiple companies via markdown file input
- Structured output using Pydantic models

## Prerequisites

- Python 3.11 or higher (required for browser-use package)
- MongoDB database (local or cloud)
- OpenRouter API key for LLM integration

## Setup

### Option 1: Automated Setup (Recommended)

#### On macOS/Linux:
```bash
chmod +x setup.sh
./setup.sh
```

#### On Windows:
```cmd
setup.bat
```

### Option 2: Manual Setup

1. Create a virtual environment:
```bash
python3 -m venv venv
```

2. Activate the virtual environment:
```bash
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate.bat
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install Playwright browsers:
```bash
playwright install chromium
```

## Environment Variables

Create a `.env` file in the root directory with the following variables:

```env
OPENROUTER_API_KEY=your_openrouter_api_key_here
MONGODB_URI=your_mongodb_connection_string_here
```

## Usage

1. Ensure your virtual environment is activated
2. Make sure your `.env` file is configured
3. Run the main script:

```bash
python temp/tempv2.py
```

## Project Structure

```
job-scraper-agent/
├── temp/
│   ├── tempv2.py          # Main job scraping script
│   ├── temp.py            # Alternative implementation
│   ├── strtured_output_format.py  # Example structured output
│   └── companies_list.md  # Company data input file
├── requirements.txt       # Python dependencies
├── setup.sh              # Unix/macOS setup script
├── setup.bat             # Windows setup script
└── README.md             # This file
```

## Dependencies

- `browser-use`: Browser automation framework
- `pydantic`: Data validation and serialization
- `python-dotenv`: Environment variable management
- `lmnr`: Monitoring and instrumentation
- `pymongo`: MongoDB database driver

## Notes

- The script uses a custom Chrome browser path. You may need to adjust the `PLAYWRIGHT_BROWSERS_PATH` environment variable in the scripts.
- The MongoDB connection string in the code should be updated with your own credentials.
- The Laminar API key in the code should be replaced with your own key.

## Troubleshooting

1. **Playwright browser not found**: Run `playwright install chromium` after activating your virtual environment.

2. **MongoDB connection issues**: Verify your MongoDB connection string and ensure the database is accessible.

3. **OpenRouter API issues**: Check your API key and ensure you have sufficient credits.

4. **Permission errors on setup script**: Run `chmod +x setup.sh` to make the script executable.
