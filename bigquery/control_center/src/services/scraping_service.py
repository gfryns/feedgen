import asyncio
import aiohttp
from bs4 import BeautifulSoup
from google.cloud import aiplatform
from vertexai.generative_models import GenerativeModel
from services.bq_client import get_bq_client
import csv
import os
from google.cloud import bigquery

async def detect_css_selector(project: str, dataset: str, url_col: str, sample_count: int = 5, log_cb=print) -> str:
    """Uses Gemini to detect the CSS selector for product descriptions."""
    client = get_bq_client(project)
    source_table = "InputFiltered"
    
    # Fetch sample URLs
    query = f"SELECT url FROM `{project}.{dataset}.{source_table}` WHERE url IS NOT NULL ORDER BY RAND() LIMIT {sample_count}"
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(None, lambda: list(client.query(query).result()))
    
    if not results:
        raise ValueError("No URLs found in the table!")
        
    urls = [row['url'] for row in results]
    log_cb(f"Fetching {len(urls)} sample pages...\n")
    
    cleaned_htmls = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                async with session.get(url, headers=headers, timeout=15) as response:
                    response.raise_for_status()
                    html = await response.text()
                    
                    # Clean HTML
                    soup = BeautifulSoup(html, 'html.parser')
                    for script in soup(["script", "style"]):
                        script.decompose()
                    cleaned_htmls.append(str(soup))
            except Exception as e:
                log_cb(f"Warning: Error fetching {url}: {e}\n")
                
    if not cleaned_htmls:
        raise ValueError("Failed to fetch any sample pages!")
        
    log_cb("Calling Gemini to analyze HTML...\n")
    
    aiplatform.init(project=project)
    model = GenerativeModel("gemini-1.5-flash")
    
    # Construct prompt with all HTMLs
    prompt = "You are an expert web scraper. Analyze the following HTML contents of product pages.\n"
    prompt += f"Identify the CSS selector that consistently contains the product description across ALL {len(cleaned_htmls)} pages.\n"
    prompt += "Return ONLY the CSS selector string (e.g., `.product-description` or `#desc`).\n"
    prompt += "Do not include any other text, markdown, or explanation.\n\n"
    
    for i, html_content in enumerate(cleaned_htmls):
        prompt += f"--- Page {i+1} ---\n{html_content[:30000]}\n\n"
        
    def call_gemini():
        response = model.generate_content(prompt)
        return response.text.strip()
        
    selector = await loop.run_in_executor(None, call_gemini)
    
    # Clean up response
    selector = selector.replace('`', '').replace('"', '').replace("'", "").strip()
    return selector

async def run_web_scraping(project: str, dataset: str, selector: str, log_cb=print, progress_cb=None, is_cancelled=lambda: False) -> dict:
    """Runs the bulk web scraping process and loads results to BigQuery."""
    client = get_bq_client(project)
    source_table = "InputFiltered"
    dest_table = "InputFilteredWeb"
    
    query = f"SELECT id, url FROM `{project}.{dataset}.{source_table}`"
    log_cb(f"Fetching URLs with query: {query}\n")
    
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(None, lambda: list(client.query(query).result()))
    
    csv_filename = "ids_contents.csv"
    log_cb(f"Found {len(results)} rows. Scraping pages...\n")
    
    if progress_cb:
        progress_cb(total=len(results), progress=0)
        
    total = len(results)
    success = 0
    extracted = 0
    failed = 0
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    semaphore = asyncio.Semaphore(20)
    
    async def fetch_and_parse(session, row):
        nonlocal success, extracted, failed
        item_id = row['id']
        url = row['url']
        content = ""
        
        async with semaphore:
            if is_cancelled(): return item_id, content
            try:
                async with session.get(url, headers=headers, timeout=15) as response:
                    response.raise_for_status()
                    html = await response.text()
                    success += 1
                    
                    soup = BeautifulSoup(html, 'html.parser')
                    elements = soup.select(selector)
                    content = " ".join(el.get_text() for el in elements)
                    
                    content = content.replace('\n', ' ').replace('\r', '').strip()
                    content = " ".join(content.split())
                    
                    if content:
                        extracted += 1
                    else:
                        failed += 1
            except Exception:
                failed += 1
                
            if progress_cb:
                progress_cb(advance=1)
            return item_id, content
            
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_and_parse(session, row) for row in results]
        parsed_results = await asyncio.gather(*tasks)
        
    if is_cancelled():
        log_cb("Scraping cancelled.\n")
        return {'cancelled': True}

    with open(csv_filename, mode='w', newline='', encoding='utf-8') as csv_file:
        fieldnames = ['id', 'content']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        for item_id, content in parsed_results:
            writer.writerow({'id': item_id, 'content': content})

    log_cb("Loading data to BigQuery...\n")
    
    table_id = f"{project}.{dataset}.{dest_table}"
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=0,
        schema=[
            bigquery.SchemaField("id", "STRING"),
            bigquery.SchemaField("content", "STRING"),
        ],
        write_disposition="WRITE_TRUNCATE",
    )
    
    with open(csv_filename, "rb") as source_file:
        load_job = client.load_table_from_file(source_file, table_id, job_config=job_config)
        
    await loop.run_in_executor(None, load_job.result)
    
    log_cb(f"Job finished. Loaded data to {table_id}\n")
    
    if os.path.exists(csv_filename):
        os.remove(csv_filename)
        
    return {
        'total': total,
        'success': success,
        'extracted': extracted,
        'failed': failed
    }
