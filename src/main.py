"""Module defines the main entry point for the Apify Actor.

Feel free to modify this file to suit your specific needs.

To build Apify Actors, utilize the Apify SDK toolkit, read more at the official documentation:
https://docs.apify.com/sdk/python
"""

from __future__ import annotations

import re
from typing import Any

from apify import Actor
from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext
from crawlee.requests import Request
from playwright.async_api import Page


async def extract_youtube_video_urls(page: Page, max_videos: int = 30) -> list[str]:
    """Extract YouTube video URLs from a YouTube page (homepage, search, channel, etc.).
    
    Args:
        page: Playwright page object for the YouTube page
        max_videos: Maximum number of video URLs to extract
        
    Returns:
        List of YouTube video URLs
    """
    video_urls: list[str] = []
    
    try:
        # Wait for the page to load
        await page.wait_for_load_state('networkidle')
        await page.wait_for_timeout(3000)  # Wait for dynamic content to load
        
        # Scroll down to load more videos (YouTube uses infinite scroll)
        for _ in range(3):  # Scroll 3 times to load more content
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(2000)
        
        # Extract video links - try multiple selectors for different YouTube layouts
        video_selectors = [
            'a[href*="/watch?v="]',
            'ytd-video-renderer a[href*="/watch?v="]',
            'ytd-rich-item-renderer a[href*="/watch?v="]',
            'ytd-grid-video-renderer a[href*="/watch?v="]',
            'a#video-title[href*="/watch?v="]',
        ]
        
        for selector in video_selectors:
            try:
                links = await page.locator(selector).all()
                for link in links:
                    if len(video_urls) >= max_videos:
                        break
                    
                    href = await link.get_attribute('href')
                    if href:
                        # Convert relative URLs to absolute
                        if href.startswith('/'):
                            video_url = f'https://www.youtube.com{href}'
                        elif href.startswith('http'):
                            video_url = href
                        else:
                            continue
                        
                        # Extract clean video URL (remove extra parameters if needed)
                        if '/watch?v=' in video_url:
                            # Keep only the video ID part
                            match = re.search(r'/watch\?v=([^&]+)', video_url)
                            if match:
                                video_url = f'https://www.youtube.com/watch?v={match.group(1)}'
                            
                            # Avoid duplicates
                            if video_url not in video_urls:
                                video_urls.append(video_url)
                
                if len(video_urls) >= max_videos:
                    break
            except Exception as e:
                Actor.log.warning(f'Error extracting videos with selector {selector}: {e}')
                continue
        
        Actor.log.info(f'Extracted {len(video_urls)} video URLs from {page.url}')
        
    except Exception as e:
        Actor.log.error(f'Error extracting YouTube video URLs: {e}')
    
    return video_urls[:max_videos]


async def get_youtube_video_info(page: Page) -> dict[str, Any]:
    """Extract YouTube video information from a page.
    
    Args:
        page: Playwright page object for the YouTube video page
        
    Returns:
        Dictionary containing video URL, title, duration, likes, creators, and summary
    """
    # Wait for the page to load and video content to be available
    await page.wait_for_load_state('networkidle')
    await page.wait_for_timeout(2000)  # Additional wait for dynamic content
    
    video_info: dict[str, Any] = {
        'video_url': page.url,
        'title': None,
        'duration': None,
        'likes': None,
        'creators': None,
        'summary': None,
    }
    
    try:
        # Extract title - try multiple selectors
        title_selectors = [
            'h1.ytd-watch-metadata yt-formatted-string',
            'h1.ytd-watch-metadata',
            'h1[class*="watch"]',
            'meta[property="og:title"]',
            'title',
        ]
        
        for selector in title_selectors:
            try:
                if selector.startswith('meta'):
                    title = await page.get_attribute(selector, 'content')
                else:
                    element = page.locator(selector).first
                    if await element.count() > 0:
                        title = await element.text_content()
                    else:
                        continue
                
                if title:
                    video_info['title'] = title.strip()
                    break
            except Exception:
                continue
        
        # Fallback to page title if no title found
        if not video_info['title']:
            video_info['title'] = (await page.title()).replace(' - YouTube', '').strip()
        
        # Extract duration - try multiple selectors
        duration_selectors = [
            '.ytp-time-duration',
            'span.ytp-time-duration',
            'meta[itemprop="duration"]',
            '[class*="duration"]',
        ]
        
        for selector in duration_selectors:
            try:
                if selector.startswith('meta'):
                    duration = await page.get_attribute(selector, 'content')
                    if duration:
                        # Parse ISO 8601 duration format (PT4M13S -> 4:13)
                        duration = duration.replace('PT', '').replace('H', ':').replace('M', ':').replace('S', '')
                else:
                    element = page.locator(selector).first
                    if await element.count() > 0:
                        duration = await element.text_content()
                    else:
                        continue
                
                if duration:
                    video_info['duration'] = duration.strip()
                    break
            except Exception:
                continue
        
        # Extract likes - try multiple selectors
        likes_selectors = [
            'button[aria-label*="like"] span',
            'yt-formatted-string[id="text"]:has-text("likes")',
            '[aria-label*="like"]',
            'button[aria-label*="Like"]',
        ]
        
        for selector in likes_selectors:
            try:
                # Try to find like button and extract the count
                like_button = page.locator(selector).first
                if await like_button.count() > 0:
                    # Try to get aria-label or text content
                    aria_label = await like_button.get_attribute('aria-label')
                    if aria_label:
                        # Extract number from aria-label like "1.2K likes" or "123 likes"
                        match = re.search(r'([\d,\.]+[KMB]?)\s*likes?', aria_label, re.IGNORECASE)
                        if match:
                            video_info['likes'] = match.group(1)
                            break
                    
                    # Try text content as fallback
                    text = await like_button.text_content()
                    if text and ('like' in text.lower() or text.strip().replace(',', '').replace('.', '').isdigit()):
                        video_info['likes'] = text.strip()
                        break
            except Exception:
                continue
        
        # Extract creator/channel name - try multiple selectors
        creator_selectors = [
            'ytd-channel-name a',
            'ytd-channel-name #text',
            'ytd-channel-name yt-formatted-string a',
            'a[class*="channel"]',
            'meta[itemprop="author"]',
        ]
        
        for selector in creator_selectors:
            try:
                if selector.startswith('meta'):
                    creator = await page.get_attribute(selector, 'content')
                else:
                    element = page.locator(selector).first
                    if await element.count() > 0:
                        creator = await element.text_content()
                    else:
                        continue
                
                if creator:
                    video_info['creators'] = creator.strip()
                    break
            except Exception:
                continue
        
        # Extract summary/description - try multiple selectors
        summary_selectors = [
            'ytd-expander #content',
            'ytd-expander #description',
            '#description',
            'meta[property="og:description"]',
            'meta[name="description"]',
        ]
        
        for selector in summary_selectors:
            try:
                if selector.startswith('meta'):
                    summary = await page.get_attribute(selector, 'content')
                else:
                    # Try to expand description if collapsed
                    try:
                        expand_button = page.locator('button[aria-label*="more"]').first
                        if await expand_button.count() > 0:
                            await expand_button.click()
                            await page.wait_for_timeout(500)
                    except Exception:
                        pass
                    
                    element = page.locator(selector).first
                    if await element.count() > 0:
                        summary = await element.text_content()
                    else:
                        continue
                
                if summary:
                    video_info['summary'] = summary.strip()
                    break
            except Exception:
                continue
        
        Actor.log.info(f'Successfully extracted video info for: {video_info.get("title", "Unknown")}')
        
    except Exception as e:
        Actor.log.error(f'Error extracting YouTube video info: {e}')
    
    return video_info


async def main() -> None:
    """Define a main entry point for the Apify Actor.

    This coroutine is executed using `asyncio.run()`, so it must remain an asynchronous function for proper execution.
    Asynchronous execution is required for communication with Apify platform, and it also enhances performance in
    the field of web scraping significantly.
    """
    # Enter the context of the Actor.
    async with Actor:
        # Retrieve the Actor input, and use default values if not provided.
        actor_input = await Actor.get_input() or {}
        start_urls = [
            url.get('url')
            for url in actor_input.get(
                'start_urls',
                [{'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'}],
            )
        ]

        # Exit if no start URLs are provided.
        if not start_urls:
            Actor.log.info('No start URLs specified in Actor input, exiting...')
            await Actor.exit()

        # Get max videos to scrape (default 30)
        max_videos = actor_input.get('max_videos', 30)
        
        # Create a crawler.
        crawler = PlaywrightCrawler(
            # Allow enough requests for initial page + 30 videos
            max_requests_per_crawl=max_videos + 1,
            headless=True,
            browser_launch_options={
                'args': ['--disable-gpu', '--no-sandbox'],
            },
        )
        
        # Define a request handler, which will be called for every request.
        @crawler.router.default_handler
        async def request_handler(context: PlaywrightCrawlingContext) -> None:
            url = context.request.url
            Actor.log.info(f'Scraping {url}...')
            
            # Get current scraped count
            scraped_videos_count = await Actor.get_value('scraped_videos_count') or 0

            # Check if this is a YouTube video URL
            if 'youtube.com/watch' in url or 'youtu.be/' in url:
                # Check if we've already scraped enough videos
                if scraped_videos_count >= max_videos:
                    Actor.log.info(f'Reached max videos limit ({max_videos}), skipping {url}')
                    return
                
                # Extract YouTube video information
                data = await get_youtube_video_info(context.page)
                
                # Store the extracted data to the default dataset.
                await context.push_data(data)
                
                # Update scraped count
                scraped_videos_count += 1
                await Actor.set_value('scraped_videos_count', scraped_videos_count)
                Actor.log.info(f'Scraped {scraped_videos_count}/{max_videos} videos')
                
            elif 'youtube.com' in url:
                # This is a YouTube page (homepage, search, channel, etc.)
                # Extract video URLs from this page
                video_urls = await extract_youtube_video_urls(context.page, max_videos)
                
                # Enqueue only video URLs, not all links
                requests_to_enqueue = []
                for video_url in video_urls:
                    if scraped_videos_count >= max_videos:
                        break
                    requests_to_enqueue.append(Request(video_url))
                
                if requests_to_enqueue:
                    await context.add_requests(requests_to_enqueue)
            else:
                # For non-YouTube pages, just extract basic data
                data = {
                    'url': context.request.url,
                    'title': await context.page.title(),
                    'h1s': [await h1.text_content() for h1 in await context.page.locator('h1').all()],
                    'h2s': [await h2.text_content() for h2 in await context.page.locator('h2').all()],
                    'h3s': [await h3.text_content() for h3 in await context.page.locator('h3').all()],
                }
                await context.push_data(data)

        # Reset scraped count at start
        await Actor.set_value('scraped_videos_count', 0)
        
        # Run the crawler with the starting requests.
        await crawler.run(start_urls)
