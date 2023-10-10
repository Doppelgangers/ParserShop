import dataclasses
import logging
import urllib.parse
from pathlib import Path
import re
import aiohttp
import asyncio
import requests
from bs4 import BeautifulSoup


# @dataclasses.dataclass
# class Product:
#     id: int
#     title: str
#     url: str
#     regular_price: float
#     promo_price: float = None
#     brand: str = None
#
#     def __str__(self):
#         return \
# f"""
# ===== {self.id} =====
# Title: {self.title}
# URL: {self.url}
# RegularPrice: {self.regular_price}
# PromoPirce: {self.promo_price}
# Brand: {self.brand}
# """

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


class Parser:
    def __init__(self, url, file: Path | str = None, cookies=None):
        self.url = url
        self.base_url = self.base_url(self.url)
        html_page = self.get_html_for_url(self.url, cookies=cookies) if file is None else self.get_html_for_file(file)
        self.soup = BeautifulSoup(html_page, 'lxml')

    @staticmethod
    def base_url(url, with_path=False):
        parsed = urllib.parse.urlparse(url)
        path = '/'.join(parsed.path.split('/')[:-1]) if with_path else ''
        parsed = parsed._replace(path=path)
        parsed = parsed._replace(params='')
        parsed = parsed._replace(query='')
        parsed = parsed._replace(fragment='')
        return parsed.geturl()

    @staticmethod
    def get_html_for_url(url, save: bool = False, cookies=None, headers=None, params=None):
        response = requests.get(url, cookies=cookies, headers=headers, params=params)
        if save:
            with open("body.html", 'w') as f:
                f.write(response.text)
        return response.content

    @staticmethod
    def get_html_for_file(path: Path | str):
        with open(path, 'r') as f:
            return f.read()


class ParserProduct:
    def __init__(self, html_block):
        self.soup: BeautifulSoup = html_block

    @property
    def id(self) -> int:
        return int(self.soup['data-sku'])

    @property
    def title(self) -> str:
        return self.soup.find(class_='product-card-name__text').text.strip()

    @property
    def price(self):
        prices = self.soup.find(class_="product-card-prices__content")

        try:
            actual = prices.find(class_="product-card-prices__actual").find(class_="product-price__sum").text
            actual = re.sub(r"[^\d\.]", '', actual)
            actual = float(actual)
        except (ValueError, AttributeError):
            actual = None

        try:
            old = prices.find(class_="product-card-prices__old").find(class_="product-price__sum").text
            old = re.sub(r"[^\d\.]", '', old)
            old = float(old)
        except (ValueError, AttributeError):
            old = None

        return actual, old

    @property
    def link(self) -> str:
        return self.soup.find("a")["href"]


class MainParser(Parser):

    def __init__(self, url: str, metro_store_id, file: Path | str = None):
        cookies['metroStoreId'] = f'{metro_store_id}'
        self.url = url.split("?")[0]
        super().__init__(url=self.url, file=file, cookies=cookies)

    @property
    def address(self):
        return self.soup.find(class_="header-address__receive-address")

    @property
    def pagination_list(self) -> range:
        items_pagination = self.soup.find(class_="subcategory-or-type__pagination").findAll('li')
        items_pagination = map(lambda x: x.text, items_pagination)
        items_pagination = [int(x) for x in items_pagination if x.isdigit()]
        return range(min(items_pagination), max(items_pagination) + 1)

    async def parse_all_page(self):
        self.list_product = []
        async with aiohttp.ClientSession() as session:
            tasks = []
            for page in self.pagination_list:
                task = asyncio.create_task(self.get_items_for_page(session, page))
                tasks.append(task)
            await asyncio.gather(*tasks)

    async def get_items_for_page(self, session, page):
        async with session.get(url=self.url, params={'page': f'{page}'}, cookies=cookies, headers=headers) as response:
            html_page = await response.text()
            soup = BeautifulSoup(html_page, "lxml")

            products = soup.select('div.subcategory-or-type__products-item.catalog--common')
            i = 0
            for product in products:
                product = ParserProduct(product)
                actual_price, old_price = product.price
                i+=1
                obj_product = {
                    'id': product.id,
                    'title': product.title,
                    'url': f"{self.base_url}" + product.link,
                    'regular_price': old_price if old_price else actual_price,
                    'promo_price': actual_price if old_price else None,
                }

                self.list_product.append(obj_product)
            logging.debug(f"[INFO] - парсинг страницы - {page} (собрано {i} товаров)")


if __name__ == "__main__":
    m_par = MainParser(url='https://online.metro-cc.ru/category/chaj-kofe-kakao/kofe?from=under_search', metro_store_id=16)
    asyncio.run(m_par.parse_all_page())
    print(m_par.list_product.__len__())


