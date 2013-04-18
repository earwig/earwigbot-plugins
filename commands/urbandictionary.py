# -*- coding: utf-8  -*-
#
# Public domain, 2013 Legoktm
#

from json import loads
import re
from urllib import quote
from urllib2 import urlopen

from earwigbot.commands import Command

class UrbanDictionary(Command):
    """Get the definition of a word using Urban Dictionary."""
    name = "urban"
    commands = ["urban", "urbandictionary", "dictt", "definee", "defne", "dct",
                "ud"]

    def process(self, data):
        if not data.args:
            self.reply(data, "What do you want to define?")
            return

        url = "http://api.urbandictionary.com/v0/define?term={0}"
        q = quote(' '.join(data.args), safe="")
        query = urlopen(url.format(q)).read()
        res = loads(query)
        if res['result_type'] == 'exact':
            definition = re.sub(r"\s+", " ", res['list'][0]['definition'])
            example = re.sub(r"\s+", " ", res['list'][0]['example'])
            msg = '{0}; example: {1}'.format(definition, example)
            self.reply(data, msg)
        elif res['result_type'] == 'fulltext':
            L = [i['word'] for i in res['list']]
            msg = 'Here are some close matches: {0}.'.format(', '.join(L))
            self.reply(data, msg)
        else:
            self.reply(data, 'Sorry, no results found.')
