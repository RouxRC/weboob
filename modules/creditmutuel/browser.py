# -*- coding: utf-8 -*-

# Copyright(C) 2010-2011 Julien Veyssier
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


from weboob.tools.browser import BaseBrowser, BrowserIncorrectPassword
from weboob.capabilities.bank import Transfer, TransferError
from datetime import datetime

from .pages import LoginPage, LoginErrorPage, AccountsPage, UserSpacePage, \
                   OperationsPage, NoOperationsPage, InfoPage, TransfertPage

__all__ = ['CreditMutuelBrowser']


# Browser
class CreditMutuelBrowser(BaseBrowser):
    PROTOCOL = 'https'
    DOMAIN = 'www.creditmutuel.fr'
    ENCODING = 'iso-8859-1'
    USER_AGENT = BaseBrowser.USER_AGENTS['wget']
    PAGES = {'https://www.creditmutuel.fr/groupe/fr/index.html':   LoginPage,
             'https://www.creditmutuel.fr/.*/fr/identification/default.cgi': LoginErrorPage,
         'https://www.creditmutuel.fr/.*/fr/banque/situation_financiere.cgi': AccountsPage,
         'https://www.creditmutuel.fr/.*/fr/banque/espace_personnel.aspx': UserSpacePage,
         'https://www.creditmutuel.fr/.*/fr/banque/mouvements.cgi.*': OperationsPage,
         'https://www.creditmutuel.fr/.*/fr/banque/nr/nr_devbooster.aspx.*': OperationsPage,
         'https://www.creditmutuel.fr/.*/fr/banque/operations_carte\.cgi.*': OperationsPage,
         'https://www.creditmutuel.fr/.*/fr/banque/arrivees\.asp.*': NoOperationsPage,
         'https://www.creditmutuel.fr/.*/fr/banque/BAD.*': InfoPage,
         'https://www.creditmutuel.fr/.*/fr/banque/.*Vir.*': TransfertPage
            }

    def __init__(self, *args, **kwargs):
        BaseBrowser.__init__(self, *args, **kwargs)
        #self.SUB_BANKS = ['cmdv','cmcee','cmse', 'cmidf', 'cmsmb', 'cmma', 'cmmabn', 'cmc', 'cmlaco', 'cmnormandie', 'cmm']
        #self.currentSubBank = None

    def is_logged(self):
        return self.page and not self.is_on_page(LoginPage) and not self.is_on_page(LoginErrorPage)

    def home(self):
        return self.location('https://www.creditmutuel.fr/groupe/fr/index.html')

    def login(self):
        assert isinstance(self.username, basestring)
        assert isinstance(self.password, basestring)

        if not self.is_on_page(LoginPage):
            self.location('https://www.creditmutuel.fr/', no_login=True)

        self.page.login(self.username, self.password)

        if not self.is_logged() or self.is_on_page(LoginErrorPage):
            raise BrowserIncorrectPassword()

        self.SUB_BANKS = ['cmdv', 'cmcee', 'cmse', 'cmidf', 'cmsmb', 'cmma', 'cmmabn', 'cmc', 'cmlaco', 'cmnormandie', 'cmm']
        self.getCurrentSubBank()

    def get_accounts_list(self):
        if not self.is_on_page(AccountsPage):
            self.location('https://www.creditmutuel.fr/%s/fr/banque/situation_financiere.cgi' % self.currentSubBank)
        return self.page.get_list()

    def get_account(self, id):
        assert isinstance(id, basestring)

        l = self.get_accounts_list()
        for a in l:
            if a.id == id:
                return a

        return None

    def getCurrentSubBank(self):
        # the account list and history urls depend on the sub bank of the user
        current_url = self.geturl()
        current_url_parts = current_url.split('/')
        for subbank in self.SUB_BANKS:
            if subbank in current_url_parts:
                self.currentSubBank = subbank

    def get_history(self, account):
        page_url = account._link_id
        #operations_count = 0
        l_ret = []
        while (page_url):
            if page_url.startswith('/'):
                self.location(page_url)
            else:
                self.location('https://%s/%s/fr/banque/%s' % (self.DOMAIN, self.currentSubBank, page_url))

            if not self.is_on_page(OperationsPage):
                break

            for op in self.page.get_history():
                l_ret.append(op)
            page_url = self.page.next_page_url()

        return l_ret

    def transfer(self, account, to, amount, reason=None):
        # access the transfer page
        transfert_url = 'WI_VPLV_VirUniSaiCpt.asp?RAZ=ALL&Cat=6&PERM=N&CHX=A'
        self.location('https://%s/%s/fr/banque/%s' % (self.DOMAIN, self.currentSubBank, transfert_url))

        # fill the form
        self.select_form(name='FormVirUniSaiCpt')
        self['IDB'] = [account[-1]]
        self['ICR'] = [to[-1]]
        self['MTTVIR'] = '%s' % str(amount).replace('.', ',')
        if reason != None:
            self['LIBDBT'] = reason
            self['LIBCRT'] = reason
        self.submit()

        # look for known errors
        content = unicode(self.response().get_data(), self.ENCODING)
        insufficient_amount_message     = u'Montant insuffisant.'
        maximum_allowed_balance_message = u'Solde maximum autorisé dépassé.'

        if content.find(insufficient_amount_message) != -1:
            raise TransferError('The amount you tried to transfer is too low.')

        if content.find(maximum_allowed_balance_message) != -1:
            raise TransferError('The maximum allowed balance for the target account has been / would be reached.')

        # look for the known "all right" message
        ready_for_transfer_message = u'Confirmez un virement entre vos comptes'
        if not content.find(ready_for_transfer_message):
            raise TransferError('The expected message "%s" was not found.' % ready_for_transfer_message)

        # submit the confirmation form
        self.select_form(name='FormVirUniCnf')
        submit_date = datetime.now()
        self.submit()

        # look for the known "everything went well" message
        content = unicode(self.response().get_data(), self.ENCODING)
        transfer_ok_message = u'Votre virement a été exécuté ce jour'
        if not content.find(transfer_ok_message):
            raise TransferError('The expected message "%s" was not found.' % transfer_ok_message)

        # We now have to return a Transfer object
        transfer = Transfer(submit_date.strftime('%Y%m%d%H%M%S'))
        transfer.amount = amount
        transfer.origin = account
        transfer.recipient = to
        transfer.date = submit_date
        return transfer

    #def get_coming_operations(self, account):
    #    if not self.is_on_page(AccountComing) or self.page.account.id != account.id:
    #        self.location('/NS_AVEEC?ch4=%s' % account._link_id)
    #    return self.page.get_operations()
