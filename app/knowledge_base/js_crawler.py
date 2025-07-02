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

class JSWebsiteCrawler:
    """Enhanced website crawler with JavaScript rendering support"""
    
    def __init__(self, 
                 max_depth: int = 3,
                 max_pages: int = 20,
                 delay: float = 0.5,
                 timeout: int = 10,
                 enable_js: bool = False):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.delay = delay
        self.timeout = timeout
        self.enable_js = enable_js
        self.visited_urls: Set[str] = set()
        self.crawled_content: List[CrawlResult] = []
        
    async def crawl_website(self, 
                           base_url: str,
                           include_patterns: List[str] = None,
                           exclude_patterns: List[str] = None) -> List[CrawlResult]:
        """Crawl website with JavaScript support"""
        
        logger.info(f"Starting JS-enabled crawl of {base_url} (depth: {self.max_depth}, max_pages: {self.max_pages})")
        
        # Check if we can use playwright for JS rendering
        playwright_available = False  # Disable JS by default for speed
        
        if self.enable_js and playwright_available:
            logger.info("🎭 Using Playwright for JavaScript rendering")
            return await self._crawl_with_playwright(base_url, include_patterns, exclude_patterns)
        else:
            logger.info("🌐 Using regular HTTP crawler (JS disabled)")
            return await self._crawl_with_aiohttp(base_url, include_patterns, exclude_patterns)
    
    async def _check_playwright(self) -> bool:
        """Check if playwright is available"""
        try:
            from playwright.async_api import async_playwright
            return True
        except ImportError:
            logger.warning("Playwright not available. Install with: pip install playwright")
            return False
    
    async def _crawl_with_playwright(self, base_url: str, include_patterns: List[str], exclude_patterns: List[str]) -> List[CrawlResult]:
        """Crawl using Playwright for JavaScript rendering"""
        try:
            from playwright.async_api import async_playwright
            
            async with async_playwright() as p:
                # Use chromium in headless mode
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-dev-shm-usage']
                )
                
                context = await browser.new_context(
                    user_agent='Mozilla/5.0 (compatible; KnowledgeBot/1.0; +crawler)',
                    viewport={'width': 1280, 'height': 720}
                )
                
                # Initialize crawl queue
                crawl_queue = [(base_url, 0)]
                base_domain = urlparse(base_url).netloc
                
                while crawl_queue and len(self.crawled_content) < self.max_pages:
                    current_url, depth = crawl_queue.pop(0)
                    
                    # Skip if already visited or depth exceeded
                    if current_url in self.visited_urls or depth > self.max_depth:
                        continue
                    
                    # Apply pattern filters
                    if not self._should_crawl_url(current_url, include_patterns, exclude_patterns):
                        continue
                    
                    # Ensure same domain
                    if urlparse(current_url).netloc != base_domain:
                        continue
                    
                    # Crawl the page with JavaScript
                    result, original_html = await self._crawl_page_js(context, current_url)
                    
                    if result:
                        if result.content and not result.error:
                            self.crawled_content.append(result)
                            logger.info(f"JS Crawled: {current_url} ({len(result.content)} chars)")
                            
                            # Extract links for next level using original HTML
                            if depth < self.max_depth and original_html:
                                links = self._extract_links_from_html(original_html, current_url)
                                
                                logger.info(f"Found {len(links)} links on {current_url}")
                                for link in links[:10]:  # Limit links per page
                                    if link not in self.visited_urls:
                                        crawl_queue.append((link, depth + 1))
                                        logger.debug(f"Added to queue: {link}")
                        else:
                            logger.warning(f"Failed to crawl {current_url}: {result.error}")
                    
                    self.visited_urls.add(current_url)
                    await asyncio.sleep(self.delay)
                
                await browser.close()
                
        except Exception as e:
            logger.error(f"Playwright crawling failed: {e}")
            # Fallback to regular HTTP
            return await self._crawl_with_aiohttp(base_url, include_patterns, exclude_patterns)
        
        logger.info(f"JS Crawl completed: {len(self.crawled_content)} pages crawled")
        return self.crawled_content
    
    async def _crawl_page_js(self, context, url: str) -> tuple[Optional[CrawlResult], Optional[str]]:
        """Crawl a single page with JavaScript rendering - returns (result, original_html)"""
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
            
            # Store original HTML for link extraction
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
                return CrawlResult(url, "", title, 200, "Insufficient content after JS rendering"), original_html
            
            logger.debug(f"Successfully extracted {len(content)} chars from JS page: {url}")
            return CrawlResult(url, content, title, 200), original_html
            
        except Exception as e:
            logger.error(f"Error crawling JS page {url}: {e}")
            return CrawlResult(url, "", "", 0, f"JS Error: {str(e)}"), None
    
    async def _crawl_with_aiohttp(self, base_url: str, include_patterns: List[str], exclude_patterns: List[str]) -> List[CrawlResult]:
        """Fallback to regular HTTP crawling"""
        
        # Normalize base URL
        base_url = self._normalize_url(base_url)
        base_domain = urlparse(base_url).netloc
        
        # Initialize crawl queue
        crawl_queue = [(base_url, 0)]
        
        # Create SSL context
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        # Setup HTTP session with aggressive timeouts
        connector = aiohttp.TCPConnector(
            limit=5, 
            limit_per_host=2,
            ssl=ssl_context,
            enable_cleanup_closed=True
        )
        timeout = aiohttp.ClientTimeout(total=self.timeout, connect=3)
        
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
                
                # Skip conditions
                if (current_url in self.visited_urls or 
                    depth > self.max_depth or
                    not self._should_crawl_url(current_url, include_patterns, exclude_patterns) or
                    urlparse(current_url).netloc != base_domain):
                    continue
                
                # Crawl the page
                result = await self._crawl_page_http(session, current_url)
                if result:
                    if result.content and not result.error:
                        self.crawled_content.append(result)
                        logger.info(f"HTTP Crawled: {current_url} ({len(result.content)} chars)")
                        
                        # Extract links for next level
                        if depth < self.max_depth:
                            try:
                                links = self._extract_links(result.content, current_url)
                                logger.info(f"Found {len(links)} links on {current_url}")
                                for link in links[:5]:  # Limit to 5 links per page
                                    if link not in self.visited_urls:
                                        crawl_queue.append((link, depth + 1))
                            except Exception as e:
                                logger.warning(f"Link extraction failed for {current_url}: {e}")
                    else:
                        logger.warning(f"Failed to crawl {current_url}: {result.error}")
                
                self.visited_urls.add(current_url)
                await asyncio.sleep(self.delay)
        
        logger.info(f"HTTP Crawl completed: {len(self.crawled_content)} pages crawled")
        return self.crawled_content
    
    async def _crawl_page_http(self, session: aiohttp.ClientSession, url: str) -> Optional[CrawlResult]:
        """Crawl a single page with HTTP only"""
        try:
            logger.info(f"🌐 Attempting to crawl: {url}")
            async with session.get(url, allow_redirects=True, max_redirects=5) as response:
                logger.info(f"📡 Response status: {response.status} for {url}")
                
                if response.status not in [200, 201]:
                    logger.warning(f"❌ Bad status {response.status} for {url}")
                    return CrawlResult(url, "", "", response.status, f"HTTP {response.status}")
                
                # Check content type
                content_type = response.headers.get('content-type', '').lower()
                logger.info(f"📄 Content-Type: {content_type} for {url}")
                
                if not any(ct in content_type for ct in ['text/html', 'application/xhtml', 'text/plain']):
                    return CrawlResult(url, "", "", response.status, f"Non-HTML content: {content_type}")
                
                # Read content with better error handling
                try:
                    html = await response.text()
                    logger.info(f"📖 Raw HTML length: {len(html)} chars for {url}")
                except Exception as e:
                    try:
                        html_bytes = await response.read()
                        html = html_bytes.decode('utf-8', errors='ignore')
                        logger.info(f"📖 Decoded HTML length: {len(html)} chars for {url}")
                    except Exception as e2:
                        logger.error(f"❌ Failed to read content: {e2}")
                        return CrawlResult(url, "", "", response.status, "Could not read content")
                
                if not html or len(html.strip()) < 20:
                    logger.warning(f"❌ Empty/minimal HTML for {url}")
                    return CrawlResult(url, "", "", response.status, "Empty or minimal content")
                
                # Extract content
                soup = BeautifulSoup(html, 'html.parser')
                
                # Log page title for debugging
                title_tag = soup.find('title')
                page_title = title_tag.get_text().strip() if title_tag else "No title"
                logger.info(f"📝 Page title: '{page_title}' for {url}")
                
                # Remove unwanted elements
                for element in soup(['script', 'style', 'nav', 'header', 'footer', 
                                   'aside', 'iframe', 'noscript', 'svg', 'canvas']):
                    element.decompose()
                
                # Extract title
                title = page_title if page_title != "No title" else urlparse(url).path
                
                # Extract main content
                content = self._extract_main_content(soup)
                logger.info(f"📄 Extracted content length: {len(content) if content else 0} chars for {url}")
                
                if not content or len(content.strip()) < 10:
                    logger.warning(f"❌ Insufficient content extracted for {url}")
                    # For SPA sites, try to extract at least the title and meta info
                    meta_content = self._extract_meta_content(soup)
                    if meta_content:
                        logger.info(f"📋 Using meta content as fallback: {len(meta_content)} chars")
                        return CrawlResult(url, meta_content, title, response.status)
                    
                    # Log first 200 chars of HTML for debugging
                    logger.info(f"🔍 HTML preview: {html[:200]}...")
                    return CrawlResult(url, "", title, response.status, "Insufficient content")
                
                logger.info(f"✅ Successfully extracted content for {url}")
                return CrawlResult(url, content, title, response.status)
                
        except Exception as e:
            logger.error(f"❌ Exception crawling {url}: {str(e)}")
            return CrawlResult(url, "", "", 0, f"Error: {str(e)}")
    
    def _extract_main_content(self, soup: BeautifulSoup) -> str:
        """Extract main content from HTML with improved selection"""
        content_parts = []
        
        # Try main content areas first with very low thresholds
        content_selectors = [
            'main', 'article', '[role="main"]', '.main-content', '.content',
            '#main-content', '#content', '.post-content', '.entry-content',
            '.page-content', '.article-content', '.blog-content', '.hero',
            '.banner', '.intro', '.description'
        ]
        
        found_content = False
        for selector in content_selectors:
            elements = soup.select(selector)
            if elements:
                for el in elements:
                    text = el.get_text(separator=' ', strip=True)
                    if len(text) > 10:  # Very low threshold
                        content_parts.append(text)
                        found_content = True
                break
        
        # If no main content, extract from common content tags
        if not found_content:
            content_tags = ['p', 'div', 'section', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'span', 'li', 'td']
            for tag in content_tags:
                elements = soup.find_all(tag)
                for el in elements:
                    if self._is_likely_content(el):
                        text = el.get_text(separator=' ', strip=True)
                        if len(text) > 10:  # Very low threshold
                            content_parts.append(text)
        
        # Fallback: body
        if not content_parts:
            body = soup.find('body')
            if body:
                text = body.get_text(separator=' ', strip=True)
                if len(text) > 10:  # Very low threshold
                    content_parts.append(text)
        
        # Final fallback: get all text
        if not content_parts:
            text = soup.get_text(separator=' ', strip=True)
            if len(text) > 10:
                content_parts.append(text)
        
        # Join and clean
        final_content = ' '.join(content_parts)
        final_content = re.sub(r'\s+', ' ', final_content).strip()
        
        return final_content
    
    def _extract_meta_content(self, soup: BeautifulSoup) -> str:
        """Extract meta descriptions and other useful info for SPA sites"""
        meta_parts = []
        
        # Get meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            meta_parts.append(f"Description: {meta_desc['content']}")
        
        # Get meta keywords
        meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
        if meta_keywords and meta_keywords.get('content'):
            meta_parts.append(f"Keywords: {meta_keywords['content']}")
        
        # Get og:description
        og_desc = soup.find('meta', attrs={'property': 'og:description'})
        if og_desc and og_desc.get('content'):
            meta_parts.append(f"About: {og_desc['content']}")
        
        # Get any visible text from noscript tags
        noscript_tags = soup.find_all('noscript')
        for tag in noscript_tags:
            text = tag.get_text(strip=True)
            if text and len(text) > 10:
                meta_parts.append(f"Fallback content: {text}")
        
        return ' | '.join(meta_parts) if meta_parts else ""
    
    def _is_likely_content(self, element) -> bool:
        """Check if element contains main content - more permissive"""
        skip_classes = ['nav', 'navigation', 'menu', 'header', 'footer', 'sidebar', 
                       'advertisement', 'ads', 'social', 'share', 'comment', 'cookie']
        skip_ids = ['nav', 'navigation', 'menu', 'header', 'footer', 'sidebar', 'cookie']
        
        # Check class and id attributes
        classes = element.get('class', [])
        element_id = element.get('id', '').lower()
        
        # Skip obvious non-content
        if (any(skip_class in ' '.join(classes).lower() for skip_class in skip_classes) or
            any(skip_id in element_id for skip_id in skip_ids)):
            return False
        
        # Accept more content - be less strict
        text = element.get_text(strip=True)
        if len(text) < 5:  # Very short text
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
                continue
        
        return list(set(links))
    
    def _extract_links_from_html(self, html: str, base_url: str) -> List[str]:
        """Extract links from original HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        
        for link in soup.find_all('a', href=True):
            try:
                href = link['href']
                absolute_url = urljoin(base_url, href)
                normalized_url = self._normalize_url(absolute_url)
                
                if normalized_url and self._is_valid_url(normalized_url):
                    links.append(normalized_url)
            except:
                continue
        
        return list(set(links))
        
    def _normalize_url(self, url: str) -> str:
        """Normalize URL"""
        if not url:
            return ""
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        parsed = urlparse(url)
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        
        if parsed.query:
            normalized += f"?{parsed.query}"
        
        if normalized.endswith('/') and normalized.count('/') > 2:
            normalized = normalized[:-1]
            
        return normalized
    
    def _is_valid_url(self, url: str) -> bool:
        """Check if URL is valid for crawling"""
        if not url:
            return False
            
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
                    return False
        
        # Check include patterns
        if include_patterns:
            for pattern in include_patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    return True
            return False  # No include pattern matched
        
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
                        'crawled_at': time.time(),
                        'js_rendered': self.enable_js
                    }
                )
                documents.append(doc)
        
        return documents