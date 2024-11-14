import datetime
import time

from s3p_sdk.plugin.payloads.parsers import S3PParserBase
from s3p_sdk.types import S3PRefer, S3PDocument
from selenium.common import NoSuchElementException
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

import dateutil.parser

class NIST(S3PParserBase):
    """
    Класс парсера плагина SPP

    :warning Все необходимое для работы парсера должно находится внутри этого класса

    :_content_document: Это список объектов документа. При старте класса этот список должен обнулиться,
                        а затем по мере обработки источника - заполняться.


    """
    SOURCE_NAME = 'nist'
    NEWS_TYPE: str = 'NEWS'
    PUBLICATION_TYPE: str = 'PUBS'


    def __init__(self, refer: S3PRefer, web_driver: WebDriver, url: str, max_count_documents: int = None,
                 last_document: S3PDocument = None):
        super().__init__(refer, max_count_documents, last_document)

        self._driver = web_driver
        self._wait = WebDriverWait(self._driver, timeout=20)
        self._max_count_documents = max_count_documents
        self._last_document = last_document
        if url:
            self.URL = url
            if 'news-events' in self.URL:
                self.TYPE = self.NEWS_TYPE
            elif 'publications' in self.URL:
                self.TYPE = self.PUBLICATION_TYPE
            else:
                raise ValueError('unknown document types in provided url (not news or publications)')
        else:
            raise ValueError('url must be a link to the swift topic main page')

        # self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.debug(f"Parser class init completed")
        self.logger.info(f"Set source: {self.SOURCE_NAME}")

        # функции обработки материалов разного типа
        self._parse_func_enum: dict[str, Callable] = {
            self.NEWS_TYPE: self._parse_news,
            self.PUBLICATION_TYPE: self._parse_pubs
        }

    def _parse(self):
        """
        Метод, занимающийся парсингом. Он добавляет в _content_document документы, которые получилось обработать
        :return:
        :rtype:
        """
        self.logger.debug(F"Parser enter to {self.URL}")

        for page_link in self._encounter_pages():
            # получение URL новой страницы
            for link in self._collect_doc_links(page_link):
                # парсинг материала
                doc = self._parse_func_enum.get(self.TYPE)(link)
                self._find(doc)

    def _parse_news(self, url: str) -> S3PDocument:
        doc = self._page_init(url)

        try:
            abstract = self._driver.find_element(By.XPATH, '//*[contains(@class, \'nist-block\')]/h3').text
        except Exception as e:
            self.logger.debug('Empty abstract. Error: ' + str(e))
        else:
            doc.abstract = abstract

        doc.link = url
        doc.text = self._driver.find_element(By.CLASS_NAME, 'text-with-summary').text
        return doc

    def _parse_pubs(self, url: str) -> S3PDocument:
        doc = self._page_init(url)

        try:
            abstract = self._driver.find_element(By.CLASS_NAME, 'text-with-summary').text
        except Exception as e:
            self.logger.debug('Empty abstract. Error: '+str(e))
        else:
            doc.abstract = abstract

        try:
            author = [auth.text for auth in self._driver.find_elements(By.CLASS_NAME, 'nist-author')]
        except Exception as e:
            self.logger.debug('Empty author. Error: '+str(e))
        else:
            doc.other['author'] = author

        try:
            pdf_link = self._driver.find_element(By.XPATH, '//a[contains(text(), \'doi\')]').get_attribute(
                'href')
            self._driver.get(pdf_link)
            time.sleep(0.5)

            doc_link = self._driver.current_url
            if not self._driver.current_url.endswith('.pdf'):
                self.logger.debug('Publication doesn\'t have open pdf')
        except Exception as e:
            self.logger.debug('Empty doi link => web_link = doc_link (NIST pub page). Error: ' + str(e))
            doc.link = url
        else:
            doc.link = doc_link

        return doc

    def _page_init(self, url: str) -> S3PDocument:
        self._initial_access_source(url)
        self._wait.until(ec.presence_of_element_located((By.CSS_SELECTOR, '.nist-page__title')))
        title = self._driver.find_element(By.CLASS_NAME, 'nist-page__title').text
        pub_date = dateutil.parser.parse(
            self._driver.find_element(By.TAG_NAME, 'time').get_attribute('datetime'))
        tags = self._driver.find_element(By.CLASS_NAME, 'nist-tags').text
        return S3PDocument(
            id=None,
            title=title,
            abstract=None,
            text=None,
            link=url,
            storage=None,
            other={'tags': tags},
            published=pub_date,
            loaded=datetime.datetime.now()
        )

    def _encounter_pages(self) -> str:
        """
        Формирование ссылки для обхода всех страниц
        """
        _base = self.URL
        _param = f'&page='
        page = 0
        while True:
            url = str(_base) + _param + str(page)
            page += 1
            yield url

    def _collect_doc_links(self, _url: str) -> list[str]:
        """
        Формирование списка ссылок на материалы страницы
        """
        try:
            self._initial_access_source(_url)
            self._wait.until(ec.presence_of_all_elements_located((By.CLASS_NAME, 'nist-teaser')))
        except Exception as e:
            raise NoSuchElementException() from e
        links = []

        try:
            articles = self._driver.find_elements(By.CLASS_NAME, 'nist-teaser')
        except Exception as e:
            raise NoSuchElementException('list is empty') from e
        else:
            for article in articles:
                try:
                    doc_link = article.find_element(By.TAG_NAME, 'a').get_attribute('href')
                except Exception as e:
                    raise NoSuchElementException(
                        'Страница не открывается или ошибка получения обязательных полей') from e
                else:
                    links.append(doc_link)
        return links

    def _initial_access_source(self, url: str, delay: int = 2):
        self._driver.get(url)
        self.logger.debug('Entered on web page ' + url)
        time.sleep(delay)

