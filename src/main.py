"""Module defines the main entry point for the Apify Actor.

Feel free to modify this file to suit your specific needs.

To build Apify Actors, utilize the Apify SDK toolkit, read more at the official documentation:
https://docs.apify.com/sdk/python
"""

from __future__ import annotations

import json
import re
import asyncio
from datetime import timedelta
from typing import Any
import logging
import os
import requests
from apify import Actor
from crawlee import Request
from crawlee.crawlers import PlaywrightCrawler, PlaywrightCrawlingContext
from playwright.async_api import Page, Browser, BrowserContext, Error as PlaywrightError
from bs4 import BeautifulSoup


async def wait_for_video_page_ready(page: Page, timeout: int = 30000) -> bool:
    """Wait for key elements of YouTube video page to be ready."""
    try:
        # First, wait for basic page structure
        try:
            await page.wait_for_selector(
                "ytd-watch-metadata, #title, ytd-player, ytd-watch-flexy",
                timeout=min(timeout, 15000),
                state="attached",
            )
        except Exception as e:
            Actor.log.debug(f"Basic page structure not found immediately: {e}")

        # Wait for title element (one of the most important elements)
        title_selectors = [
            "#title h1.style-scope.ytd-watch-metadata yt-formatted-string",
            "#title h1 yt-formatted-string",
            "#title h1",
            "h1.ytd-watch-metadata",
            "ytd-watch-metadata h1",
        ]

        for selector in title_selectors:
            try:
                await page.wait_for_selector(
                    selector,
                    timeout=min(timeout // len(title_selectors), 10000),
                    state="visible",
                )
                Actor.log.debug(
                    f"Video page ready - title found with selector: {selector}"
                )
                return True
            except Exception:
                continue

        # Fallback: check if page has loaded at all
        try:
            await page.wait_for_load_state("load", timeout=5000)
            # Check if we're on a YouTube page (even if video elements aren't ready)
            current_url = page.url
            if "youtube.com" in current_url or "youtu.be" in current_url:
                Actor.log.debug("Video page ready - page loaded (fallback)")
                return True
        except Exception:
            pass

        # Last resort: check if page has any content
        try:
            body_content = await page.locator("body").text_content()
            if body_content and len(body_content.strip()) > 0:
                Actor.log.debug("Video page has content (last resort check)")
                return True
        except Exception:
            pass

        return False

    except Exception as e:
        Actor.log.warning(f"Error waiting for video page to be ready: {e}")
        return False


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
            url.get("url")
            for url in actor_input.get(
                "start_urls",
                [{"url": "https://www.youtube.com"}],
            )
        ]

        # Exit if no start URLs are provided.
        if not start_urls:
            Actor.log.info("No start URLs specified in Actor input, exiting...")
            await Actor.exit()

        # Get max videos to scrape (default 30)
        max_videos = int(actor_input.get("max_videos", 30))

        # Create a crawler with English language preference
        crawler = PlaywrightCrawler(
            # Allow enough requests for initial page + videos
            max_requests_per_crawl=max_videos + 1,
            headless=True,
            browser_launch_options={
                "args": [
                    "--disable-gpu",
                    "--no-sandbox",
                    "--lang=en-US",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-extensions",
                    "--no-first-run",
                    "--disable-setuid-sandbox",
                    "--disable-web-security",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
            },
            # Increase navigation timeout (Crawlee expects timedelta object)
            navigation_timeout=timedelta(seconds=120),  # 120 seconds
        )

        # Define a request handler, which will be called for every request.
        @crawler.router.default_handler
        async def request_handler(context: PlaywrightCrawlingContext) -> None:
            # Check if this is a detail page request
            user_data = context.request.user_data or {}
            label = user_data.get("label")

            if label == "DETAIL":
                # Handle detail page
                Actor.log.info(f"Processing detail page: {context.request.url}")

                # Check if page is still open
                if context.page.is_closed():
                    Actor.log.warning("Page is closed, skipping detail page")
                    return

                try:
                    # Load page with 'commit' strategy for faster loading
                    await context.page.goto(
                        context.request.url, wait_until="commit", timeout=120000
                    )
                    Actor.log.info("Detail page navigation committed")

                    # Wait a bit for initial content to render
                    await context.page.wait_for_timeout(2000)

                    # Extract detailed video information
                    detailed: dict[str, Any] = {
                        "video_url": context.request.url,
                        "title": None,
                        "duration": None,
                        "likes": None,
                        "creators": None,
                        "summary": None,
                        "comments_count": None,
                    }

                    # Wait for key elements to be ready
                    page_ready = await wait_for_video_page_ready(
                        context.page, timeout=30000
                    )
                    if not page_ready:
                        Actor.log.warning(
                            "Detail page may not be fully loaded, continuing anyway..."
                        )

                    # Additional wait for dynamic content
                    if not context.page.is_closed():
                        await context.page.wait_for_timeout(3000)

                    # Extract video information (same logic as in default handler)
                    # ... (可以复用现有的提取逻辑)

                    # For now, just push the URL to dataset
                    await context.push_data(
                        {
                            "url": context.request.url,
                            "processed": True,
                            "label": "DETAIL",
                        }
                    )
                    Actor.log.info(f"Processed detail page: {context.request.url}")

                except PlaywrightError as e:
                    if "Target page, context or browser has been closed" in str(
                        e
                    ) or "Target closed" in str(e):
                        Actor.log.warning(
                            f"Page/context closed during detail page processing: {e}"
                        )
                        return
                    Actor.log.error(f"Error processing detail page: {e}")
                except Exception as e:
                    Actor.log.error(f"Error processing detail page: {e}")

                return  # Exit early for detail pages

            # Default handler for channel/video list pages
            Actor.log.info("Scraping is started")

            # There is no Flask request context here; use Actor input or context.request.url
            # This is just a structural fix. Adapt as needed for actual Actor input source.
            actor_input = await Actor.get_input() or {}
            channel_name = (
                actor_input.get("channel", "").replace(" ", "").replace("@", "")
            )
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
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            }

            Actor.log.info(f"Navigating to {url} using Playwright...")

            # Navigate to the URL using Playwright page (can execute JavaScript)
            await context.page.goto(url, wait_until="load", timeout=60000)

            # Wait for page to fully load and JavaScript to render content
            Actor.log.info("Waiting for page content to load...")
            await context.page.wait_for_timeout(8000)  # Wait for JavaScript to render

            # Try to wait for ytd-two-column-browse-results-renderer to appear
            try:
                await context.page.wait_for_selector(
                    "ytd-two-column-browse-results-renderer", timeout=15000
                )
                Actor.log.info("ytd-two-column-browse-results-renderer selector found")
            except Exception as e:
                Actor.log.warning(
                    f"ytd-two-column-browse-results-renderer not found: {e}"
                )

            # Use Playwright to find elements directly
            Actor.log.info("Finding video elements using Playwright...")

            # Find ytd-two-column-browse-results-renderer > div#primary > ytd-rich-grid-renderer > div#contents > ytd-rich-item-renderer
            vid_elements_locator = None
            vid_elements_count = 0

            # Try multiple selectors
            video_selectors = [
                "ytd-two-column-browse-results-renderer div#primary ytd-rich-grid-renderer div#contents ytd-rich-item-renderer",
                "ytd-rich-grid-renderer div#contents ytd-rich-item-renderer",
                "ytd-rich-item-renderer",
            ]

            for selector in video_selectors:
                try:
                    vid_elements_locator = context.page.locator(selector)
                    vid_elements_count = await vid_elements_locator.count()
                    if vid_elements_count > 0:
                        Actor.log.info(
                            f"Found {vid_elements_count} ytd-rich-item-renderer elements using selector: {selector}"
                        )
                        break
                except Exception as e:
                    Actor.log.debug(f"Error with selector {selector}: {e}")
                    continue

            if vid_elements_count == 0:
                Actor.log.warning("No video elements found with any selector")
                vid_elements_locator = None

            video_info_list = []
            for i in range(min(vid_elements_count, max_videos)):
                try:
                    video_info = {}
                    element = vid_elements_locator.nth(i)
                    video_info["video_url"] = context.page.url

                    video_info["title"] = (
                        await element.locator("a#video-title-link").first.get_attribute(
                            "aria-label"
                        )
                        or await element.locator(
                            "a#video-title-link"
                        ).first.text_content()
                    )

                    video_info["thumbnail"] = await element.locator(
                        "img"
                    ).first.get_attribute("src")

                    video_info["link"] = await element.locator(
                        "a#video-title-link"
                    ).first.get_attribute("href")

                    video_info["viscount"] = await element.locator(
                        'span:has-text("views")'
                    ).first.text_content()

                    video_info["age"] = await element.locator(
                        'span:has-text("ago")'
                    ).first.text_content()
                    video_info_list.append(video_info)

                except Exception as e:
                    Actor.log.warning(f"Error extracting data from element {i}: {e}")

            # Save individual video data to separate JSON file with UTF-8 encoding
            video_filename = f"video_info_list.json"
            video_json_data = json.dumps(video_info_list, ensure_ascii=False, indent=2)
            await Actor.set_value(
                video_filename,
                video_json_data,
                content_type="application/json; charset=utf-8",
            )
            Actor.log.info(f"Saved video data to {video_filename} (UTF-8 encoding)")

            # 第二步：将详情页请求加入队列（由其他Handler处理）
            Actor.log.info(f"Enqueueing {len(video_info_list)} video detail pages...")
            for video in video_info_list:
                link = video.get("link")
                if not link:
                    continue

                # Ensure full URL
                if link.startswith("/"):
                    link = f"https://www.youtube.com{link}"

                # 将详情页请求加入队列
                request = Request(
                    url=link, user_data={"label": "DETAIL"}  # 标记为详情页
                )
                await context.crawler.request_queue.add_request(request)
                Actor.log.debug(f"Enqueued detail page: {link}")

            Actor.log.info(
                f"Successfully enqueued {len(video_info_list)} detail page requests"
            )

            # Visit each video page to gather detailed info (comments count, likes, etc.)
            # Process videos sequentially (one by one)
            # Process videos one by one (sequentially)
            Actor.log.info(f"Processing {len(video_info_list)} videos sequentially...")

            # Track all processed videos for final JSON save
            detailed_video_info_list = []

            # Counter for individual video JSON files
            video_counter = 1

            for video in video_info_list:
                link = video.get("link")
                if not link:
                    detailed_video_info_list.append(video)
                    # Save individual video data to separate JSON file with UTF-8 encoding
                    video_filename = f"video{video_counter}.json"
                    video_json_data = json.dumps(video, ensure_ascii=False, indent=2)
                    await Actor.set_value(
                        video_filename,
                        video_json_data,
                        content_type="application/json; charset=utf-8",
                    )
                    Actor.log.info(
                        f"Saved video data to {video_filename} (UTF-8 encoding)"
                    )
                    video_counter += 1
                    continue

                try:
                    # Ensure full URL
                    if link.startswith("/"):
                        link = f"https://www.youtube.com{link}"
                        video["link"] = link

                    # Navigate to video page with optimized loading
                    Actor.log.info(f"Visiting video: {link}")

                    # Check if page is still open before navigation
                    if context.page.is_closed():
                        Actor.log.warning("Page is closed, skipping video")
                        continue

                    try:
                        # Load page with 'commit' strategy for faster loading
                        # 'commit' waits for navigation to commit, which is faster than 'load'
                        await context.page.goto(
                            link, wait_until="commit", timeout=120000
                        )
                        Actor.log.info("Page navigation committed")

                        # Wait a bit for initial content to render
                        await context.page.wait_for_timeout(2000)
                    except PlaywrightError as e:
                        if "Target page, context or browser has been closed" in str(
                            e
                        ) or "Target closed" in str(e):
                            Actor.log.warning(
                                f"Page/context closed during navigation: {e}"
                            )
                            continue
                        raise

                    # Check if page is still open before operations
                    if context.page.is_closed():
                        Actor.log.warning("Page is closed, skipping video extraction")
                        continue

                    # Check for YouTube restrictions (age verification, region block, etc.)
                    try:
                        # Check for age verification page
                        age_verification = await context.page.locator(
                            "ytd-age-gate-renderer, #age-gate-container"
                        ).count()
                        if age_verification > 0:
                            Actor.log.warning(
                                "Age verification required - video may be restricted"
                            )

                        # Check for unavailable video
                        unavailable = await context.page.locator(
                            "ytd-watch-flexy[unavailable], #unavailable-message"
                        ).count()
                        if unavailable > 0:
                            Actor.log.warning("Video is unavailable")
                    except PlaywrightError as e:
                        if "Target page, context or browser has been closed" in str(
                            e
                        ) or "Target closed" in str(e):
                            Actor.log.warning(
                                f"Page/context closed during restriction check: {e}"
                            )
                            continue
                        pass
                    except Exception:
                        pass

                    # Wait for key elements to be ready with increased timeout
                    try:
                        page_ready = await wait_for_video_page_ready(
                            context.page, timeout=30000  # Increased to 30 seconds
                        )
                        if not page_ready:
                            Actor.log.warning(
                                f"Video page may not be fully loaded, continuing anyway..."
                            )

                        # Additional wait for dynamic content to ensure everything is loaded
                        if not context.page.is_closed():
                            await context.page.wait_for_timeout(
                                3000
                            )  # Increased to 3 seconds
                    except PlaywrightError as e:
                        if "Target page, context or browser has been closed" in str(
                            e
                        ) or "Target closed" in str(e):
                            Actor.log.warning(f"Page/context closed during wait: {e}")
                            continue
                        raise

                    # Extract detailed video information directly
                    # Initialize video info dictionary
                    try:
                        video_url = context.page.url
                    except PlaywrightError as e:
                        if "Target page, context or browser has been closed" in str(
                            e
                        ) or "Target closed" in str(e):
                            Actor.log.warning(
                                f"Page/context closed when getting URL: {e}"
                            )
                            continue
                        video_url = link

                    detailed: dict[str, Any] = {
                        "video_url": video_url,
                        "title": None,
                        "duration": None,
                        "likes": None,
                        "creators": None,
                        "summary": None,
                        "comments_count": None,
                    }

                    # Check if page is still open before extraction
                    if context.page.is_closed():
                        Actor.log.warning("Page is closed, skipping video extraction")
                        continue

                    try:
                        # Extract duration - try multiple selectors
                        duration_selectors = [
                            'meta[itemprop="duration"]',  # Structured data (ISO 8601 format)
                            "span.ytp-time-duration",  # Video player duration
                            ".ytp-time-duration",  # Alternative player duration selector
                            "ytd-thumbnail-overlay-time-status-renderer span",  # Thumbnail overlay duration
                            "span.style-scope.ytd-thumbnail-overlay-time-status-renderer",  # Alternative thumbnail duration
                            'yt-formatted-string[aria-label*="duration"]',  # Formatted string with duration
                            '.ytd-watch-info-text span:has-text(":")',  # Watch info text with time format
                        ]

                        duration = None
                        for selector in duration_selectors:
                            try:
                                # Check if page is still open
                                if context.page.is_closed():
                                    break
                                element = context.page.locator(selector).first
                                if await element.count() > 0:
                                    # Try to get content attribute first (for meta tags)
                                    if selector.startswith("meta"):
                                        duration = await element.get_attribute(
                                            "content"
                                        )
                                    else:
                                        # For other elements, get text content
                                        duration = await element.text_content()

                                    if duration:
                                        duration = duration.strip()
                                        # Check if it's ISO 8601 format (PT4M13S)
                                        if duration.startswith("PT"):
                                            # Parse ISO 8601 duration format (PT4M13S -> 4:13)
                                            duration = (
                                                duration.replace("PT", "")
                                                .replace("H", ":")
                                                .replace("M", ":")
                                                .replace("S", "")
                                            )
                                            # Handle cases like "4:13" or ":13" (missing minutes)
                                            parts = duration.split(":")
                                            if len(parts) == 2 and not parts[0]:
                                                duration = f"0:{parts[1]}"
                                            elif len(parts) == 3:
                                                # Format: H:M:S -> H:MM:SS
                                                hours, minutes, seconds = parts
                                                if not hours:
                                                    hours = "0"
                                                if not minutes:
                                                    minutes = "0"
                                                if not seconds:
                                                    seconds = "0"
                                                duration = f"{hours}:{minutes.zfill(2)}:{seconds.zfill(2)}"
                                            detailed["duration"] = duration.strip()
                                            Actor.log.info(
                                                f"Found duration with selector '{selector}': {detailed['duration']}"
                                            )
                                            break
                                        # Check if it's already in time format (MM:SS or HH:MM:SS)
                                        elif re.match(
                                            r"^\d{1,2}:\d{2}(:\d{2})?$", duration
                                        ):
                                            detailed["duration"] = duration
                                            Actor.log.info(
                                                f"Found duration with selector '{selector}': {detailed['duration']}"
                                            )
                                            break
                            except PlaywrightError as e:
                                if (
                                    "Target page, context or browser has been closed"
                                    in str(e)
                                    or "Target closed" in str(e)
                                ):
                                    Actor.log.warning(
                                        f"Page/context closed during duration extraction: {e}"
                                    )
                                    raise
                                Actor.log.debug(
                                    f"Error with duration selector '{selector}': {e}"
                                )
                                continue
                            except Exception as e:
                                Actor.log.debug(
                                    f"Error with duration selector '{selector}': {e}"
                                )
                                continue

                        if not detailed["duration"]:
                            Actor.log.warning(
                                "Could not extract video duration with any selector"
                            )

                        # Extract likes - use the specific selector from YouTube
                        likes_selectors = [
                            "segmented-like-dislike-button-view-model button .yt-spec-button-shape-next__button-text-content",
                            'button[aria-label*="like"] span',
                            'yt-formatted-string[id="text"]:has-text("likes")',
                            '[aria-label*="like"]',
                            'button[aria-label*="Like"]',
                        ]

                        for selector in likes_selectors:
                            try:
                                # Try to find like button and extract the count
                                like_button = context.page.locator(selector).first
                                if await like_button.count() > 0:
                                    # Get text content from the element
                                    text = await like_button.text_content()
                                    if text:
                                        text = text.strip()
                                        # Extract number from text (e.g., "1.2K", "123", "1.5M")
                                        match = re.search(
                                            r"([\d,\.]+[KMB]?)", text, re.IGNORECASE
                                        )
                                        if match:
                                            detailed["likes"] = match.group(1)
                                            Actor.log.info(
                                                f"Found likes: {detailed['likes']}"
                                            )
                                            break
                                        # If no match but text exists, use it directly
                                        elif text:
                                            detailed["likes"] = text
                                            Actor.log.info(
                                                f"Found likes (direct): {detailed['likes']}"
                                            )
                                            break

                                    # Try to get aria-label as fallback
                                    aria_label = await like_button.get_attribute(
                                        "aria-label"
                                    )
                                    if aria_label:
                                        # Extract number from aria-label like "1.2K likes" or "123 likes"
                                        match = re.search(
                                            r"([\d,\.]+[KMB]?)\s*likes?",
                                            aria_label,
                                            re.IGNORECASE,
                                        )
                                        if match:
                                            detailed["likes"] = match.group(1)
                                            Actor.log.info(
                                                f"Found likes from aria-label: {detailed['likes']}"
                                            )
                                            break
                            except Exception as e:
                                Actor.log.debug(f"Error with selector {selector}: {e}")
                                continue

                        # Extract comments count - try multiple selectors
                        comments_selectors = [
                            "#title.style-scope.ytd-comments-header-renderer yt-formatted-string span",
                            "ytd-comments-header-renderer #count",
                            "ytd-comments-header-renderer .count-text",
                            "ytd-comments-header-renderer #title #count",
                            "yt-formatted-string.count-text",
                            "h2#count yt-formatted-string span",
                        ]

                        # Attempt to scroll to comments to ensure lazy-loaded content appears
                        try:
                            await context.page.evaluate(
                                "window.scrollBy(0, document.body.scrollHeight / 2);"
                            )
                            await context.page.wait_for_timeout(
                                1000
                            )  # Reduced from 2000 to 1000
                        except Exception:
                            pass

                        for selector in comments_selectors:
                            try:
                                element = context.page.locator(selector).first
                                if await element.count() > 0:
                                    comments_text = await element.text_content()
                                    if comments_text:
                                        detailed["comments_count"] = comments_text
                                        Actor.log.info(
                                            f"Found comments count: {detailed['comments_count']}"
                                        )
                                        break
                            except Exception as e:
                                Actor.log.debug(
                                    f"Error with comments selector {selector}: {e}"
                                )

                        # Extract creator/channel name - try multiple selectors
                        creator = await context.page.locator(
                            "ytd-channel-name a"
                        ).first.text_content()
                        if creator:
                            detailed["creators"] = creator
                            Actor.log.info(f"Found creators: {detailed['creators']}")

                        # Extract summary/description - try multiple selectors
                        summary_selectors = [
                            "#description-inline-expander span.yt-core-attributed-string--link-inherit-color",
                        ]

                        description = ""
                        summaryList = context.page.locator(summary_selectors[0])
                        count = await summaryList.count()
                        if count > 0:
                            for i in range(count):
                                summaryElement = summaryList.nth(i)
                                summary = await summaryElement.text_content()
                                if summary:
                                    description += summary.strip()
                                else:
                                    continue
                            detailed["summary"] = description
                            Actor.log.info(f"Found summary: {detailed['summary']}")

                    except PlaywrightError as e:
                        if "Target page, context or browser has been closed" in str(
                            e
                        ) or "Target closed" in str(e):
                            Actor.log.warning(
                                f"Page/context closed during video info extraction: {e}"
                            )
                            continue
                        Actor.log.error(
                            f"Playwright error extracting YouTube video info: {e}"
                        )
                        continue
                    except Exception as e:
                        Actor.log.error(f"Error extracting YouTube video info: {e}")
                        continue

                    # Merge detailed fields
                    video["video_url"] = detailed.get("video_url", link)
                    video["duration"] = detailed.get("duration")
                    video["likes"] = detailed.get("likes")
                    video["creators"] = detailed.get("creators")
                    video["summary"] = detailed.get("summary")
                    video["comments_count"] = detailed.get("comments_count")

                    detailed_video_info_list.append(video)

                    # Push each video individually to dataset immediately
                    await context.push_data(video)
                    Actor.log.info(
                        f"Saved video to dataset: {video.get('title', 'Unknown')}"
                    )

                    # Save individual video data to separate JSON file with UTF-8 encoding
                    video_filename = f"video{video_counter}.json"
                    video_json_data = json.dumps(video, ensure_ascii=False, indent=2)
                    await Actor.set_value(
                        video_filename,
                        video_json_data,
                        content_type="application/json; charset=utf-8",
                    )
                    Actor.log.info(
                        f"Saved video data to {video_filename} (UTF-8 encoding)"
                    )
                    video_counter += 1

                except Exception as e:
                    Actor.log.warning(f"Error visiting video {link}: {e}")
                    # Still save the basic video info even if detailed extraction failed
                    detailed_video_info_list.append(video)
                    await context.push_data(video)
                    Actor.log.info(
                        f"Saved basic video info to dataset: {video.get('title', 'Unknown')}"
                    )

                    # Save individual video data to separate JSON file with UTF-8 encoding
                    video_filename = f"video{video_counter}.json"
                    video_json_data = json.dumps(video, ensure_ascii=False, indent=2)
                    await Actor.set_value(
                        video_filename,
                        video_json_data,
                        content_type="application/json; charset=utf-8",
                    )
                    Actor.log.info(
                        f"Saved video data to {video_filename} (UTF-8 encoding)"
                    )
                    video_counter += 1

            # Save all video_info_list to JSON file in key-value store (for backup/reference)
            Actor.log.info(
                f"Saving {len(detailed_video_info_list)} video information to JSON file..."
            )
            json_data = json.dumps(
                detailed_video_info_list, ensure_ascii=False, indent=2
            )
            await Actor.set_value(
                "video_information.json", json_data, content_type="application/json"
            )
            Actor.log.info(
                "Video information saved to key-value store as 'video_information.json'"
            )

        # Reset scraped count at start
        await Actor.set_value("scraped_videos_count", 0)

        # Run the crawler with the starting requests.
        await crawler.run(start_urls)
