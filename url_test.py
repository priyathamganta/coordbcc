import requests

url = "http://127.0.0.1:5000/api/change"
params = {'file_name': 'test.rules'}
r = requests.get(url=url, params=params)
print(r)
