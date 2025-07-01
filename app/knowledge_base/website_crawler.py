import asyncio
import aiohttp
import logging
import re
import time
from urllib.parse import urljoin, urlparse
from typing import List, Set, Dict, Optional
from bs4 import BeautifulSoup
from dataclasses import dataclass
from langchain.schema import Document

logger = logging.getLogger(__name__)

@dataclass
class CrawlResult:
    url: str
    content: str
    title: str
    status_code: int
    error: Optional[str] = None

class WebsiteCrawler:
    """Simple, robust website crawler with pattern filtering"""
    
    def __init__(self, 
                 max_depth: int = 3,
                 max_pages: int = 100,
                 delay: float = 1.0,
                 timeout: int = 30):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.delay = delay
        self.timeout = timeout
        self.visited_urls: Set[str] = set()
        self.crawled_content: List[CrawlResult] = []
        
    async def crawl_website(self, 
                           base_url: str,
                           include_patterns: List[str] = None,
                           exclude_patterns: List[str] = None) -> List[CrawlResult]:
        """Crawl website with pattern filtering"""
        
        logger.info(f"Starting crawl of {base_url} (depth: {self.max_depth}, max_pages: {self.max_pages})")
        
        # Normalize base URL
        base_url = self._normalize_url(base_url)
        base_domain = urlparse(base_url).netloc
        
        # Initialize crawl queue
        crawl_queue = [(base_url, 0)]  # (url, depth)
        
        # Setup HTTP session
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=3)
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={'User-Agent': 'KnowledgeBot/1.0 (+crawler)'}
        ) as session:
            
            while crawl_queue and len(self.crawled_content) < self.max_pages:
                current_url, depth = crawl_queue.pop(0)
                
                # Skip if already visited
                if current_url in self.visited_urls:
                    continue
                    
                # Skip if depth exceeded
                if depth > self.max_depth:
                    continue
                
                # Apply pattern filters
                if not self._should_crawl_url(current_url, include_patterns, exclude_patterns):
                    continue
                    
                # Ensure we stay on the same domain
                if urlparse(current_url).netloc != base_domain:
                    continue
                
                # Crawl the page
                result = await self._crawl_page(session, current_url)
                if result and result.content:
                    self.crawled_content.append(result)
                    logger.info(f"Crawled: {current_url} ({len(result.content)} chars)")
                    
                    # Extract links for next level
                    if depth < self.max_depth:
                        links = self._extract_links(result.content, current_url)
                        for link in links:
                            if link not in self.visited_urls:
                                crawl_queue.append((link, depth + 1))
                
                self.visited_urls.add(current_url)
                
                # Rate limiting
                await asyncio.sleep(self.delay)
        
        logger.info(f"Crawl completed: {len(self.crawled_content)} pages crawled")
        return self.crawled_content
    
    async def _crawl_page(self, session: aiohttp.ClientSession, url: str) -> Optional[CrawlResult]:
        """Crawl a single page"""
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.warning(f"HTTP {response.status} for {url}")
                    return CrawlResult(url, "", "", response.status, f"HTTP {response.status}")
                
                # Check content type
                content_type = response.headers.get('content-type', '')
                if not content_type.startswith('text/html'):
                    logger.debug(f"Skipping non-HTML content: {url}")
                    return None
                
                html = await response.text()
                
                # Extract content
                soup = BeautifulSoup(html, 'html.parser')
                
                # Remove unwanted elements
                for element in soup(['script', 'style', 'nav', 'header', 'footer', 
                                   'aside', 'iframe', 'noscript']):
                    element.decompose()
                
                # Extract title
                title_tag = soup.find('title')
                title = title_tag.get_text().strip() if title_tag else url
                
                # Extract main content
                content = self._extract_main_content(soup)
                
                if not content or len(content.strip()) < 100:
                    logger.debug(f"Insufficient content: {url}")
                    return None
                
                return CrawlResult(url, content, title, response.status)
                
        except asyncio.TimeoutError:
            logger.warning(f"Timeout crawling {url}")
            return CrawlResult(url, "", "", 0, "Timeout")
        except Exception as e:
            logger.error(f"Error crawling {url}: {e}")
            return CrawlResult(url, "", "", 0, str(e))
    
    def _extract_main_content(self, soup: BeautifulSoup) -> str:
        """Extract main content from HTML"""
        # Try to find main content areas
        content_selectors = [
            'main', 'article', '[role="main"]',
            '.content', '.main-content', '.post-content',
            '#content', '#main-content', '#post-content'
        ]
        
        for selector in content_selectors:
            elements = soup.select(selector)
            if elements:
                return ' '.join(el.get_text(separator=' ', strip=True) for el in elements)
        
        # Fallback: extract from body
        body = soup.find('body')
        if body:
            return body.get_text(separator=' ', strip=True)
        
        # Last resort: all text
        return soup.get_text(separator=' ', strip=True)
    
    def _extract_links(self, html_content: str, base_url: str) -> List[str]:
        """Extract all links from HTML"""
        soup = BeautifulSoup(html_content, 'html.parser')
        links = []
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            absolute_url = urljoin(base_url, href)
            normalized_url = self._normalize_url(absolute_url)
            
            if normalized_url and self._is_valid_url(normalized_url):
                links.append(normalized_url)
        
        return list(set(links))  # Remove duplicates
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL (remove fragments, clean up)"""
        if not url:
            return ""
        
        # Add scheme if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Remove fragment
        if '#' in url:
            url = url.split('#')[0]
        
        # Remove trailing slash
        if url.endswith('/') and url.count('/') > 2:
            url = url[:-1]
            
        return url
    
    def _is_valid_url(self, url: str) -> bool:
        """Check if URL is valid for crawling"""
        if not url:
            return False
            
        # Skip file extensions we don't want
        skip_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.zip', 
                          '.rar', '.tar', '.gz', '.exe', '.dmg', '.pkg',
                          '.jpg', '.jpeg', '.png', '.gif', '.svg', '.ico',
                          '.mp3', '.mp4', '.avi', '.mov', '.wav']
        
        url_lower = url.lower()
        return not any(url_lower.endswith(ext) for ext in skip_extensions)
    
    def _should_crawl_url(self, url: str, 
                         include_patterns: List[str] = None,
                         exclude_patterns: List[str] = None) -> bool:
        """Check if URL matches include/exclude patterns"""
        
        # Check exclude patterns first
        if exclude_patterns:
            for pattern in exclude_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    logger.debug(f"URL excluded by pattern '{pattern}': {url}")
                    return False
        
        # Check include patterns
        if include_patterns:
            for pattern in include_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    return True
            # If include patterns exist but none match, exclude
            logger.debug(f"URL not included by any pattern: {url}")
            return False
        
        # No patterns or no exclude match
        return True
    
    def get_documents(self) -> List[Document]:
        """Convert crawled content to Langchain documents"""
        documents = []
        
        for result in self.crawled_content:
            if result.content and not result.error:
                doc = Document(
                    page_content=result.content,
                    metadata={
                        'source': result.url,
                        'title': result.title,
                        'type': 'webpage',
                        'crawled_at': time.time()
                    }
                )
                documents.append(doc)
        
        return documents