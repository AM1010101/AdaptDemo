import requests

response = requests.get("https://api.scrapingdog.com/scrape", params={
  'api_key': '6842c97fd9e8bb8d222525ec',
  'url': 'https://www.backmarket.co.uk/en-gb/p/iphone-12-64-gb-black-unlocked/ec0b1d0d-251d-456e-bcd6-978be85e25d6?l=12#',
  'dynamic': 'false',
  'markdown': 'true'
  })

# print(response.text)
# write response to file in data folder


with open("scraping_dog_response.txt", "w", encoding="utf-8") as file:
    file.write(response.text)