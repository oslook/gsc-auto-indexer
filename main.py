import os
import csv
import xml.etree.ElementTree as ET
from urllib.request import urlopen, Request
from urllib.parse import urlparse, urljoin
from urllib.error import HTTPError
from google.oauth2 import service_account
from googleapiclient.discovery import build
from prompt_toolkit.shortcuts import prompt
from prompt_toolkit.shortcuts import confirm

# optional flags
INDEX_FROM_CSV = False  # if True, read URLs from CSV file "urls.csv"

# service account file
SERVICE_ACCOUNT_FILE = "service_account.json"  # replace with your JSON file name

# scopes
SCOPES = ["https://www.googleapis.com/auth/webmasters"]

def get_all_site_urls(service):
    """Get all accessible site URLs."""
    sites = service.sites().list().execute()
    return [site['siteUrl'] for site in sites.get('siteEntry', [])]

def get_sitemap_url(service, site_url):
    """Get sitemap URL from Google Search Console."""
    sitemaps = service.sitemaps().list(siteUrl=site_url).execute()
    if sitemaps.get('sitemap'): # check if sitemap exists
        return sitemaps['sitemap'][0]['path']
    else:
        return None  # if no sitemap, return None

def get_all_pages_from_sitemap(url):
    """Parse all page URLs from sitemap."""
    try:
        # Create a request with headers to mimic a browser request
        req = Request(
            url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/xml,application/xml,application/xhtml+xml,text/html;q=0.9,text/plain;q=0.8,image/png,*/*;q=0.5',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive'
            }
        )
        
        # Add error handling for HTTP errors
        try:
            with urlopen(req, timeout=10) as response:
                if response.status != 200:
                    print(f"HTTP Error {response.status} for URL: {url}")
                    return []
                xml_data = response.read()
                
                # Parse the XML data
                root = ET.fromstring(xml_data)
                namespaces = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                links = [element.find('ns:loc', namespaces).text for element in root.findall('ns:url', namespaces)]
                return links
                
        except HTTPError as e:
            print(f"HTTP Error {e.code} for URL: {url}")
            return []
            
    except Exception as e:
        print(f"Error parsing sitemap: {e}, {url}")
        return []

def get_all_pages_from_csv(path):
    """Read all page URLs from CSV file."""
    try:
        with open(path, 'r', newline='') as csvfile:
            reader = csv.reader(csvfile)
            for row in reader:
                return row # assume all URLs are in one line
    except FileNotFoundError:
        print(f"CSV file not found: {path}")
        return []

def submit_index_request(service, site_url, page_url):
    """Submit index request to Google Search Console."""
    try:
        request = {
            'inspectionUrl': page_url,
            'siteUrl': site_url
        }
        response = service.urlInspection().index().inspect(body=request).execute()
        return response
    except Exception as e:
        print(f"Error submitting index request: {e}")
        return None

def main():
    """Main function."""

    # authentication
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    service = build('searchconsole', 'v1', credentials=credentials)

    # select site
    all_site_urls = get_all_site_urls(service)
    if not all_site_urls:
        print("No accessible sites. Please check your service account permissions.")
        return

    print("\nAvailable sites:")
    for i, url in enumerate(all_site_urls, 1):
        print(f"{i}. {url}")
    selected_site_url = prompt("Select a site number: ")
    try:
        site_index = int(selected_site_url) - 1
        selected_site_url = all_site_urls[site_index]
    except (ValueError, IndexError):
        print("Invalid selection")
        return

    # determine pages to index
    pages_to_index = []
    if INDEX_FROM_CSV:
        pages_to_index = get_all_pages_from_csv("urls.csv")
        print(f"Found {len(pages_to_index)} pages in urls.csv:")
        print(pages_to_index)
    else:
        sitemap_url = get_sitemap_url(service, selected_site_url)
        if sitemap_url:
            pages_to_index = get_all_pages_from_sitemap(sitemap_url)
            print(f"Found {len(pages_to_index)} pages in sitemap of {selected_site_url}:")
            print(pages_to_index)
        else:
            print(f"No sitemap found for {selected_site_url}.")
            return

    # submit index
    if pages_to_index:
        should_index = confirm("Submit all these pages for re-indexing?")
        if should_index:
            for page in pages_to_index:
                response = submit_index_request(service, selected_site_url, page)
                if response:
                    index_status = response.get('inspectionResult', {}).get('indexStatusResult', {})
                    current_status = index_status.get('coverageState', 'unknown')
                    last_crawled = index_status.get('lastCrawlTime', 'never')
                    print(f"({page}) | current status: {current_status} | last crawled: {last_crawled}")
            print(f"Indexed {len(pages_to_index)} pages for {selected_site_url}.")

    print("Done.")

if __name__ == "__main__":
    main()