# -*- coding: utf-8  -*-
#
# Copyright (C) 2021 Ben Kurtovic <ben.kurtovic@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import difflib
import json
import re
import sqlite3
import subprocess
import time

import more_itertools
import mwparserfromhell
import unidecode

from earwigbot.tasks import Task

class SynonymAuthorities(Task):
    """
    Correct mismatched synonym authorities in taxon articles created by Qbugbot.
    """
    name = 'synonym_authorities'
    number = 21
    base_summary = (
        'Fix {changes} mismatched synonym authorities per ITIS '
        '([[Wikipedia:Bots/Requests for approval/EarwigBot 21|more info]])'
    )

    def setup(self):
        self.site = self.bot.wiki.get_site()
        self.creator = 'Qbugbot'
        self.pages_path = 'qbugbot_pages.json'
        self.synonyms_path = 'qbugbot_synonyms.json'
        self.edits_path = 'qbugbot_edits.json'
        self.itis_path = 'itis.db'
        self.summary = self.make_summary(self.base_summary)

    def run(self, action=None):
        if action == 'fetch_pages':
            self.fetch_pages()
        elif action == 'fetch_synonyms':
            self.fetch_synonyms()
        elif action == 'prepare_edits':
            self.prepare_edits()
        elif action == 'view_edits':
            self.view_edits()
        elif action == 'save_edits':
            self.save_edits()
        elif action is None:
            raise RuntimeError(f'This task requires an action')
        else:
            raise RuntimeError(f'No such action: {action}')

    def fetch_pages(self):
        """
        Fetch pages edited by Qbugbot.
        """
        pages = {}
        for chunk in more_itertools.chunked(self._iter_creations(), 500):
            pages.update(self._fetch_chunk(chunk))

        self.logger.info(f'Fetched {len(pages)} pages')
        with open(self.pages_path, 'w') as fp:
            json.dump(pages, fp)

    def _iter_creations(self):
        # TODO: include converted redirects ([[Category:Articles created by Qbugbot]])
        params = {
            'action': 'query',
            'list': 'usercontribs',
            'ucuser': self.creator,
            'uclimit': 5000,
            'ucnamespace': 0,
            'ucprop': 'ids',
            'ucshow': 'new',
            'formatversion': 2,
        }

        results = self.site.api_query(**params)
        while contribs := results['query']['usercontribs']:
            yield from contribs
            if 'continue' not in results:
                break
            params.update(results['continue'])
            results = self.site.api_query(**params)

    def _fetch_chunk(self, chunk):
        result = self.site.api_query(
            action='query',
            prop='revisions',
            rvprop='ids|content',
            rvslots='main',
            pageids='|'.join(str(page['pageid']) for page in chunk),
            formatversion=2,
        )

        pages = result['query']['pages']
        assert len(pages) == len(chunk)

        return {
            page['pageid']: {
                'title': page['title'],
                'content': page['revisions'][0]['slots']['main']['content'],
                'revid': page['revisions'][0]['revid'],
            }
            for page in pages
        }

    def fetch_synonyms(self):
        """
        Fetch correct synonym lists for pages generated by fetch_pages.
        """
        with open(self.pages_path) as fp:
            pages = json.load(fp)
        wikidata = self.bot.wiki.get_site('wikidatawiki')
        itis_property = 'P815'
        conn = sqlite3.connect(self.itis_path)
        cur = conn.cursor()

        synonyms = {}
        for chunk in more_itertools.chunked(pages.items(), 50):
            titles = {page['title']: pageid for pageid, page in chunk}
            result = wikidata.api_query(
                action='wbgetentities',
                sites='enwiki',
                titles='|'.join(titles),
                props='claims|sitelinks',
                languages='en',
                sitefilter='enwiki',
            )

            for item in result['entities'].values():
                if 'sitelinks' not in item:
                    self.logger.warning(f'No sitelinks for item: {item}')
                    continue
                title = item['sitelinks']['enwiki']['title']
                pageid = titles[title]
                if itis_property not in item['claims']:
                    self.logger.warning(f'No ITIS ID for [[{title}]]')
                    continue
                claims = item['claims'][itis_property]
                assert len(claims) == 1, (title, claims)
                itis_id = claims[0]['mainsnak']['datavalue']['value']

                cur.execute("""
                    SELECT synonym.complete_name, authors.taxon_author
                    FROM synonym_links sl
                    INNER JOIN taxonomic_units accepted ON sl.tsn_accepted = accepted.tsn
                    INNER JOIN taxonomic_units synonym ON sl.tsn = synonym.tsn
                    LEFT JOIN taxon_authors_lkp authors ON synonym.taxon_author_id = authors.taxon_author_id
                    WHERE sl.tsn_accepted = ?
                    UNION ALL
                    SELECT complete_name, taxon_author
                    FROM taxonomic_units accepted
                    LEFT JOIN taxon_authors_lkp authors USING (taxon_author_id)
                    WHERE accepted.tsn = ?;
                """, (itis_id, itis_id))
                synonyms[pageid] = cur.fetchall()

        self.logger.info(f'Fetched {len(synonyms)} synonym lists')
        with open(self.synonyms_path, 'w') as fp:
            json.dump(synonyms, fp)

    def prepare_edits(self):
        """
        Prepare edits based on the output of fetch_pages and fetch_synonyms.
        """
        with open(self.pages_path) as fp:
            pages = json.load(fp)
        with open(self.synonyms_path) as fp:
            synonyms = json.load(fp)

        edits = {}
        for pageid, pageinfo in pages.items():
            if pageid not in synonyms:
                continue
            wikitext = mwparserfromhell.parse(pageinfo['content'])
            try:
                changes = self._update_synonyms(pageinfo['title'], wikitext, synonyms[pageid])
                if not changes:
                    continue
            except Exception:
                self.logger.error(f'Failed to update synonyms for [[{pageinfo["title"]}]]')
                raise
            edits[pageid] = {
                'title': pageinfo['title'],
                'revid': pageinfo['revid'],
                'original': pageinfo['content'],
                'content': str(wikitext),
                'changes': changes,
            }

        with open(self.edits_path, 'w') as fp:
            json.dump(edits, fp)

    def _update_synonyms(self, title, wikitext, synonyms):
        if len(synonyms) <= 1:
            return False
        if wikitext.split('\n', 1)[0].upper().startswith('#REDIRECT'):
            self.logger.debug(f'[[{title}]]: Skipping redirect')
            return False

        taxoboxes = wikitext.filter_templates(
            matches=lambda tmpl: tmpl.name.matches(('Speciesbox', 'Automatic taxobox')))
        if not taxoboxes:
            self.logger.warning(f'[[{title}]]: No taxoboxes found')
            return False
        if len(taxoboxes) > 1:
            self.logger.warning(f'[[{title}]]: Multiple taxoboxes found')
            return False

        try:
            syn_param = taxoboxes[0].get('synonyms')
        except ValueError:
            self.logger.debug(f'[[{title}]]: No synonyms parameter in taxobox')
            return False

        tmpls = syn_param.value.filter_templates(
            matches=lambda tmpl: tmpl.name.matches(('Species list', 'Taxon list')))
        if not tmpls:
            # This means the bot's original work is no longer there. In most cases, this is
            # an unrelated synonym list added by another editor and there is nothing to check,
            # but it's possible someone converted the bot's list into a different format without
            # checking the authorities. Those cases need to be manually checked.
            self.logger.warning(f'[[{title}]]: Could not find a taxa list in taxobox')
            return False
        if len(tmpls) > 1:
            self.logger.warning(f'[[{title}]]: Multiple taxa lists found in taxobox')
            return False

        expected = {}
        for taxon, author in synonyms:
            if taxon in expected and expected[taxon] != author:
                # These need to be manually reviewed
                self.logger.warning(f'[[{title}]]: Expected synonym list has duplicates')
                return False
            expected[self._normalize(taxon)] = self._normalize(author)

        actual = {}
        formatted_authors = {}
        splist = tmpls[0]
        for i in range(len(splist.params) // 2):
            taxon_param, author_param = splist.params[2 * i], splist.params[2 * i + 1]
            taxon = self._normalize(taxon_param.value)
            author = self._normalize(author_param.value)
            if taxon not in expected:
                self.logger.warning(f'[[{title}]]: Unknown synonym {taxon!r}')
                return False
            actual[taxon] = author
            formatted_authors.setdefault(author, []).append(author_param.value.strip())

        expected = {taxon: author for taxon, author in expected.items() if taxon in actual}
        assert set(expected.keys()) == set(actual.keys())
        if expected == actual:
            self.logger.debug(f'[[{title}]]: Nothing to update')
            return None
        if list(expected.values()) != list(actual.values()):
            if set(expected.values()) == set(actual.values()):
                self.logger.warning(f'[[{title}]]: Actual authors are not in expected order')
            else:
                self.logger.warning(f'[[{title}]]: Actual authors do not match expected')
            return False

        changes = []
        for i in range(len(splist.params) // 2):
            taxon_param, author_param = splist.params[2 * i], splist.params[2 * i + 1]
            taxon = self._normalize(taxon_param.value)
            if expected[taxon] != actual[taxon]:
                author = formatted_authors[expected[taxon]].pop(0)
                match = re.match(r'^(\s*).*?(\s*)$', str(author_param.value))
                ws_before, ws_after = match.group(1), match.group(2)
                author_param.value = f'{ws_before}{author}{ws_after}'
                changes.append((taxon, actual[taxon], expected[taxon]))

        if changes:
            self.logger.info(f'Will update {len(changes)} synonyms in [[{title}]]')
        else:
            self.logger.debug(f'Nothing to update in [[{title}]]')
        return changes

    @staticmethod
    def _normalize(value):
        """
        Normalize a taxon or author name.
        """
        if isinstance(value, mwparserfromhell.wikicode.Wikicode):
            value = value.strip_code()
        if not value or not value.strip():
            return None
        return unidecode.unidecode(value.strip().casefold().replace('&', 'and').replace(',', ''))

    def view_edits(self):
        """
        Examine edits prepared by prepare_edits.
        """
        with open(self.edits_path) as fp:
            edits = json.load(fp)

        self.logger.info(f'{len(edits)} pages to edit')
        for pageid, edit in edits.items():
            print(f'\n{pageid}: {edit["title"]}:')
            old, new = edit['original'], edit['content']

            udiff = difflib.unified_diff(old.splitlines(), new.splitlines(), 'old', 'new')
            subprocess.run(
                ['delta', '-s', '--paging', 'never'],
                input='\n'.join(udiff), text=True
            )

    def save_edits(self):
        """
        Save edits prepared by prepare_edits.
        """
        with open(self.edits_path) as fp:
            edits = json.load(fp)

        self.logger.info(f'{len(edits)} pages to edit')
        for pageid, edit in edits.items():
            page = self.site.get_page(edit['title'])
            self.logger.info(f'{pageid}: [[{page.title}]]')

            if self.shutoff_enabled():
                raise RuntimeError('Shutoff enabled')
            if not page.check_exclusion():
                self.logger.warning(f'[[{page.title}]]: Bot excluded from editing')
                continue

            page.edit(
                edit['content'],
                summary=self.summary.format(changes=len(edit['changes'])),
                baserevid=edit['revid'],
                basetimestamp=None,
                starttimestamp=None,
            )
            time.sleep(10)
