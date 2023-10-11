import asyncio
import json
import time
import re
from copy import copy
import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode
from art import tprint
import aiohttp
import requests
from bs4 import BeautifulSoup
import logging
import settings


class URL:
    def __init__(self, url: str):
        self.url = url

    def update_query(self, new_params=None):
        if new_params is None:
            new_params = {}

        parsed_url = urlparse(self.url)
        # Превращаю в словарь GET запрос
        query_params = parse_qs(parsed_url.query)
        # Соеденить словари
        query_params.update(new_params)
        # Составить запрос в виде строки из словаря
        updated_query = urlencode(query_params, doseq=True)
        # Замена query у объекте URL
        parsed_url = parsed_url._replace(query=updated_query)
        self.url = parsed_url.geturl()

    def set_query(self, new_params=None):
        if new_params is None:
            new_params = {}
        parsed_url = urlparse(self.url)
        # Составить запрос в виде строки из словаря
        updated_query = urlencode(new_params, doseq=True)
        # Замена query у объекте URL
        parsed_url = parsed_url._replace(query=updated_query)
        self.url = parsed_url.geturl()

    @property
    def root_url(self):
        parsed_url = urlparse(self.url)
        return parsed_url.scheme + "://" + parsed_url.netloc

    def __str__(self) -> str:
        return self.url


class BaseParser:

    def __init__(self, html_page=None, bs_tag=None):
        if html_page and bs_tag:
            raise AttributeError(f"html_page & bs_tag is None!")
        self.soup = BeautifulSoup(html_page, 'lxml') if html_page else bs_tag


class ParserProductTag(BaseParser):

    def __init__(self, bs_tag=None):
        super().__init__(bs_tag=bs_tag)

    @property
    def id(self) -> int:
        return int(self.soup['data-sku'])

    @property
    def title(self) -> str:
        return self.soup.find(class_='product-card-name__text').text.strip()

    @property
    def price(self) -> tuple[float | None, float | None]:
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


class ParserCatalogProduct(BaseParser):
    def __init__(self, html_page=None):
        super().__init__(html_page=html_page)

    @property
    def address(self):
        return self.soup.find(class_="header-address__receive-address").text.strip()

    @property
    def pagination_list(self) -> range:
        try:
            items_pagination = self.soup.select("ul.catalog-paginate.v-pagination")[0].findAll('li')
            items_pagination = map(lambda x: x.text, items_pagination)
            items_pagination = [int(x) for x in items_pagination if x.isdigit()]
            return range(min(items_pagination), max(items_pagination) + 1)
        except IndexError:
            return range(1, 2)


class ParserPageProduct(BaseParser):

    def __init__(self, html_page=None):
        super().__init__(html_page=html_page)

    @property
    def characteristics_table(self) -> dict:
        table = self.soup.find(class_="product-attributes__list style--product-page-full-list").find_all(
            class_="product-attributes__list-item")
        table = [x.text.replace("\n", "").strip().split("   ") for x in table]
        table = [sublist[0:1] + sublist[-1:] for sublist in table]
        return {k.strip().lower(): v.strip() for (k, v) in table}


class MetroManagerParser:
    def __init__(self, url_path: str, metro_store_id: int, in_stock: bool = False):
        self.address = None
        self.url_path = url_path
        self.in_stock = in_stock
        self.cookies = copy(settings.cookies)
        self.cookies['metroStoreId'] = f'{metro_store_id}'

    def get_all_product_in_category(self):
        url = URL(self.url_path)
        if self.in_stock:
            url.update_query({'in_stock': 1})

        page = requests.get(url.url, cookies=self.cookies, headers=settings.headers).text
        parser_category = ParserCatalogProduct(page)
        self.address = parser_category.address
        logging.info(f"Адрес: {parser_category.address}")
        pagination = parser_category.pagination_list
        logging.info(f"Пагинация {pagination}")
        products = asyncio.run(self._create_tasks_grab_all_category_pages(pagination))

        # Преобразование списка  [[{}, {}, {}], [{}]] -> [{}, {}, {}, {}]
        return [d for sublist in products for d in sublist if d]

    async def _create_tasks_grab_all_category_pages(self, pagination):
        async with aiohttp.ClientSession() as session:
            tasks = []
            for page in pagination:
                task = asyncio.create_task(self._get_products_in_page_category(session=session, page=page))
                tasks.append(task)
            return await asyncio.gather(*tasks)
        
    async def _get_products_in_page_category(self, session, page):
        url = URL(self.url_path)
        url.update_query({'page': page})
        if self.in_stock:
            url.update_query({'in_stock': 1})
        async with session.get(url=url.url, cookies=self.cookies, headers=settings.headers) as response:

            soup = BeautifulSoup(await response.text(), "lxml")

            products = soup.find_all('div', attrs={'data-sku': True})
            i = 0
            list_product = []
            for product in products:
                product = ParserProductTag(product)
                actual_price, old_price = product.price
                i += 1
                obj_product = {
                    'id': product.id,
                    'title': product.title,
                    'url': f"{url.root_url}" + product.link,
                    'regular_price': old_price if old_price else actual_price,
                    'promo_price': actual_price if old_price else None,
                    'brand': None
                }
                list_product.append(obj_product)
            logging.info(f"[INFO] - парсинг страницы - {page} (собрано {i} товаров)")
            return list_product

    def supplement_products_in_single_page(self, products_list: list[dict]):
        return asyncio.run(self._create_tasks_supplements(products_list=products_list))

    async def _create_tasks_supplements(self, products_list: list[dict]):
        async with aiohttp.ClientSession() as session:
            tasks = []
            for product in products_list:
                task = asyncio.create_task(self._supplement_product_data(data_product=product, session=session))
                tasks.append(task)
            return await asyncio.gather(*tasks)

    async def _supplement_product_data(self, data_product, session=None):
        url = data_product['url']
        async with session.get(url, cookies=self.cookies, headers=settings.headers) as response:
            html_page = await response.text()
            parser_product_page = ParserPageProduct(html_page)
            characteristics_table = parser_product_page.characteristics_table
            data_product['brand'] = characteristics_table["бренд"]
            return data_product


class ConsoleMenu:

    def __init__(self):
        self.url_path = None
        self.metro_store_id = None
        tprint("( Metro - parser )")
        print("Что бы войти в найтройки введите: settings")
        self.br()
        self.main_menu()

    def br(self):
        print("________________________________________________________________________________________\n")

    def main_menu(self):
        first_message = input("Введите ссылку на категорию: ")
        if first_message.strip() == 'settings':
            self.settings_menu()
        self.set_url_path(first_message)
        self.br()
        self.view_shop_in_moscow_and_spb()
        self.set_metro_store_id()
        self.br()

    def set_url_path(self, url_path=None):
        if url_path is None:
            self.url_path = input("Введите ссылку на категорию: ")
        else:
            self.url_path = url_path
        return self.url_path

    def set_metro_store_id(self):
        print("Введите ID: магазина METRO который необходимо спарсить.\nДля вывода всех магазинов введите list ")
        store_id = input("-->")
        store_id = store_id.strip()
        if store_id == "list":
            self.view_all_city()
            self.set_metro_store_id()

        if not store_id.isdigit():
            print("ERROR[]: - - -  ID магазина должно быть числом - - -")
            time.sleep(1)
            self.set_metro_store_id()

        self.metro_store_id = int()
        return self.metro_store_id

    def settings_menu(self):
        self.br()
        print("--- SETTINGS ---")
        print(f"""Текущий путь сохранения файлов: {settings.SAVE_PATH}\n""")
        print(f"""Действия:\n  1)Изменить путь сохранения данных\n  0)Назад""")
        do = input("--> ")
        do = do.strip()
        match do:
            case '1':
                self.edit_save_path()
            case '0':
                self.main_menu()
            case _:
                print(f"Действия со значением ({do}) не предусмотренны!")
                self.settings_menu()

    def view_all_city(self):
        for city, streets in settings.STORES_IN_CITY.items():
            print(f"Город -> [{city}]")
            for street in streets:
                address = street['address']
                store_id = street['store_id']
                print(f"    ID -> [{store_id}] | Улица -> [{address}]")
            print()

    def view_shop_in_moscow_and_spb(self):
        moscow = settings.STORES_IN_CITY["Москва"]
        spb = settings.STORES_IN_CITY["Санкт-Петербург"]

        print("Магазины Москвы:")
        for datashop in moscow:
            address = datashop['address']
            store_id = datashop['store_id']
            print(f"  ID: {store_id} | Адрес: '{address}'")
        print()
        print("Санкт-Петербургa:")
        for datashop in spb:
            address = datashop['address']
            store_id = datashop['store_id']
            print(f"  ID: {store_id} | Адрес: '{address}'")
        self.br()

    def edit_save_path(self):
        self.br()
        print(f"""Текущий путь сохранения файлов: {settings.SAVE_PATH}\n""")
        print("Введите новый путь сохранения\nДля отмены введите: 0")
        do = input("--> ")
        do.strip()
        match do:
            case "0":
                self.settings_menu()
            case _:
                path = Path(do)
                if not path.exists():
                    path.mkdir(parents=True)
                with open(settings.config_json_path, 'w') as f:
                    data = {"SAVE_PATH": path.__str__()}
                    settings.SAVE_PATH = path
                    json.dump(data, fp=f)
                print(f"[INFO] new save folder: {path}\nНовый путь сохранения файлов установлен! ")
                self.settings_menu()


if __name__ == '__main__':
    console_menu = ConsoleMenu()
    print("Начало парсинга")
    start = time.time()
    parser_metro = MetroManagerParser(url_path=console_menu.url_path, metro_store_id=console_menu.metro_store_id, in_stock=True)
    products = parser_metro.get_all_product_in_category()
    print("Элементов: ", products.__len__())
    print(f"Загрузка данных из каталога завершена за {time.time() - start} секунд.")

    start = time.time()
    parser_metro.supplement_products_in_single_page(products_list=products)
    print("Элементов: ", products.__len__())
    print(f"Загрузка данных о каждом продукте завершена за {time.time() - start} секунд.")

    current_datetime = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M")
    address = parser_metro.address.replace(',', '').replace(' ', '_').replace(".", "_")
    filename = settings.SAVE_PATH / f"{current_datetime}_{address}_onlineMetroRu.json"
    with open(filename, 'w') as file:
        json.dump(products, file)
    print(f"Данные сохранены в {filename}")
