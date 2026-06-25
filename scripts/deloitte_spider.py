import scrapy
import json
from w3lib.html import remove_tags
from tqdm import tqdm
from scrapy import signals

class DeloitteJobsSpider(scrapy.Spider):
    """
    Spider to extract job postings from the Deloitte USI Careers portal.
    Includes a dynamic tqdm progress bar and pretty-printed JSON output.
    """
    name = "deloitte_jobs"
    allowed_domains = ["usijobs.deloitte.com"]
    start_urls = ["https://usijobs.deloitte.com/en_US/careersUSI/SearchJobs/"]

    # 1. Format the JSON output using Scrapy's custom_settings
    custom_settings = {
        'FEED_FORMAT': 'json',
        'FEED_URI': 'jobs.json',
        'FEED_EXPORT_INDENT': 4, # This ensures the JSON is well-structured and pretty-printed
        'LOG_LEVEL': 'DEBUG',     # Mutes debug logs so the progress bar renders cleanly in the terminal
    }

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        """
        Instantiates the spider and connects Scrapy signals to the tqdm progress bar.
        """
        spider = super(DeloitteJobsSpider, cls).from_crawler(crawler, *args, **kwargs)
        
        # Initialize tqdm as a counter (since we don't know the total number of jobs upfront)
        spider.pbar = tqdm(desc="Jobs Scraped", unit="job")
        
        # Connect the item_scraped signal to update the progress bar
        crawler.signals.connect(spider.item_scraped, signal=signals.item_scraped)
        crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
        
        return spider

    def item_scraped(self, item, response, spider):
        """Callback: Updates the progress bar every time a job is yielded."""
        self.pbar.update(1)

    def spider_closed(self, spider):
        """Callback: Closes the progress bar cleanly when the spider finishes."""
        self.pbar.close()

    def parse(self, response):
        """
        Parses the main search results page.
        Extracts links to individual job postings and follows pagination.
        """
        job_links = response.css('article.article--result h3 a.link::attr(href)').getall()
        
        for link in job_links:
            yield response.follow(link, callback=self.parse_job)

        next_page = response.css('a.paginationNextLink::attr(href)').get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)

    def parse_job(self, response):
        """
        Parses individual job pages.
        Locates the application/ld+json block, parses it, and cleans the text.
        """
        ld_json_data = response.xpath('//script[@type="application/ld+json"]/text()').get()

        if ld_json_data:
            try:
                job_data = json.loads(ld_json_data)
                
                yield {
                    'job_id': job_data.get('identifier', {}).get('value'),
                    'title': job_data.get('title'),
                    'url': response.url,
                    'date_posted': job_data.get('datePosted'),
                    'location': self._format_location(job_data.get('jobLocation', {})),
                    'description': self._clean_text(job_data.get('description')),
                    'qualifications': self._clean_text(job_data.get('qualifications')),
                    'experience_requirements': self._clean_text(job_data.get('experienceRequirements')),
                    'hiring_organization': job_data.get('hiringOrganization', {}).get('name')
                }
            except json.JSONDecodeError:
                self.logger.error(f"Failed to decode JSON-LD on {response.url}")

    def _format_location(self, location_data):
        """
        Extracts and formats the physical location from the Schema.org Place object.
        """
        address = location_data.get('address', {})
        locality = address.get('addressLocality', '')
        region = address.get('addressRegion', '')
        
        parts = [part for part in [locality, region] if part]
        return ", ".join(parts) if parts else "Multiple Locations / Unspecified"

    def _clean_text(self, raw_html):
        """
        Strips HTML tags and standardizes whitespace for clean JSON formatting.
        """
        if not raw_html:
            return None
            
        text = remove_tags(raw_html)
        return " ".join(text.split())