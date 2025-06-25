import requests

url = "https://r.jina.ai/https://www.backmarket.co.uk/en-gb/p/iphone-12-64-gb-black-unlocked/ec0b1d0d-251d-456e-bcd6-978be85e25d6?l=12#"
headers = {
    "Authorization": "Bearer jina_23b4a4c3279b415ebf2154e61ee16e3baUxtZGIP_EkgX44RAe33tLWwenv_"
}

response = requests.get(url, headers=headers)

print(response.text)

# write the resposne to a file
with open("response.txt", "w", encoding="utf-8") as file:
    file.write(response.text)