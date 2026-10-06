import logging
import random
import time
import warnings
import re
from datetime import date as date_type, timedelta
from urllib.parse import urljoin

import requests
import schedule
from bs4 import BeautifulSoup, GuessedAtParserWarning

from .database import NEWS_SCHEMA, get_connection

warnings.filterwarnings('ignore', category=GuessedAtParserWarning)

PATTERN_OUT = "%d.%m.%y"
REQUEST_TIMEOUT = 20
RUSSIAN_MONTHS = {
    'января': 1, 'янв': 1,
    'февраля': 2, 'фев': 2,
    'марта': 3, 'мар': 3,
    'апреля': 4, 'апр': 4,
    'мая': 5, 'май': 5,
    'июня': 6, 'июн': 6,
    'июля': 7, 'июл': 7,
    'августа': 8, 'авг': 8,
    'сентября': 9, 'сентябрь': 9, 'сен': 9, 'сент': 9,
    'октября': 10, 'октябрь': 10, 'окт': 10,
    'ноября': 11, 'ноябрь': 11, 'ноя': 11,
    'декабря': 12, 'декабрь': 12, 'дек': 12,
}
logger = logging.getLogger(__name__)
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0'}


def fetch_soup(url):
    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return BeautifulSoup(response.text, 'lxml')


def parse_published_date(value):
    if not value:
        return None

    text = ' '.join(value.split()).lower().replace('\xa0', ' ')
    numeric_date = re.search(r'\b(\d{1,2})[./](\d{1,2})[./](\d{2,4})\b', text)
    if numeric_date:
        day, month, year = map(int, numeric_date.groups())
        if year < 100:
            year += 2000
        try:
            return date_type(year, month, day).strftime(PATTERN_OUT)
        except ValueError:
            return None

    russian_date = re.search(
        r'\b(\d{1,2})\s+([а-яё]+)(?:\s+(\d{4}))?\b',
        text
    )
    if not russian_date:
        return None

    day, month_name, year_text = russian_date.groups()
    month = RUSSIAN_MONTHS.get(month_name)
    if month is None:
        return None

    today = date_type.today()
    year = int(year_text) if year_text else today.year
    try:
        published = date_type(year, month, int(day))
    except ValueError:
        return None
    if not year_text and published > today + timedelta(days=31):
        published = date_type(year - 1, month, int(day))
    return published.strftime(PATTERN_OUT)


def update_existing_news_date(title, university_name, published_date):
    if published_date is None:
        return
    with get_connection(NEWS_SCHEMA) as connection:
        connection.execute(
            'UPDATE posts SET news_date = %s WHERE university_name = %s AND TRIM(news_title) = %s;',
            (published_date, university_name, title.strip())
        )


def news_exists(title, university_name):
    with get_connection(NEWS_SCHEMA) as connection:
        row = connection.execute(
            'SELECT 1 FROM posts WHERE university_name = %s AND TRIM(news_title) = %s LIMIT 1;',
            (university_name, title.strip())
        ).fetchone()
    return row is not None


def existing_article_is_empty(title, university_name):
    with get_connection(NEWS_SCHEMA) as connection:
        row = connection.execute(
            'SELECT news_text FROM posts WHERE university_name = %s AND TRIM(news_title) = %s LIMIT 1;',
            (university_name, title.strip())
        ).fetchone()
    return row is not None and not (row[0] or '').strip()


def image_url(item, base_url):
    image = item.find('img')
    if image is None:
        return None
    source = image.get('data-src') or image.get('src')
    return urljoin(base_url, source) if source else None


def extract_article_text(article):
    if article is None:
        return ''

    for unwanted in article.select('script, style, noscript'):
        unwanted.decompose()

    content_blocks = article.find_all(['p', 'li', 'blockquote', 'h2', 'h3', 'h4', 'h5', 'h6'])
    paragraphs = []
    for block in content_blocks:
        if block.name in {'li', 'blockquote'} and block.find(['p', 'li', 'blockquote']):
            continue
        text = block.get_text(' ', strip=True)
        text = re.sub(r'\s+([,.;:!?%»])', r'\1', text)
        text = re.sub(r'([«([{])\s+', r'\1', text)
        if text and (not paragraphs or text != paragraphs[-1]):
            paragraphs.append(text)

    if not paragraphs:
        text = article.get_text('\n', strip=True)
        return '\n'.join(line.strip() for line in text.splitlines() if line.strip())
    return '\n'.join(paragraphs)


def NewsDump(currentArticle, title, university_name, img_url, published_date):
    title = title.strip()
    if not title:
        logger.warning('Skipping article with an empty title from %s', university_name)
        return
    if published_date is None:
        logger.warning('Skipping %r from %s: publication date was not found', title, university_name)
        return
    if currentArticle is None:
        logger.warning('Skipping %r from %s: article body was not found', title, university_name)
        return

    article_text = extract_article_text(currentArticle)
    if not article_text:
        logger.warning('Skipping %r from %s: article contains no paragraph text', title, university_name)
        return

    with get_connection(NEWS_SCHEMA) as connection:
        existing = connection.execute(
            'SELECT id, news_text FROM posts WHERE university_name = %s AND TRIM(news_title) = %s LIMIT 1;',
            (university_name, title)
        ).fetchone()
        if existing is not None:
            if len((existing[1] or '').strip()) >= len(article_text.strip()):
                return
            connection.execute(
                'UPDATE posts SET news_text = %s, news_date = %s WHERE id = %s;',
                (article_text, published_date, existing[0])
            )
            logger.info('Repaired truncated article %r from %s', title, university_name)
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

    with get_connection(NEWS_SCHEMA) as connection:
        connection.execute(
            'INSERT INTO posts (news_title, news_text, university_name, news_date, news_img, deleted) '
            'VALUES (%s, %s, %s, %s, %s, %s);',
            (title, article_text, university_name, published_date, img, 0)
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
        date_element = item.find('p', class_='meta')
        published_date = parse_published_date(date_element.get_text(' ', strip=True) if date_element else None)
        if title and news_exists(title, university_name):
            update_existing_news_date(title, university_name, published_date)
            if not existing_article_is_empty(title, university_name):
                continue
        if link is None:
            continue
        time.sleep(random.randint(1, 3))
        article = fetch_soup(urljoin(url, link['href']))
        article_body = article.find('div', class_='news-single')
        heading = article.find('h2', class_='text-center')
        title = heading.get_text(' ', strip=True) if heading else title
        article_date = article.find('div', class_='date')
        published_date = parse_published_date(
            article_date.get_text(' ', strip=True) if article_date else None
        ) or published_date
        NewsDump(article_body, title, university_name, image_url(item, url), published_date)


def MAI_check():
    url = "https://mai.ru/press/news/"
    block = fetch_soup(url).select('div.col-sm-6.col-lg-6.mb-3.mb-lg-5')
    university_name = 'МАИ'

    for item in block:
        title_element = item.find('h5')
        title = title_element.get_text(' ', strip=True) if title_element else ''
        date_element = item.select_one('.badge')
        published_date = parse_published_date(date_element.get_text(' ', strip=True) if date_element else None)
        if title and news_exists(title, university_name):
            update_existing_news_date(title, university_name, published_date)
            if not existing_article_is_empty(title, university_name):
                continue
        link = item.find('a', class_='card-transition', href=True)
        if link is None:
            continue
        time.sleep(random.randint(1, 3))
        article = fetch_soup(urljoin(url, link['href']))
        article_body = article.find('article', itemprop='articleBody')
        heading = article.find('h1')
        title = heading.get_text(' ', strip=True) if heading else title
        article_date = article.select_one('span.d-block.small.mb-4.text-muted')
        published_date = parse_published_date(
            article_date.get_text(' ', strip=True) if article_date else None
        ) or published_date
        NewsDump(article_body, title, university_name, image_url(item, url), published_date)


def Baum_check():
    url = "https://kf.bmstu.ru/news"
    block = fetch_soup(url).select('div.l-news-list-col.col-12.col-md-4')
    university_name = 'МГТУ им. Баумана'
    for item in block:
        title_element = item.find('span', class_='l-news-title')
        title = title_element.get_text(' ', strip=True) if title_element else ''
        date_element = item.find('span', class_='l-news-date')
        published_date = parse_published_date(date_element.get_text(' ', strip=True) if date_element else None)
        if title and news_exists(title, university_name):
            update_existing_news_date(title, university_name, published_date)
            if not existing_article_is_empty(title, university_name):
                continue
        link = item.find('a', class_='l-news-element', href=True)
        if link is None:
            continue
        time.sleep(random.randint(1, 3))
        article = fetch_soup(urljoin(url, link['href']))
        article_body = article.find('div', class_='l-typography-text')
        heading = article.find('h1')
        title = heading.get_text(' ', strip=True) if heading else title
        NewsDump(article_body, title, university_name, image_url(item, url), published_date)


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
        content = item.find('div', class_='news-block-content')
        published_date = parse_published_date(content.get_text(' ', strip=True) if content else None)
        if title and news_exists(title, university_name):
            update_existing_news_date(title, university_name, published_date)
            if not existing_article_is_empty(title, university_name):
                continue
        time.sleep(random.randint(1, 3))
        article = fetch_soup(urljoin(url, link['href']))
        article_body = article.select_one('.news-item-text')
        heading = article.find('h1')
        title = heading.get_text(' ', strip=True) if heading else title
        article_date = article.select_one('.news-item-text .uk-margin-bottom')
        published_date = parse_published_date(
            article_date.get_text(' ', strip=True) if article_date else None
        ) or published_date
        NewsDump(article_body, title, university_name, image_url(item, url), published_date)


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
