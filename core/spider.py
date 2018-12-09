import requests as rlib
import urllib.parse
import logging
from bs4 import BeautifulSoup
import socket
from threading import Thread, RLock, get_ident
import time
import json
import re
import os
from core.boiler import BoilerWithShingle
from tqdm import tqdm
import ZODB
import ZODB.config
import transaction

import BTrees.OOBTree
import ZODB.FileStorage

db = ZODB.config.databaseFromURL('zeo.xml')

connection = db.open()
root = connection.root

root.bags = BTrees.OOBTree.BTree()
root.visited = BTrees.OOBTree.BTree()
root.index = BTrees.OOBTree.BTree()

transaction.commit()

dirs_to_create = ["root", "normal_text", "html", "logs", "logs/spiders"]
for i in dirs_to_create:
    if not os.path.exists(i):
        os.makedirs(i)


class Crawler(Thread):
    """
    Main Crawler Class

    """
    save_freq = 15  # AutoSave interval

    debug = True
    delay = 0.05
    max_depth = 32
    timeout = 1.0
    max_attempts = 1

    repeat_start_time = 60
    repeat_max_time = 60*60
    delta = 2

    def __init__(self, runner, init_url, anchor='*'):
        super().__init__(target=self.run)

        self.runner = runner
        self.init_url = init_url
        self.anchor = anchor
        self.bid = str(get_ident())
        root.bags["ubag-"+self.bid] = [self.init_url]
        self.disallow = set()
        self.running = True

        self.logger = logging.getLogger("neutron.spider")
        self.logger.setLevel(logging.DEBUG)

        # create the logging file handler
        fh = logging.FileHandler("logs/spiders/n_spider.log")

        formatter = logging.Formatter('%(asctime)s - %(name)s - %(thread)d - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)

        # add handler to logger object
        self.logger.addHandler(fh)
        transaction.commit()
    def run(self): #Crawler Start
        try:
            self.go(self.max_depth)
        except Exception as ex:
            if str(ex) != 'Stop':
                self.runner.remove(self)
        else:
            self.runner.remove(self)

    def stop(self):
        self.running = False

    def get_url(self, url, href):
        # TODO: Schema Checks. Provide plugins for unknown schemas
        combined_url = urllib.parse.urljoin(url, href).split('?')[0].split('#')[0]
        s = urllib.parse.urlparse(combined_url)
        if s.netloc in self.runner.restricted_hosts:
            return
        if s.netloc == self.anchor or s.netloc.endswith(urllib.parse.urlparse(self.init_url).netloc):
            return combined_url
        if self.anchor == '*':
            #Adding new crawlers for another domains
            self.runner.lock.acquire()
            self.runner.add(Crawler(self.runner, combined_url))
            self.runner.lock.release()

    def get_disallow(self):
        if not self.get_url(self.init_url, 'robots.txt'):
            return
        try:
            
            robots = rlib.get(self.get_url(self.init_url, 'robots.txt')).text.split('\n')
            robots.raise_for_status()
            for rule in robots:
                if 'Disallow:' in rule:
                    disallow = rule.split(': ')[1]
                    self.disallow.add(self.get_url(self.init_url, disallow))
        except (rlib.exceptions.HTTPError, socket.timeout, IndexError):
            pass

    def fetch(self, url): # LinkSearch
        for _ in range(self.max_attempts):
            try:
                response = rlib.get(url)
                response.raise_for_status()
                doc_structure = BeautifulSoup(response.text, "lxml")
                children_urls = []
                for link in doc_structure.findAll('a'):
                    try:
                        static_url = self.get_url(url, link['href'])
                        if static_url:
                            children_urls.append(static_url)
                    except KeyError:
                        pass

                break
            except (rlib.exceptions.HTTPError, socket.timeout, UnicodeEncodeError) as e:
                self.runner.pbar.write("FUCK!!!!")
                self.runner.pbar.write(str(e))
                self.logger.error(str(e))
                return False, '', list()
        else:
            self.runner.pbar.write("FUCK!!!!")
            return False, '', list()
        return True, response.text, children_urls # Note1: status, html-document, urls. TODO: Status to INT

    def go(self, current_depth):
        if current_depth <= 0:
            return root.index["ind"]
        for i, url in enumerate(root.bags["ubag-"+self.bid].copy()):
            if not self.running:
                raise Exception('Stop')
            if url in root.visited["visited"] and len(root.bags["ubag-"+self.bid]) != 1:
                continue
            for dis in self.disallow:
                if re.findall(dis, url): # If url is permitted, passing it!
                    continue
            else:
                root.bags["ubag-"+self.bid].pop(i) #Deleting items from DB
                status, html, children_urls = self.fetch(url)
                if not status:
                    continue
                root.bags["ubag-"+self.bid] += children_urls
                """
                Commit to DB should be there! --^
                """

                transaction.commit()
                self.runner.lock.acquire()
                try:
                    ids = str(self.runner.id)
                    root.index["ind"][self.runner.id] = url
                    root.visited["visited"].add(url)
                    self.runner.id += 1

                    if not self.runner.id % self.save_freq and self.runner.id:  # AUTO-SAVE ENGINE
                        with open("index.json", "w") as ind:
                            json.dump(root.index["ind"], ind, indent=2)
                        with open('last_ind.tmp', 'w') as last:
                            last.write(str(self.runner.id - 1))
                except Exception as ex:
                    self.runner.pbar.write(ex)
                self.runner.lock.release()
                self.logger.info("Trying to write HTML...")
                try:
                  with open(os.path.join(self.runner.output_dir, str(ids)), "wb") as f:
                    f.write(html.encode())
                    self.logger.info("Success!")
                except BaseException as e:
                    self.logger.error("Failure( Logs: {}".format(e))
                    raise Exception("Fucking Exception")
                if self.debug:
                    self.runner.pbar.write("{0}\t{1}".format(ids, url))

                code = self.runner.boiler_engine.handle(self.runner.output_dir, self.runner.txt_dir, ids) 
                # *SOLVED*: By some reason, boilerpipe don't working --^
                if not code:
                    try:
                        root.index["ind"].pop(ids)
                    except IndexError as e:
                        self.runner.pbar.write(str(e))
                else:
                    self.runner.max_pages -= 1
                    self.runner.pbar.update(1)

                if self.runner.max_pages <= 0:
                    self.runner.stop()

                time.sleep(self.delay)
        if root.bags["ubag-"+self.bid]:
            self.go(current_depth - 1)
        return root.index["ind"]


class CrawlerRunner:
    """
    CrawlerRunner Class
    Run Spiders
    """
    max_crawlers = 16
    running = False
    restricted_hosts = ['youtube.com', '*.youtube.com']
    output_dir = 'html/'
    txt_dir = 'root/'

    max_pages = 10000

    def __init__(self):
        root.visited["visited"] = set()
        root.index["ind"] = {}
        self.id = 0
        self.lock = RLock()
        self.boiler_engine = BoilerWithShingle()
        self.pbar = tqdm(total=self.max_pages)
        self.spider_queue = []

        self.active_crawlers = [Crawler(self, 'https://lenta.ru/')]
        transaction.commit()
    def add(self, crawler):
        if len(self.active_crawlers) >= self.max_crawlers:
            self.spider_queue.append(crawler)
        else:
            self.active_crawlers.append(crawler)
            crawler.start()

    def remove(self, crawler):
        self.active_crawlers.remove(crawler)
        new_crawler = self.spider_queue.pop(0)
        self.active_crawlers.append(new_crawler)
        new_crawler.start()

    def start(self):
        for crawler in self.active_crawlers:
            crawler.start()
        print("Spider has started")
        self.running = True

    def stop(self):
        self.running = False
        for crawler in self.active_crawlers:
            crawler.stop()
        print('Spider has stopped')
        self.pbar.close()

    def get_info(self): # TODO
        return {
            "visited_links": list(root.visited["visited"])
               }

    def find_duplicates(self):
        self.boiler_engine.find(root.index["ind"])
