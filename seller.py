import io
import logging.config
import os
import re
import zipfile
from environs import Env

import pandas as pd
import requests

logger = logging.getLogger(__file__)


def get_product_list(last_id, client_id, seller_token):
    """Получить список товаров

    Args:
        last_id (str): идентификатор последнего товара в списке товаров для продавца 
        client_id (str): идентификатор клиента 
        seller_token (str): токен продавца

    Returns:
        list: список товаров
    Example:
        >>> get_product_list('123', '456', '434')
        [{"offer_id": "123", "price": 100}, {"offer_id": "456", "price": 0}]
        >>> get_product_list('', '456', '434')
        []
    """

    url = "https://api-seller.ozon.ru/v2/product/list"
    headers = {
        "Client-Id": client_id,
        "Api-Key": seller_token,
    }
    payload = {
        "filter": {
            "visibility": "ALL",
        },
        "last_id": last_id,
        "limit": 1000,
    }
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    response_object = response.json()
    return response_object.get("result")


def get_offer_ids(client_id, seller_token):
    """Получить идентификаторы товаров

    Args:
        client_id (str): идентификатор клиента
        seller_token (str): токен продавца

    Returns:
        list: список идентификаторов
    Example:
        >>> get_offer_ids('456', '434')
        ['123', '456']

    """

    last_id = ""
    product_list = []
    while True:
        some_prod = get_product_list(last_id, client_id, seller_token)
        product_list.extend(some_prod.get("items"))
        total = some_prod.get("total")
        last_id = some_prod.get("last_id")
        if total == len(product_list):
            break
    offer_ids = []
    for product in product_list:
        offer_ids.append(product.get("offer_id"))
    return offer_ids


def update_price(prices: list, client_id, seller_token):
    """Обновить цены

    Args:
        prices (list): список цен
        client_id (str): идентификатор клиента
        seller_token (str): токен продавца

    Returns:
        list: список цен
    Example:
        >>> update_price(123, '456', '434')
        [{"offer_id": "123", "price": 100}, {"offer_id": "456", "price": 0}]

    """

    url = "https://api-seller.ozon.ru/v1/product/import/prices"
    headers = {
        "Client-Id": client_id,
        "Api-Key": seller_token,
    }
    payload = {"prices": prices}
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


def update_stocks(stocks: list, client_id, seller_token):
    """Обновить остатки товаров

    Args:
        stocks (list): список остатков
        client_id (str): идентификатор клиента 
        seller_token (str): токен продавца

    Returns:
        list: список остатков
    example:
        >>> update_stocks(123, '456', '434')
        [{"offer_id": "123", "stock": 100}, {"offer_id": "456", "stock": 0}]
        >>> update_stocks([], '456', '434')
        []

    """

    url = "https://api-seller.ozon.ru/v1/product/import/stocks"
    headers = {
        "Client-Id": client_id,
        "Api-Key": seller_token,
    }
    payload = {"stocks": stocks}
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


def download_stock():
    """Скачать остатки с сайта

    Returns:
        list: список остатков
    example:
        >>> download_stock()
        [{"offer_id": "123", "stock": 100}, {"offer_id": "456", "stock": 0}]
        >>> download_stock()
        []
    """

    # Скачать остатки с сайта
    casio_url = "https://timeworld.ru/upload/files/ostatki.zip"
    session = requests.Session()
    response = session.get(casio_url)
    response.raise_for_status()
    with response, zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        archive.extractall(".")
    # Создаем список остатков часов:
    excel_file = "ostatki.xls"
    watch_remnants = pd.read_excel(
        io=excel_file,
        na_values=None,
        keep_default_na=False,
        header=17,
    ).to_dict(orient="records")
    os.remove("./ostatki.xls")  # Удалить файл
    return watch_remnants


def create_stocks(watch_remnants, offer_ids):
    """Создать список остатков

    Args:
        watch_remnants (list): список остатков
        offer_ids (list): список артикулов

    Returns:
        list: список остатков
    example:
        >>> create_stocks(watch_remnants, offer_ids)
        [{"offer_id": "123", "stock": 100}, {"offer_id": "456", "stock": 0}]
        >>> create_stocks([], [])
        []
    """

    # Уберем то, что не загружено в seller
    stocks = []
    for watch in watch_remnants:
        if str(watch.get("Код")) in offer_ids:
            count = str(watch.get("Количество"))
            if count == ">10":
                stock = 100
            elif count == "1":
                stock = 0
            else:
                stock = int(watch.get("Количество"))
            stocks.append({"offer_id": str(watch.get("Код")), "stock": stock})
            offer_ids.remove(str(watch.get("Код")))
    # Добавим недостающее из загруженного:
    for offer_id in offer_ids:
        stocks.append({"offer_id": offer_id, "stock": 0})
    return stocks


def create_prices(watch_remnants, offer_ids):
    """Создать список цен

    Args:
        watch_remnants (list): список остатков 
        offer_ids (list): список артикулов

    Returns:
        list: список цен, например: [100,200,300,...]
    Examples:
        >>> create_prices(watch_remnants, offer_ids)
        [100,200,300,...]
        >>> create_prices([], [])
        []  
        >>> create_prices(watch_remnants, [])
        []
        >>> create_prices([], offer_ids)
        []  

    """

    prices = []
    for watch in watch_remnants:
        if str(watch.get("Код")) in offer_ids:
            price = {
                "auto_action_enabled": "UNKNOWN",
                "currency_code": "RUB",
                "offer_id": str(watch.get("Код")),
                "old_price": "0",
                "price": price_conversion(watch.get("Цена")),
            }
            prices.append(price)
    return prices


def price_conversion(price: str) -> str:
    """Сonverse the price 

    Args: 
        price: "5990.00"
    Returns: 
        "5990" 
    Examples:
        >>> price_conversion("5'990.00 руб.")
        '5990'

        >>> price_conversion("4,999.50")
        '4999'

        >>> price_conversion("10,00.99 руб.")
        '1000'

        >>> price_conversion("abc")
        ''
     """

    return re.sub("[^0-9]", "", price.split(".")[0])


def divide(lst: list, n: int):
    """Разделить список 

    Args:
        lst (list): список товаров 
        n (int): количество товаров в одном запросе

    Yields:
        list: список товаров 
    Examples:
        >>> divide([1,2,3,4,5], 2)
        [[1,2], [3,4], [5]]
        >>> divide([1,2,3,4,5], 3)
        [[1,2,3], [4,5]]
        >>> divide([], 2)
        []
    """

    for i in range(0, len(lst), n):
        yield lst[i: i + n]


async def upload_prices(watch_remnants, client_id, seller_token):
    """Загрузить цены 

    Args:
        watch_remnants (list): список остатков
        client_id (str): идентификатор клиента
        seller_token (str): токен продавца

    Returns:
        list: список цен
    Examples:
        >>> upload_prices(watch_remnants, client_id, seller_token)
        [{"offer_id": "123", "price": 100}, {"offer_id": "456", "price": 0}]
        >>> upload_prices([], client_id, seller_token)
        []
    """

    offer_ids = get_offer_ids(client_id, seller_token)
    prices = create_prices(watch_remnants, offer_ids)
    for some_price in list(divide(prices, 1000)):
        update_price(some_price, client_id, seller_token)
    return prices


async def upload_stocks(watch_remnants, client_id, seller_token):
    """Загрузить остатки

    Args:
        watch_remnants (list): список остаков товаров
        client_id (str): идентификатор клиента
        seller_token (str): токен продавца

    Returns:
        list: список остатков
    Examples:
        >>> upload_stocks(watch_remnants, client_id, seller_token)
        [{"offer_id": "123", "stock": 100}, {"offer_id": "456", "stock": 0}]
        >>> upload_stocks([], client_id, seller_token)
        []  

    """
    offer_ids = get_offer_ids(client_id, seller_token)
    stocks = create_stocks(watch_remnants, offer_ids)
    for some_stock in list(divide(stocks, 100)):
        update_stocks(some_stock, client_id, seller_token)
    not_empty = list(filter(lambda stock: (stock.get("stock") != 0), stocks))
    return not_empty, stocks


def main():
    """Главная функция"""
    env = Env()
    seller_token = env.str("SELLER_TOKEN")
    client_id = env.str("CLIENT_ID")
    try:
        offer_ids = get_offer_ids(client_id, seller_token)
        watch_remnants = download_stock()
        # Обновить остатки
        stocks = create_stocks(watch_remnants, offer_ids)
        for some_stock in list(divide(stocks, 100)):
            update_stocks(some_stock, client_id, seller_token)
        # Поменять цены
        prices = create_prices(watch_remnants, offer_ids)
        for some_price in list(divide(prices, 900)):
            update_price(some_price, client_id, seller_token)
    except requests.exceptions.ReadTimeout:
        print("Превышено время ожидания...")
    except requests.exceptions.ConnectionError as error:
        print(error, "Ошибка соединения")
    except Exception as error:
        print(error, "ERROR_2")


if __name__ == "__main__":
    main()
