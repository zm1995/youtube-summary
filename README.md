## Python Crawlee with Playwright template

<!-- This is an Apify template readme -->

A template for [web scraping](https://apify.com/web-scraping) data from websites starting from provided URLs using Python. The starting URLs are passed through the Actor's input schema, defined by the [input schema](https://docs.apify.com/platform/actors/development/input-schema). The template uses [Crawlee for Python](https://crawlee.dev/python) for efficient web crawling, making requests via headless browser managed by [Playwright](https://playwright.dev/python/), and handling each request through a user-defined handler that uses [Playwright](https://playwright.dev/python/) API to extract data from the page. Enqueued URLs are managed in the [request queue](https://crawlee.dev/python/api/class/RequestQueue), and the extracted data is saved in a [dataset](https://crawlee.dev/python/api/class/Dataset) for easy access.

## Included features

- **[Apify SDK](https://docs.apify.com/sdk/python/)** - a toolkit for building Apify [Actors](https://apify.com/actors) in Python.
- **[Crawlee for Python](https://crawlee.dev/python/)** - a web scraping and browser automation library.
- **[Input schema](https://docs.apify.com/platform/actors/development/input-schema)** - define and validate a schema for your Actor's input.
- **[Request queue](https://crawlee.dev/python/api/class/RequestQueue)** - manage the URLs you want to scrape in a queue.
- **[Dataset](https://crawlee.dev/python/api/class/Dataset)** - store and access structured data extracted from web pages.
- **[Playwright](https://playwright.dev/python/)** - a library for managing headless browsers.

## Resources

- [Video introduction to Python SDK](https://www.youtube.com/watch?v=C8DmvJQS3jk)
- [Webinar introducing to Crawlee for Python](https://www.youtube.com/live/ip8Ii0eLfRY)
- [Apify Python SDK documentation](https://docs.apify.com/sdk/python/)
- [Crawlee for Python documentation](https://crawlee.dev/python/docs/quick-start)
- [Python tutorials in Academy](https://docs.apify.com/academy/python)
- [Integration with Make, GitHub, Zapier, Google Drive, and other apps](https://apify.com/integrations)
- [Video guide on getting scraped data using Apify API](https://www.youtube.com/watch?v=ViYYDHSBAKM)
- A short guide on how to build web scrapers using code templates:

[web scraper template](https://www.youtube.com/watch?v=u-i-Korzf8w)


## Getting started

For complete information [see this article](https://docs.apify.com/platform/actors/development#build-actor-at-apify-console). In short, you will:

1. Build the Actor
2. Run the Actor

## Environment Variables and Secrets

This Actor supports YouTube login via credentials. You can provide credentials in two ways:

1. **Via Input Schema**: Enter `youtube_email` and `youtube_password` in the Actor input
2. **Via Environment Variables**: Set the following environment variables:
   - `YOUTUBE_EMAIL`: Your YouTube account email
   - `YOUTUBE_PASSWORD`: Your YouTube account password (secret)

### Setting Secrets in Apify Console

To set `YOUTUBE_PASSWORD` as a secret environment variable:

1. Go to your Actor in the Apify Console
2. Navigate to **Settings** → **Environment variables**
3. Click **Add environment variable**
4. Set:
   - **Name**: `YOUTUBE_PASSWORD`
   - **Value**: Your YouTube password
   - **Secret**: ✅ Enable this checkbox to mark it as a secret
5. Click **Save**

The Actor will automatically use the environment variable if it's set, otherwise it will use the input values.

**Note**: Secrets are encrypted and never exposed in logs or output.

## Pull the Actor for local development

If you would like to develop locally, you can pull the existing Actor from Apify console using Apify CLI:

1. Install `apify-cli`

    **Using Homebrew**

    ```bash
    brew install apify-cli
    ```

    **Using NPM**

    ```bash
    npm -g install apify-cli
    ```

2. Pull the Actor by its unique `<ActorId>`, which is one of the following:
    - unique name of the Actor to pull (e.g. "apify/hello-world")
    - or ID of the Actor to pull (e.g. "E2jjCZBezvAZnX8Rb")

    You can find both by clicking on the Actor title at the top of the page, which will open a modal containing both Actor unique name and Actor ID.

    This command will copy the Actor into the current directory on your local machine.

    ```bash
    apify pull <ActorId>
    ```

## Documentation reference

To learn more about Apify and Actors, take a look at the following resources:

- [Apify SDK for JavaScript documentation](https://docs.apify.com/sdk/js)
- [Apify SDK for Python documentation](https://docs.apify.com/sdk/python)
- [Apify Platform documentation](https://docs.apify.com/platform)
- [Join our developer community on Discord](https://discord.com/invite/jyEM2PRvMU)
