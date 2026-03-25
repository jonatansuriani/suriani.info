---
title: "Using Python and Scrapy to Scrape Beer Data"
date: 2022-12-30 12:00:00 +0000
layout: post
permalink: /post/using-python-and-scrapy-to-scrape-beer-data-1/
---
![](/assets/images/posts/using-python-and-scrapy-to-scrape-beer-data-1/11062b_8772b9f42c3d4a4fb860fddcc303ccf4~mv2.jpeg)

I'm on a new project creating a (new) database with beer data, so it can be used later to enrich data from ratings, also to create specific user experience. There are a few places that have this public information, and using Scrapy is one of the easiest ways of creating a webcrawler/webscraper to gather this information to be processed in order to create this new database.

> Scrapy is a fast high-level [web crawling](https://en.wikipedia.org/wiki/Web_crawler) and [web scraping](https://en.wikipedia.org/wiki/Web_scraping) framework, used to crawl websites and extract structured data from their pages. It can be used for a wide range of purposes, from data mining to monitoring and automated testing.

The source-code for this project can be found at [_github_](https://github.com/jonatansuriani/beer-crawlers).

The first scraper I've created focus on getting data from [_BeerAdvocate.com_](https://beeradvocate.com) _,_ and the strategy consists on first getting data from Styles, then for each style I get Beers details, and for each beer, I get brewery details.

The spider created is called [**_BeerAdvocateSpider_**](https://github.com/jonatansuriani/beer-crawlers/blob/c496fa13f1dbe7925442296fd726447f6bd6fa2f/beercrawler/beercrawler/spiders/beeradvocate.py) , and use the style listing page as starting url:

![](/assets/images/posts/using-python-and-scrapy-to-scrape-beer-data-1/da009b_6ee2beadb06b46c2b229da96b7864fab~mv2.png)

The strategy is to get data from each style listed, as follows:

    def parse(self, response):
    	style_pages = '#ba-content li a'
    	yield from response.follow_all(css=style_pages, callback=self.parse_style)

The _response.follow_all_ get details of each style. For instance, this is the Bock style page:

![](/assets/images/posts/using-python-and-scrapy-to-scrape-beer-data-1/da009b_048d93e91cb343ddad63da61d406e3db~mv2.png)

And this is how it's data is read:

    def parse_style(self, response):
    	def from_content(query):
    		content_xpath = '//div[@id="ba-content"]/div[1]';
    		return response.xpath(content_xpath).xpath(query).get(default='').strip()

    	beers_page = response.xpath("//tr//td//a[contains(@href, '/beer/profile/')][1]")
    	yield from response.follow_all(beers_page, callback=self.parse_beer)

    	yield {
    		'type' : 'style',
    		'original_url': response.url,
    		'doc': {
    			'name': response.css('h1::text').get(),
    			'description': from_content('text()'),
    			'abv': from_content('span[contains(.,"ABV:")]/text()'),
    			'ibu': from_content('span[contains(.,"IBU:")]/text()')
    		}
    	}

Then we get details for each beer listed:

    def parse_beer(self, response):
    	brewery_url = response.urljoin(response.xpath("//dt[contains(.,'From:')]/following-sibling::dd[1]/a/@href").get())

    	yield response.follow(brewery_url, callback=self.parse_brewery)

    	yield {
    		'type' : 'beer',
    		'original_url': response.url,
    		'doc':{
    			'name': response.css('h1::text').get(),
    			'images': response.xpath('//div[@id="main_pic_norm"]/div/img').getall(),
    			'brewery': {
    				'original_url': brewery_url,
    				'name': response.xpath("//dt[contains(.,'From:')]/following-sibling::dd[1]/a/b/text()").get()
    			}
    		}
    	}

Then, for each Brewery,its details are scraped using:

    def parse_brewery(self, response):

    	yield {
    		'type' : 'brewery',
    		'original_url': response.url,
    		'doc':{
    			'name': response.css('h1::text').get(),
    			'images': response.xpath('//div[@id="main_pic_norm"]/img/@src').getall(),
    			'address':{
    				'address':  response.xpath('//div[@id="info_box"]/text()').get()[2:3],
    				'zipcode':  response.xpath('//div[@id="info_box"]/text()').get()[4:5],
    				'city': response.xpath('//div[@id="info_box"]/a/text()').getall()[0],
    				'state': response.xpath('//div[@id="info_box"]/a/text()').getall()[1],
    				'country': response.xpath('//div[@id="info_box"]/a/text()').getall()[2],
    				'map': response.xpath('//div[@id="info_box"]/a/@href').getall()[3],
    				'website': response.xpath('//div[@id="info_box"]/a/@href').getall()[4]
    			}
    		}
    	}

To run the project, follow [_setup instructions on github_](https://github.com/jonatansuriani/beer-crawlers#setup) , then to run it locally specify the _beeradvocate_ crawler and the choose the [feed export](https://docs.scrapy.org/en/latest/topics/feed-exports.html#topics-feed-format-json). To export as json file run:

    scrapy crawl beeradvocate -O data.json

This is a sample of the data generated: [_sample-data.json_](https://github.com/jonatansuriani/beer-crawlers/blob/d5777fbbe38fbdbad3e9c614b95bff82357fa50e/sample-data.json)

Next step for this project consists in uploading the data to S3 using [_S3 Feed Storage_](https://docs.scrapy.org/en/latest/topics/feed-exports.html#topics-feed-storage-s3) , then data can be read and sent to a Kafka topic for later processing.
