# -*- coding: utf-8 -*-

# Copyright(C) 2012 Romain Bignon
#
# This file is part of weboob.
#
# weboob is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# weboob is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with weboob. If not, see <http://www.gnu.org/licenses/>.


from urlparse import urlsplit

from weboob.deprecated.browser import Browser, BrowserIncorrectPassword
from weboob.capabilities.bank import Account

from .pages import LoginPage, IndexPage, ErrorPage, UnavailablePage, MarketPage, LifeInsurance


__all__ = ['CaisseEpargne']


class CaisseEpargne(Browser):
    DOMAIN = 'www.caisse-epargne.fr'
    PROTOCOL = 'https'
    CERTHASH = ['dfff27d6db1fcdf1cea3ab8e3c1ca4f97c971262e95be49f3385b40c97fe640c', '9894ab2088630f341de821a09f1286c525f854f62ac186bd442368b4692c5969', '0e0fa585a8901c206c4ebbc7ee33e00e17809d7086f224e1b226c46165a4b5ac']
    PAGES = {'https://[^/]+/particuliers/ind_pauthpopup.aspx.*':          LoginPage,
             'https://[^/]+/Portail.aspx.*':                              IndexPage,
             'https://[^/]+/login.aspx':                                  ErrorPage,
             'https://[^/]+/Pages/logout.aspx.*':                         ErrorPage,
             'https://[^/]+/page_hs_dei_.*.aspx':                         UnavailablePage,
             'https://[^/]+/Pages/Bourse.*':                              MarketPage,
             'https://www.caisse-epargne.offrebourse.com/ReroutageSJR':   MarketPage,
             'https://www.caisse-epargne.offrebourse.com/Portefeuille':   MarketPage,
             'https://[^/]+/Assurance/Pages/Assurance.aspx':              LifeInsurance,
             'https://www.extranet2.caisse-epargne.fr.*':                 LifeInsurance,
            }

    def __init__(self, nuser, *args, **kwargs):
        self.nuser = nuser
        self.DOMAIN = kwargs.pop('domain', self.DOMAIN)
        Browser.__init__(self, *args, **kwargs)

    def is_logged(self):
        return self.page is not None and not self.is_on_page((LoginPage,ErrorPage))

    def home(self):
        if self.is_logged():
            self.location(self.buildurl('/Portail.aspx'))
        else:
            self.login()

    def login(self):
        """
        Attempt to log in.
        Note: this method does nothing if we are already logged in.
        """
        assert isinstance(self.username, basestring)
        assert isinstance(self.password, basestring)

        if self.is_logged():
            return

        self._ua_handlers['_cookies'].cookiejar.clear()
        if not self.is_on_page(LoginPage):
            self.location(self.buildurl('/particuliers/ind_pauthpopup.aspx?mar=101&reg=&fctpopup=auth&cv=0'), no_login=True)

        self.page.login(self.username)
        if not self.page.login2(self.nuser, self.password):
            # perso
            self.page.login3(self.password)

        if not self.is_logged():
            raise BrowserIncorrectPassword()

        v = urlsplit(self.page.url)
        self.DOMAIN = v.netloc

    def get_accounts_list(self):
        if self.is_on_page(IndexPage):
            self.page.go_list()
        else:
            self.location(self.buildurl('/Portail.aspx'))

        return self.page.get_list()

    def get_account(self, id):
        assert isinstance(id, basestring)

        l = self.get_accounts_list()
        for a in l:
            if a.id == id:
                return a

        return None

    def _get_history(self, info):
        if not info['link'].startswith('HISTORIQUE'):
            return
        if self.is_on_page(IndexPage):
            self.page.go_list()
        else:
            self.location(self.buildurl('/Portail.aspx?tache=CPTSYNT0'))

        self.page.go_history(info)

        while True:
            assert self.is_on_page(IndexPage)

            for tr in self.page.get_history():
                yield tr

            if not self.page.go_next():
                return

    def get_history(self, account):
        return self._get_history(account._info)

    def get_coming(self, account):
        for info in account._card_links:
            for tr in self._get_history(info):
                tr.type = tr.TYPE_CARD
                yield tr

    def get_investment(self, account):
        if account.type is not Account.TYPE_LIFE_INSURANCE and account.type is not Account.TYPE_MARKET:
            raise NotImplementedError()
        if self.is_on_page(IndexPage):
            self.page.go_list()
        else:
            self.location(self.buildurl('/Portail.aspx'))

        self.page.go_history(account._info)
        if account.type is Account.TYPE_MARKET:
            self.page.submit()
            if self.page.is_error():
                return iter([])
            self.location('https://www.caisse-epargne.offrebourse.com/Portefeuille')
        elif account.type is Account.TYPE_LIFE_INSURANCE:
            try:
                self.page.go_life_insurance(account)
                self.page.submit()
                self.location('https://www.extranet2.caisse-epargne.fr%s' % self.page.get_cons_repart())
            except IndexError:
                return iter([])
        return self.page.iter_investment()
