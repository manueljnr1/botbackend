import asyncio
import aiohttp
import logging
import re
import time
import ssl
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
        
        # Create SSL context that's more permissive
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        # Setup HTTP session with better error handling
        connector = aiohttp.TCPConnector(
            limit=10, 
            limit_per_host=3,
            ssl=ssl_context,
            ttl_dns_cache=300,
            use_dns_cache=True,
            enable_cleanup_closed=True
        )
        timeout = aiohttp.ClientTimeout(total=self.timeout, connect=10)
        
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; KnowledgeBot/1.0; +crawler)',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
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
                if result:
                    if result.content and not result.error:
                        self.crawled_content.append(result)
                        logger.info(f"Crawled: {current_url} ({len(result.content)} chars)")
                        
                        # Extract links for next level
                        if depth < self.max_depth:
                            links = self._extract_links(result.content, current_url)
                            for link in links[:10]:  # Limit links per page
                                if link not in self.visited_urls:
                                    crawl_queue.append((link, depth + 1))
                    else:
                        logger.warning(f"Failed to crawl {current_url}: {result.error}")
                
                self.visited_urls.add(current_url)
                
                # Rate limiting
                await asyncio.sleep(self.delay)
        
        logger.info(f"Crawl completed: {len(self.crawled_content)} pages crawled")
        return self.crawled_content
    
    async def _crawl_page_js(self, context, url: str) -> Optional[CrawlResult]:
        """Crawl a single page with JavaScript rendering"""
        try:
            page = await context.new_page()
            
            # Set reasonable timeout
            page.set_default_timeout(30000)  # 30 seconds
            
            # Navigate and wait for network to be idle
            await page.goto(url, wait_until='networkidle')
            
            # Wait a bit more for dynamic content
            await page.wait_for_timeout(2000)  # 2 seconds
            
            # Get the final rendered HTML
            html_content = await page.content()
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract title
            title_tag = soup.find('title')
            title = title_tag.get_text().strip() if title_tag else url
            
            # STORE THE ORIGINAL HTML FOR LINK EXTRACTION
            original_html = html_content
            
            # Remove unwanted elements for content extraction
            for element in soup(['script', 'style', 'nav', 'header', 'footer', 
                            'aside', 'iframe', 'noscript', 'svg', 'canvas']):
                element.decompose()
            
            # Extract main content
            content = self._extract_main_content(soup)
            
            await page.close()
            
            if not content or len(content.strip()) < 50:
                logger.debug(f"Insufficient JS content: {url} (length: {len(content) if content else 0})")
                return CrawlResult(url, "", title, 200, "Insufficient content after JS rendering")
            
            logger.debug(f"Successfully extracted {len(content)} chars from JS page: {url}")
            
            # CREATE A SPECIAL RESULT THAT INCLUDES THE ORIGINAL HTML
            result = CrawlResult(url, content, title, 200)
            result.original_html = original_html  # Add this for link extraction
            return result
            
        except Exception as e:
            logger.error(f"Error crawling JS page {url}: {e}")
            return CrawlResult(url, "", "", 0, f"JS Error: {str(e)}")
        
    
    def _extract_main_content(self, soup: BeautifulSoup) -> str:
        """Extract main content from HTML with improved selection"""
        content_parts = []
        
        # Try to find main content areas in order of preference
        content_selectors = [
            'main', 'article', '[role="main"]', '.main-content', '.content',
            '#main-content', '#content', '.post-content', '.entry-content',
            '.page-content', '.article-content', '.blog-content'
        ]
        
        found_content = False
        for selector in content_selectors:
            elements = soup.select(selector)
            if elements:
                for el in elements:
                    text = el.get_text(separator=' ', strip=True)
                    if len(text) > 30:  # Lowered from 100
                        content_parts.append(text)
                        found_content = True
                break
        
        # If no main content area found, try extracting from common content tags
        if not found_content:
            content_tags = ['p', 'div', 'section', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']
            for tag in content_tags:
                elements = soup.find_all(tag)
                for el in elements:
                    # Skip if element is likely navigation or metadata
                    if self._is_likely_content(el):
                        text = el.get_text(separator=' ', strip=True)
                        if len(text) > 20:  # Lowered from 50
                            content_parts.append(text)
        
        # Fallback: extract from body
        if not content_parts:
            body = soup.find('body')
            if body:
                text = body.get_text(separator=' ', strip=True)
                if len(text) > 30:  # Lowered from 100
                    content_parts.append(text)
        
        # Final fallback: all text
        if not content_parts:
            text = soup.get_text(separator=' ', strip=True)
            if len(text) > 20:  # Lowered from 50
                content_parts.append(text)
        
        # Join and clean up content
        final_content = ' '.join(content_parts)
        
        # Clean up whitespace
        final_content = re.sub(r'\s+', ' ', final_content)
        final_content = final_content.strip()
        
        return final_content
    
    def _is_likely_content(self, element) -> bool:
        """Check if an element is likely to contain main content"""
        # Skip elements that are likely navigation or metadata
        skip_classes = ['nav', 'navigation', 'menu', 'header', 'footer', 'sidebar', 
                       'advertisement', 'ads', 'social', 'share', 'comment']
        skip_ids = ['nav', 'navigation', 'menu', 'header', 'footer', 'sidebar']
        
        # Check class attributes
        classes = element.get('class', [])
        if any(skip_class in ' '.join(classes).lower() for skip_class in skip_classes):
            return False
        
        # Check id attribute
        element_id = element.get('id', '').lower()
        if any(skip_id in element_id for skip_id in skip_ids):
            return False
        
        # Skip if element has very few characters but many links
        text = element.get_text(strip=True)
        links = element.find_all('a')
        if len(links) > 3 and len(text) < len(links) * 20:
            return False
        
        return True
    
    def _extract_links(self, html_content: str, base_url: str) -> List[str]:
        """Extract all links from HTML"""
        soup = BeautifulSoup(html_content, 'html.parser')
        links = []
        
        for link in soup.find_all('a', href=True):
            try:
                href = link['href']
                absolute_url = urljoin(base_url, href)
                normalized_url = self._normalize_url(absolute_url)
                
                if normalized_url and self._is_valid_url(normalized_url):
                    links.append(normalized_url)
            except (KeyError, TypeError, AttributeError):
                # Skip malformed links
                continue
        
        return list(set(links))  # Remove duplicates
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL (remove fragments, clean up)"""
        if not url:
            return ""
        
        # Add scheme if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Parse and reconstruct to normalize
        parsed = urlparse(url)
        
        # Remove fragment
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        # Add query if present (but clean it up)
        if parsed.query:
            normalized += f"?{parsed.query}"
        
        # Remove trailing slash unless it's the root
        if normalized.endswith('/') and normalized.count('/') > 2:
            normalized = normalized[:-1]
            
        return normalized
    
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