"""Module defines the main entry point for the Apify Actor.

Feel free to modify this file to suit your specific needs.

To build Apify Actors, utilize the Apify SDK toolkit, read more at the official documentation:
https://docs.apify.com/sdk/python
"""

from __future__ import annotations

import json
import re
from typing import Any
import logging
import os
import requests
from apify import Actor
from crawlee import Request
from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext
from playwright.async_api import Page, Browser, BrowserContext
from bs4 import BeautifulSoup


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
        'comments_count': None,
    }
    
    try:
        # Extract title - try multiple selectors
        title_selectors = [
            '#title h1.style-scope.ytd-watch-metadata yt-formatted-string',
            'h1.ytd-watch-metadata yt-formatted-string',
            'h1.ytd-watch-metadata',
            'h1[class*="watch"]',
            'meta[property="og:title"]',
            'title',
        ]
        
        for selector in title_selectors:
            element = page.locator(selector).first
            if await element.count() > 0:
                title = await element.text_content()
                if title:
                    video_info['title'] = title.strip()
                    break
                
      
        
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
        
        # Extract likes - use the specific selector from YouTube
        likes_selectors = [
            'segmented-like-dislike-button-view-model button .yt-spec-button-shape-next__button-text-content',
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
                    # Get text content from the element
                    text = await like_button.text_content()
                    if text:
                        text = text.strip()
                        # Extract number from text (e.g., "1.2K", "123", "1.5M")
                        match = re.search(r'([\d,\.]+[KMB]?)', text, re.IGNORECASE)
                        if match:
                            video_info['likes'] = match.group(1)
                            Actor.log.info(f"Found likes: {video_info['likes']}")
                            break
                        # If no match but text exists, use it directly
                        elif text:
                            video_info['likes'] = text
                            Actor.log.info(f"Found likes (direct): {video_info['likes']}")
                            break
                    
                    # Try to get aria-label as fallback
                    aria_label = await like_button.get_attribute('aria-label')
                    if aria_label:
                        # Extract number from aria-label like "1.2K likes" or "123 likes"
                        match = re.search(r'([\d,\.]+[KMB]?)\s*likes?', aria_label, re.IGNORECASE)
                        if match:
                            video_info['likes'] = match.group(1)
                            Actor.log.info(f"Found likes from aria-label: {video_info['likes']}")
                            break
            except Exception as e:
                Actor.log.debug(f"Error with selector {selector}: {e}")
                continue

        # Extract comments count - try multiple selectors
        comments_selectors = [
            'ytd-comments-header-renderer #count',
            'ytd-comments-header-renderer .count-text',
            'ytd-comments-header-renderer #title #count',
            'yt-formatted-string.count-text',
        ]
        try:
            # Attempt to scroll to comments to ensure lazy-loaded content appears
            await page.evaluate("window.scrollBy(0, document.body.scrollHeight / 2);")
            await page.wait_for_timeout(1000)
        except Exception:
            pass

        for selector in comments_selectors:
            try:
                element = page.locator(selector).first
                if await element.count() > 0:
                    comments_text = await element.text_content()
                    if comments_text:
                        match = re.search(r'([\d,.,]+)\s+comments?', comments_text, re.IGNORECASE)
                        if match:
                            video_info['comments_count'] = match.group(1)
                            break
                        # Fallback: if text is just number
                        numeric = re.search(r'[\d,.,]+', comments_text)
                        if numeric:
                            video_info['comments_count'] = numeric.group(0)
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
                [{'url': 'https://www.youtube.com'}],
            )
        ]

        # Exit if no start URLs are provided.
        if not start_urls:
            Actor.log.info('No start URLs specified in Actor input, exiting...')
            await Actor.exit()

        # Get max videos to scrape (default 30)
        max_videos = int(actor_input.get('max_videos', 30))
        
        # Create a crawler with English language preference
        crawler = PlaywrightCrawler(
            # Allow enough requests for initial page + videos
            max_requests_per_crawl=max_videos + 1,
            headless=True,
            browser_launch_options={
                'args': ['--disable-gpu', '--no-sandbox', '--lang=en-US'],
            },
        )
        
        # Define a request handler, which will be called for every request.
        @crawler.router.default_handler
        async def request_handler(context: PlaywrightCrawlingContext) -> None:
            Actor.log.info("Scraping is started")
            
            # There is no Flask request context here; use Actor input or context.request.url
            # This is just a structural fix. Adapt as needed for actual Actor input source.
            actor_input = await Actor.get_input() or {}
            channel_name = actor_input.get("channel", "").replace(" ", "").replace("@", "")
            if not channel_name:
                Actor.log.warning("No channel name provided, using default")
                channel_name = "unknown"
            # Force English page with language parameters
            url = f"https://www.youtube.com/@{channel_name}/videos"
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/58.0.3029.110 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
            }
            
            Actor.log.info(f"Navigating to {url} using Playwright...")
            
            # Navigate to the URL using Playwright page (can execute JavaScript)
            await context.page.goto(url, wait_until='networkidle', timeout=60000)
            
            # Wait for page to fully load and JavaScript to render content
            Actor.log.info("Waiting for page content to load...")
            await context.page.wait_for_timeout(5000)  # Wait for JavaScript to render
            
            # Try to wait for ytd-two-column-browse-results-renderer to appear
            try:
                await context.page.wait_for_selector('ytd-two-column-browse-results-renderer', timeout=10000)
                Actor.log.info("ytd-two-column-browse-results-renderer selector found")
            except Exception as e:
                Actor.log.warning(f"ytd-two-column-browse-results-renderer not found: {e}")
            
            # Use Playwright to find elements directly
            Actor.log.info("Finding video elements using Playwright...")
            
            # Find ytd-two-column-browse-results-renderer > div#primary > ytd-rich-grid-renderer > div#contents > ytd-rich-item-renderer
            try:
                # Get all ytd-rich-item-renderer elements using the full path
                vid_elements_locator = context.page.locator(
                    'ytd-two-column-browse-results-renderer div#primary ytd-rich-grid-renderer div#contents ytd-rich-item-renderer'
                )
                vid_elements_count = await vid_elements_locator.count()
                Actor.log.info(f"Found {vid_elements_count} ytd-rich-item-renderer elements")
            except Exception as e:
                Actor.log.error(f"Error finding video elements: {e}")
                vid_elements_count = 0
                vid_elements_locator = None
         

            video_info_list = []
            for i in range(min(vid_elements_count, max_videos)):
                try:
                    video_info = {}
                    element = vid_elements_locator.nth(i)
                    video_info['video_url'] = context.page.url
                    
                    video_info['title'] = await element.locator('a#video-title-link').first.get_attribute('aria-label') or await element.locator('a#video-title-link').first.text_content()
                    
                    video_info['thumbnail'] = await element.locator('img').first.get_attribute('src')
                     
                    video_info['link'] = await element.locator('a#video-title-link').first.get_attribute('href')
                    
                    video_info['viscount'] = await element.locator('span:has-text("views")').first.text_content()
                    
                    video_info['age'] = await element.locator('span:has-text("ago")').first.text_content()
                    video_info_list.append(video_info)
                
                except Exception as e:
                    Actor.log.warning(f"Error extracting data from element {i}: {e}")

            # Visit each video page to gather detailed info (comments count, likes, etc.)
            detailed_video_info_list = []
            for idx, video in enumerate(video_info_list):
                link = video.get('link')
                if not link:
                    detailed_video_info_list.append(video)
                    continue
                try:
                    # Ensure full URL
                    if link.startswith('/'):
                        link = f"https://www.youtube.com{link}"
                        video['link'] = link
                    Actor.log.info(f"Visiting video {idx+1}/{len(video_info_list)}: {link}")
                    await context.page.goto(link, wait_until='networkidle', timeout=60000)
                    await context.page.wait_for_timeout(2000)
                    
                    detailed = await get_youtube_video_info(context.page)
                    
                    # Merge detailed fields
                    video['video_url'] = detailed.get('video_url', link)
                    video['duration'] = detailed.get('duration')
                    video['likes'] = detailed.get('likes')
                    video['creators'] = detailed.get('creators')
                    video['summary'] = detailed.get('summary')
                    video['comments_count'] = detailed.get('comments_count')
                    
                    # Prefer detailed title if available
                    if detailed.get('title'):
                        video['title'] = detailed['title']
                    
                    detailed_video_info_list.append(video)
                except Exception as e:
                    Actor.log.warning(f"Error visiting video {link}: {e}")
                    detailed_video_info_list.append(video)
                
            # Save video_info_list to JSON file in key-value store
            Actor.log.info(f"Saving {len(detailed_video_info_list)} video information to JSON file...")
            json_data = json.dumps(detailed_video_info_list, ensure_ascii=False, indent=2)
            await Actor.set_value('video_information.json', json_data, content_type='application/json')
            Actor.log.info("Video information saved to key-value store as 'video_information.json'")    
                        
            # Push data to dataset
            await context.push_data(detailed_video_info_list)

        # Reset scraped count at start
        await Actor.set_value('scraped_videos_count', 0)
        
        # Run the crawler with the starting requests.
        await crawler.run(start_urls)
