# -*- coding: utf-8  -*-
#
# Public domain, 2013 Legoktm
#

from json import loads
from urllib import quote
from urllib2 import urlopen

from earwigbot.commands import Command

class UrbanDictionary(Command):
    """Get the real definition of a word."""
    name = "urban"
    commands = ["dictt", "definee", "defne", "dct", "ud"]

    def process(self, data):
        if not data.args:
            return
        q = ' '.join(data.args)

        url = "http://api.urbandictionary.com/v0/define?term={}"
        q = quote(q, safe="")
        query = urlopen(url.format(q)).read()
        res = loads(query)
        if res['result_type'] == 'exact':
            defin = res['list'][0]
            msg = 'Definition: {definition}; example: {example}'.format(**defin)
            self.reply(data, msg)
        elif res['result_type'] == 'fulltext':
            l = [i['word'] for i in res['list']]
            msg = 'Here are some close matches...: {0}'.format(', '.join(l))
            self.reply(data, msg)
        else:
            self.reply(data, 'Sorry, no results found :(')

