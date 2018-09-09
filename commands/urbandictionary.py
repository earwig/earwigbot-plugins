# -*- coding: utf-8  -*-
#
# Public domain, 2013 Legoktm; 2013, 2018 Ben Kurtovic
#

from json import loads
import re
from urllib import quote
from urllib2 import urlopen

from earwigbot.commands import Command

class UrbanDictionary(Command):
    """Get the definition of a word or phrase using Urban Dictionary."""
    name = "urban"
    commands = ["urban", "urbandictionary", "dct", "ud"]

    @staticmethod
    def _normalize(word):
        return re.sub(r"\W", "", word.lower())

    def process(self, data):
        if not data.args:
            self.reply(data, "What do you want to define?")
            return

        url = "http://api.urbandictionary.com/v0/define?term={0}"
        arg = " ".join(data.args)
        query = urlopen(url.format(quote(arg, safe=""))).read()
        res = loads(query)
        results = res.get("list")
        if not results:
            self.reply(data, 'Sorry, no results found.')
            return

        result = results[0]
        definition = re.sub(r"\s+", " ", result["definition"])
        example = re.sub(r"\s+", " ", result["example"])
        url = result["permalink"].rsplit("/", 1)[0]
        if definition and definition[-1] not in (".", "!", "?"):
            definition += "."

        msg = "{0} \x02Example\x0F: {1} {2}".format(
            definition.encode("utf8"), example.encode("utf8"), url)
        if self._normalize(result["word"]) != self._normalize(arg):
            msg = "\x02{0}\x0F: {1}".format(result["word"].encode("utf8"), msg)

        self.reply(data, msg)
