import json
import os
from pathlib import Path

ROOT_PATH = Path(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = ROOT_PATH / 'configs'
config_json_path = CONFIG_PATH / 'config.json'

if not config_json_path.exists():
    with open(config_json_path, 'w') as f:
        path = ROOT_PATH / 'jsons'
        data = {"SAVE_PATH": path.__str__() }
        json.dump(data, fp=f)

with open(config_json_path, 'r') as f:
    data = json.load(f)
    try:
        SAVE_PATH = Path(data["SAVE_PATH"])
    except (TypeError, KeyError):
        with open(config_json_path, 'w') as f:
            path = Path('jsons')
            data = {"SAVE_PATH": path.__str__()}
            json.dump(data, fp=f)
        SAVE_PATH = path


if not SAVE_PATH.exists():
    SAVE_PATH.mkdir(parents=True)

cookies = {
    'is18Confirmed': 'true',
    'metroStoreId': '10',
    '_ym_isad': '2',
    '_ym_visorc': 'w',
}

headers = {
    'authority': 'online.metro-cc.ru',
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'accept-language': 'ru,en;q=0.9,en-GB;q=0.8,en-US;q=0.7',
    'cache-control': 'max-age=0',
    'dnt': '1',
    'if-none-match': '"1fcdd4-MEtp9tGesqqDa+/XHqrLShfvoVE"',
    'referer': 'https://online.metro-cc.ru/',
    'sec-ch-ua': '"Microsoft Edge";v="117", "Not;A=Brand";v="8", "Chromium";v="117"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'same-origin',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 Edg/117.0.2045.60'
}

with open(CONFIG_PATH / 'stores.json', 'r', encoding="utf-8") as f:
    stores_data = json.load(f)

ADDRESS_STORES = []
for store in stores_data:
    store_data = {
        'city': store["city"],
        'address': store['name'],
        "store_id": store['store_id']
    }
    ADDRESS_STORES.append(store_data)

STORES_IN_CITY = {}
for item in ADDRESS_STORES:
    city = item['city']
    address = item['address']
    store_id = item['store_id']

    if city not in STORES_IN_CITY:
        STORES_IN_CITY[city] = []
    STORES_IN_CITY[city].append({'address': address, 'store_id': store_id})
