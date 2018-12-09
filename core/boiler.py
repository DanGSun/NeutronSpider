import os
import re
from tqdm import tqdm
from itertools import combinations
from math import factorial
import json
from core.words import extract_words, split
import logging
from selectolax.parser import HTMLParser
from bs4 import BeautifulSoup
from core.pyboiler import boil
boil_py = False

logger = logging.getLogger("neutron.boiler")
logger.setLevel(logging.DEBUG)

# create the logging file handler
fh = logging.FileHandler("logs/boiler.log")

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)

# add handler to logger object
logger.addHandler(fh)


def bs_parse_text(contents_string):
    new_lines = re.compile(r'[\r\n]\s+')
    bs = BeautifulSoup(contents_string, "lxml")
    for script in bs(["script", "style"]):
        script.extract()
    txt = bs.getText('\n')
    return new_lines.sub('\n', txt)


def sl_parse_text(html):
    tree = HTMLParser(html)

    if tree.body is None:
        return None

    for tag in tree.css('script'):
        tag.decompose()
    for tag in tree.css('style'):
        tag.decompose()

    text = tree.body.text(separator='\n')
    return text


def parse_text(contents_string, selectolax=True):
    if selectolax:
        sl_parse_text(contents_string)
    else:
        bs_parse_text(contents_string)


def shingle(text, n):
    res = set()
    for pos in range(len(text) - n):
        sh = text[pos:pos + n]
        res.add(sh)
    return res


def dist(a, b):
    return float(len(a.intersection(b))) / len(a.union(b))


def c_from_n(n, k):
    return factorial(n) // (factorial(k) * factorial(n - k))


class BoilerWithShingle:
    def __init__(self):
        self.doc_signatures = []
        self.deleted = []

    def handle(self, inp, out, index):

            new_name = os.path.join(out, index + '.txt')
            logger.debug("CMD: java -jar core/boiler.jar {0} > {1}".format(os.path.join(inp, index),
                                                                                new_name))
            code = os.system("java -jar core/boiler.jar {0} > {1}".format(os.path.join(inp, index),
                                                                                new_name))
            logger.debug("CODE: {}".format(code))
            with open(new_name, 'r', encoding='utf-8') as inp:
                text = inp.read()
                normal_text = extract_words(split(text))  # Extract there TODO: Extract replacement to selectolax
                with open(os.path.join('normal_text/', '{0}.txt'.format(index)), 'w', encoding='utf-8') as f:
                    f.write(' '.join(normal_text))
            if code:
                return False

            return self.add(index, out)

    def n_handle(self, text, outdir, index):
        new_name = os.path.join(outdir, index + '.txt')
        return self.add(index, outdir)

    def add(self, index, out='root/'):
        new_name = os.path.join(out, index + '.txt')
        with open(new_name, 'r', encoding='utf-8') as content_file:
            content = content_file.read()
            if not content.strip():
                return False
            text = parse_text(content)
            self.doc_signatures.append((new_name, shingle(text, 8), index))
        return True

    def find(self, index):
        i = 0
        for sgn1, sgn2 in tqdm(combinations(self.doc_signatures[::4], 2),
                               total=c_from_n(len(self.doc_signatures[::4]), 2)):
            i += 1
            if not i % 100000:
                with open('index.json', 'w') as f:
                    json.dump(index, f, indent=2)
            if sgn1[0] in self.deleted or sgn2[0] in self.deleted:
                continue
            if dist(sgn1[1], sgn2[1]) > 0.7:
                print(sgn1[0], sgn2[0] + ' removed')
                os.unlink(sgn2[0])
                self.deleted.append(sgn2[0])
                index.pop(sgn2[2])
        with open('index.json', 'w') as f:
            json.dump(index, f, indent=2)
