import requests

API_KEY = 'YOUR API KEY HERE'  # replace with your API key
MODEL_ID = 'jellybelly3'
MODEL_VERSION = '3'

headers = {
    'Authorization': f'Bearer {API_KEY}',
}

response = requests.get(f'https://api.roboflow.com/model/{MODEL_ID}/{MODEL_VERSION}', headers=headers)

if response.status_code == 200:
    print("API key is valid!")
elif response.status_code == 401:
    print("Invalid API key!")
else:
    print(f"Unexpected response: {response.status_code} - {response.text}")
