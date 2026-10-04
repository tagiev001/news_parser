import logging
import random
import sqlite3
import time
import warnings
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
import schedule
from bs4 import BeautifulSoup, GuessedAtParserWarning

warnings.filterwarnings('ignore', category=GuessedAtParserWarning)

PATTERN_OUT = "%d.%m.%y"
DATABASE_PATH = Path(__file__).resolve().with_name('parced_news.db')
REQUEST_TIMEOUT = 20
logger = logging.getLogger(__name__)
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0'}


def fetch_soup(url):
    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return BeautifulSoup(response.text, 'lxml')


def news_exists(title, university_name):
    with sqlite3.connect(DATABASE_PATH) as connection:
        row = connection.execute(
            'SELECT 1 FROM Posts WHERE university_name = ? AND TRIM(news_title) = ? LIMIT 1;',
            (university_name, title.strip())
        ).fetchone()
    return row is not None


def image_url(item, base_url):
    image = item.find('img')
    if image is None:
        return None
    source = image.get('data-src') or image.get('src')
    return urljoin(base_url, source) if source else None


def NewsDump(currentArticle, title, university_name, img_url):
    title = title.strip()
    if not title:
        logger.warning('Skipping article with an empty title from %s', university_name)
        return
    if news_exists(title, university_name):
        return
    if currentArticle is None:
        logger.warning('Skipping %r from %s: article body was not found', title, university_name)
        return

    paragraphs = [
        paragraph.get_text(' ', strip=True)
        for paragraph in currentArticle.find_all('p')
        if paragraph.get_text(' ', strip=True)
    ]
    article_text = '\n'.join(paragraphs)
    if not article_text:
        logger.warning('Skipping %r from %s: article contains no paragraph text', title, university_name)
        return

    img = None
    if img_url:
        time.sleep(random.randint(1, 3))
        try:
            response = requests.get(img_url, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            img = response.content
        except requests.RequestException:
            logger.exception('Could not download image for %r from %s', title, university_name)

    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            'INSERT INTO Posts (news_title, news_text, university_name, news_date, news_img, deleted) '
            'VALUES (?, ?, ?, ?, ?, ?);',
            (title, article_text, university_name, datetime.today().strftime(PATTERN_OUT), img, 0)
        )
    logger.info('Saved article %r from %s', title, university_name)


def MTUCI_check():
    url = 'https://mtuci.ru/about_the_university/news/'
    block = fetch_soup(url).select('.news-list__item, .news-list__first-item')
    university_name = 'МТУСИ'

    for item in block:
        title_element = item.find('p', class_='title')
        link = item.find('a', href=True, string=True)
        title = title_element.get_text(' ', strip=True) if title_element else (
            link.get_text(' ', strip=True) if link else ''
        )
        if title and news_exists(title, university_name):
            continue
        if link is None:
            continue
        time.sleep(random.randint(1, 3))
        article = fetch_soup(urljoin(url, link['href']))
        article_body = article.find('div', class_='news-single')
        heading = article.find('h2', class_='text-center')
        title = heading.get_text(' ', strip=True) if heading else title
        NewsDump(article_body, title, university_name, image_url(item, url))


def MAI_check():
    url = "https://mai.ru/press/news/"
    block = fetch_soup(url).select('div.col-sm-6.col-lg-6.mb-3.mb-lg-5')
    university_name = 'МАИ'

    for item in block:
        title_element = item.find('h5')
        title = title_element.get_text(' ', strip=True) if title_element else ''
        if title and news_exists(title, university_name):
            continue
        link = item.find('a', class_='card-transition', href=True)
        if link is None:
            continue
        time.sleep(random.randint(1, 3))
        article = fetch_soup(urljoin(url, link['href']))
        article_body = article.find('article', itemprop='articleBody')
        heading = article.find('h1')
        title = heading.get_text(' ', strip=True) if heading else title
        NewsDump(article_body, title, university_name, image_url(item, url))


def Baum_check():
    url = "https://kf.bmstu.ru/news"
    block = fetch_soup(url).select('div.l-news-list-col.col-12.col-md-4')
    university_name = 'МГТУ им. Баумана'
    for item in block:
        title_element = item.find('span', class_='l-news-title')
        title = title_element.get_text(' ', strip=True) if title_element else ''
        if title and news_exists(title, university_name):
            continue
        link = item.find('a', class_='l-news-element', href=True)
        if link is None:
            continue
        time.sleep(random.randint(1, 3))
        article = fetch_soup(urljoin(url, link['href']))
        article_body = article.find('div', class_='l-typography-text')
        heading = article.find('h1')
        title = heading.get_text(' ', strip=True) if heading else title
        NewsDump(article_body, title, university_name, image_url(item, url))


def MIREA_check():
    url = 'https://www.mirea.ru/news/'
    listing = fetch_soup(url)
    block = listing.select('a.news-block-slider-grid__item[href]')
    if not block:
        block = listing.select('div.uk-card.uk-card-default')
    university_name = 'МИРЭА'
    for item in block:
        link = item if item.name == 'a' and item.get('href') else item.find('a', href=True)
        if link is None:
            continue
        title_element = item.find('div', class_='events-block-body') or item.find('a', class_='uk-link-reset')
        title = (
            item.get('title')
            or (title_element.get_text(' ', strip=True) if title_element else '')
        )
        if title and news_exists(title, university_name):
            continue
        time.sleep(random.randint(1, 3))
        article = fetch_soup(urljoin(url, link['href']))
        article_body = article.select_one('.news-item-text')
        heading = article.find('h1')
        title = heading.get_text(' ', strip=True) if heading else title
        NewsDump(article_body, title, university_name, image_url(item, url))


def news_check():
    for check in (MTUCI_check, MAI_check, Baum_check, MIREA_check):
        try:
            check()
        except Exception:
            logger.exception('News check failed: %s', check.__name__)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    news_check()
    schedule.every().hour.do(news_check)

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == '__main__':
    main()
