import os
import requests
import time
import random
from datetime import datetime
from urllib.parse import urlencode, urlparse
from bs4 import BeautifulSoup
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from .models import SearchQuery
from .forms import SearchForm
import boto3
from botocore.exceptions import NoCredentialsError, ClientError

class GoogleSearchScraper:
    """Enhanced Google Search scraper using BeautifulSoup"""
    
    def __init__(self):
        # Rotate user agents to avoid detection
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0'
        ]
    
    def get_headers(self):
        """Get randomized headers"""
        return {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    def search_google(self, query, num_results=10, language='en'):
        """
        Scrape Google search results
        """
        try:
            # Build Google search URL
            params = {
                'q': query,
                'num': min(num_results, 100),  # Google allows max 100 results per page
                'hl': language,
                'gl': 'us',
                'start': 0
            }
            
            url = f"https://www.google.com/search?{urlencode(params)}"
            
            # Make request with headers
            session = requests.Session()
            response = session.get(url, headers=self.get_headers(), timeout=15)
            response.raise_for_status()
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(response.content, 'lxml')
            
            results = []
            
            # Extract search results
            # Google uses different div classes, so we'll try multiple selectors
            search_containers = soup.find_all('div', class_='g') or soup.find_all('div', class_='tF2Cxc')
            
            for container in search_containers[:num_results]:
                result = self._extract_result_data(container)
                if result:
                    results.append(result)
            
            # If no results found with primary method, try alternative extraction
            if not results:
                results = self._alternative_extraction(soup, num_results)
            
            return results
            
        except requests.RequestException as e:
            print(f"Request error: {e}")
            return []
        except Exception as e:
            print(f"Search error: {e}")
            return []
    
    def _extract_result_data(self, container):
        """Extract data from a search result container"""
        try:
            result = {}
            
            # Extract title and URL
            title_element = container.find('h3') or container.find('a')
            if title_element:
                # Get the link
                link_element = title_element.find_parent('a') or title_element
                if link_element and link_element.get('href'):
                    result['url'] = self._clean_google_url(link_element['href'])
                
                result['title'] = title_element.get_text(strip=True)
            
            # Extract snippet/description
            snippet_selectors = [
                '.VwiC3b',  # Common snippet class
                '.s3v9rd',  # Alternative snippet class
                '.st',      # Older snippet class
                '[data-sncf="1"]',  # Another snippet selector
            ]
            
            snippet = ""
            for selector in snippet_selectors:
                snippet_element = container.select_one(selector)
                if snippet_element:
                    snippet = snippet_element.get_text(strip=True)
                    break
            
            # If no snippet found, try finding any text content
            if not snippet:
                text_divs = container.find_all('div', recursive=True)
                for div in text_divs:
                    text = div.get_text(strip=True)
                    if len(text) > 50 and not text.startswith('http'):
                        snippet = text[:300] + '...' if len(text) > 300 else text
                        break
            
            result['snippet'] = snippet
            
            # Extract displayed URL (breadcrumb)
            cite_element = container.find('cite') or container.select_one('.UdQCqe')
            if cite_element:
                result['display_url'] = cite_element.get_text(strip=True)
            else:
                result['display_url'] = result.get('url', '')
            
            # Only return if we have at least title and URL
            if result.get('title') and result.get('url'):
                return result
            
        except Exception as e:
            print(f"Error extracting result: {e}")
        
        return None
    
    def _alternative_extraction(self, soup, num_results):
        """Alternative method to extract search results"""
        results = []
        
        try:
            # Try to find all links with /url?q= pattern (Google's redirect links)
            links = soup.find_all('a', href=True)
            
            for link in links:
                href = link.get('href', '')
                if '/url?q=' in href or href.startswith('http'):
                    title_element = link.find('h3')
                    if title_element:
                        title = title_element.get_text(strip=True)
                        url = self._clean_google_url(href)
                        
                        # Find snippet nearby
                        snippet = ""
                        parent = link.find_parent('div', class_='g') or link.find_parent()
                        if parent:
                            text_content = parent.get_text(strip=True)
                            if len(text_content) > len(title):
                                snippet = text_content[len(title):].strip()[:300]
                        
                        if title and url:
                            results.append({
                                'title': title,
                                'url': url,
                                'snippet': snippet,
                                'display_url': url
                            })
                            
                            if len(results) >= num_results:
                                break
        
        except Exception as e:
            print(f"Alternative extraction error: {e}")
        
        return results
    
    def _clean_google_url(self, url):
        """Clean Google redirect URLs"""
        if '/url?q=' in url:
            # Extract the actual URL from Google's redirect
            try:
                from urllib.parse import parse_qs, urlparse
                parsed = urlparse(url)
                if parsed.path == '/url':
                    query_params = parse_qs(parsed.query)
                    actual_url = query_params.get('q', [''])[0]
                    return actual_url
            except:
                pass
        
        # Remove any remaining Google parameters
        if url.startswith('/'):
            url = 'https://www.google.com' + url
        
        return url

def search_bing(query, num_results=10):
    """Alternative search using Bing (as backup)"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        url = f"https://www.bing.com/search?q={query}&count={num_results}"
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'lxml')
        
        results = []
        search_results = soup.find_all('li', class_='b_algo')
        
        for result in search_results[:num_results]:
            title_element = result.find('h2')
            if title_element and title_element.find('a'):
                title = title_element.get_text(strip=True)
                url = title_element.find('a')['href']
                
                snippet_element = result.find('p') or result.find('div', class_='b_caption')
                snippet = snippet_element.get_text(strip=True) if snippet_element else ""
                
                results.append({
                    'title': title,
                    'url': url,
                    'snippet': snippet,
                    'display_url': url
                })
        
        return results
        
    except Exception as e:
        print(f"Bing search error: {e}")
        return []

def search_web(query, num_results=10, use_bing_fallback=True):
    """
    Enhanced web search with multiple fallback options
    """
    scraper = GoogleSearchScraper()
    
    # Add delay to be respectful to search engines
    time.sleep(random.uniform(1, 3))
    
    # Try Google first
    results = scraper.search_google(query, num_results)
    
    # If Google fails and fallback is enabled, try Bing
    if not results and use_bing_fallback:
        print("Google search failed, trying Bing...")
        time.sleep(random.uniform(1, 2))
        results = search_bing(query, num_results)
    
    # Filter out low-quality results
    filtered_results = []
    for result in results:
        if (result.get('title') and 
            len(result['title']) > 5 and 
            result.get('url') and 
            result['url'].startswith('http')):
            filtered_results.append(result)
    
    return filtered_results

def save_results_to_s3(query, results):
    """Save search results to AWS S3 with enhanced formatting"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"search_results/search_{timestamp}_{query.replace(' ', '_')[:50]}.txt"
        
        # Create file content
        content = []
        content.append(f"Search Query: {query}")
        content.append(f"Search Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        content.append(f"Number of Results: {len(results)}")
        content.append(f"Search Engine: Google (with Bing fallback)")
        content.append("=" * 70)
        content.append("")
        
        for i, result in enumerate(results, 1):
            content.append(f"Result {i}:")
            content.append(f"Title: {result.get('title', 'N/A')}")
            content.append(f"URL: {result.get('url', 'N/A')}")
            content.append(f"Display URL: {result.get('display_url', 'N/A')}")
            snippet = result.get('snippet', 'N/A')
            if len(snippet) > 500:
                snippet = snippet[:500] + '...'
            content.append(f"Snippet: {snippet}")
            content.append("-" * 50)
            content.append("")
        
        file_content = "\n".join(content)
        
        # Save to S3 using Django's default storage
        file_path = default_storage.save(filename, ContentFile(file_content.encode('utf-8')))
        
        # Return just the filename for display purposes
        return os.path.basename(file_path)
        
    except Exception as e:
        print(f"S3 save error: {e}")
        return None

def get_s3_file_url(filename):
    """Generate a presigned URL for downloading the file from S3"""
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name='us-east-1'  # Update to your bucket region
        )
        
        # Generate presigned URL (valid for 1 hour)
        file_key = f"search_results/{filename}"
        url = s3_client.generate_presigned_url(
            'get_object',
            # Params={'Bucket': settings.AWS_STORAGE_BUCKET_NAME, 'Key': file_key},
            ExpiresIn=3600  # 1 hour
        )
        return url
    except Exception as e:
        print(f"Error generating S3 URL: {e}")
        return None

def list_s3_search_files():
    """List all search result files in S3"""
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name='us-east-1'  # Update to your bucket region
        )
        
        response = s3_client.list_objects_v2(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Prefix='search_results/',
            MaxKeys=100
        )
        
        files = []
        if 'Contents' in response:
            for obj in response['Contents']:
                files.append({
                    'key': obj['Key'],
                    'filename': os.path.basename(obj['Key']),
                    'last_modified': obj['LastModified'],
                    'size': obj['Size']
                })
        
        return sorted(files, key=lambda x: x['last_modified'], reverse=True)
        
    except Exception as e:
        print(f"Error listing S3 files: {e}")
        return []

def delete_s3_file(filename):
    """Delete a search result file from S3"""
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name='us-east-1'  # Update to your bucket region
        )
        
        file_key = f"search_results/{filename}"
        s3_client.delete_object(
            Bucket=settings.AWS_STORAGE_BUCKET_NAME,
            Key=file_key
        )
        return True
        
    except Exception as e:
        print(f"Error deleting S3 file: {e}")
        return False

def index(request):
    """Main search page with enhanced search functionality and S3 storage"""
    if request.method == 'POST':
        form = SearchForm(request.POST)
        if form.is_valid():
            query = form.cleaned_data['query']
            
            # Show loading message
            messages.info(request, f"Searching for '{query}'... This may take a few seconds.")
            
            # Perform enhanced search
            try:
                results = search_web(query, num_results=15)
                
                if results:
                    # Save results to S3
                    filename = save_results_to_s3(query, results)
                    
                    if filename:
                        # Generate S3 download URL
                        download_url = get_s3_file_url(filename)
                        
                        # Save to database
                        search_record = SearchQuery.objects.create(
                            query=query,
                            results_file=filename,
                            results_count=len(results)
                        )
                        
                        messages.success(
                            request, 
                            f"Search completed! Found {len(results)} high-quality results. "
                            f"Results saved to S3 storage."
                        )
                        
                        return render(request, 'search_app/results.html', {
                            'query': query,
                            'results': results,
                            'filename': filename,
                            'download_url': download_url,
                            'search_record': search_record
                        })
                    else:
                        messages.error(request, "Search completed but failed to save results to S3.")
                        return render(request, 'search_app/results.html', {
                            'query': query,
                            'results': results,
                        })
                else:
                    messages.warning(
                        request, 
                        "No results found for your query. Try rephrasing your search terms or using different keywords."
                    )
            
            except Exception as e:
                messages.error(
                    request, 
                    f"Search failed due to technical issues. Please try again later. Error: {str(e)[:100]}"
                )
                print(f"Search error: {e}")
    else:
        form = SearchForm()
    
    # Get recent searches
    recent_searches = SearchQuery.objects.order_by('-created_at')[:10]
    
    return render(request, 'search_app/index.html', {
        'form': form,
        'recent_searches': recent_searches
    })

def search_history(request):
    """View search history with S3 file management"""
    searches = SearchQuery.objects.order_by('-created_at')
    
    # Add download URLs for each search
    for search in searches:
        if search.results_file:
            search.download_url = get_s3_file_url(search.results_file)
    
    # Also get list of all S3 files for management
    s3_files = list_s3_search_files()
    
    return render(request, 'search_app/history.html', {
        'searches': searches,
        's3_files': s3_files
    })

def download_search_file(request, filename):
    """Generate and redirect to S3 presigned URL for file download"""
  
    download_url = f"https://signalpro.s3.eu-north-1.amazonaws.com/search_results/{filename}"
    return redirect(download_url)
    

def delete_search_file(request, filename):
    """Delete a search result file from S3"""
    if request.method == 'POST':
        if delete_s3_file(filename):
            # Also delete from database if exists
            SearchQuery.objects.filter(results_file=filename).delete()
            messages.success(request, f"File {filename} deleted successfully.")
        else:
            messages.error(request, f"Failed to delete file {filename}.")
    
    return redirect('search_app:history')

def ajax_search(request):
    """AJAX endpoint for live search suggestions"""
    if request.method == 'GET':
        query = request.GET.get('q', '').strip()
        if len(query) >= 3:
            try:
                # Quick search with fewer results for suggestions
                results = search_web(query, num_results=5)
                return JsonResponse({
                    'success': True,
                    'results': results[:5],
                    'count': len(results)
                })
            except Exception as e:
                return JsonResponse({
                    'success': False,
                    'error': str(e)
                })
        
        return JsonResponse({
            'success': False,
            'error': 'Query too short'
        })