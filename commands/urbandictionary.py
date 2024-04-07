# Public domain, 2013 Legoktm; 2013, 2018 Ben Kurtovic

import re
from json import loads
from urllib.parse import quote
from urllib.request import urlopen

from earwigbot.commands import Command


class UrbanDictionary(Command):
    """Get the definition of a word or phrase using Urban Dictionary."""

    name = "urban"
    commands = ["urban", "urbandictionary", "dct", "ud"]

    @staticmethod
    def _normalize_term(term):
        return re.sub(r"\W", "", term.lower())

    @staticmethod
    def _normalize_text(text):
        return re.sub(r"\[(.*?)\]", "\\1", re.sub(r"\s+", " ", text))

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
            self.reply(data, "Sorry, no results found.")
            return

        result = results[0]
        definition = self._normalize_text(result["definition"])
        example = self._normalize_text(result["example"])
        url = result["permalink"].rsplit("/", 1)[0]
        if definition and definition[-1] not in (".", "!", "?"):
            definition += "."

        msg = "{} \x02Example\x0f: {} {}".format(
            definition.encode("utf8"), example.encode("utf8"), url
        )
        if self._normalize_term(result["word"]) != self._normalize_term(arg):
            msg = "\x02{}\x0f: {}".format(result["word"].encode("utf8"), msg)

        self.reply(data, msg)
