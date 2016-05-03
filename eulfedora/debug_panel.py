'''
Panel for use with
`django-debug-toolbar <https://django-debug-toolbar.readthedocs.org/>`_.

To install, add:

    'eulfedora.debug_panel.FedoraPanel',

to your configured **DEBUG_TOOLBAR_PANELS**.

Reports on the Fedora API requests used run to generate a page, including
time to run the query, arguments passed, and response returned.
'''

import time
import traceback
from django.dispatch import Signal
from debug_toolbar import settings as dt_settings
from debug_toolbar.panels import Panel
from debug_toolbar.utils import render_stacktrace, tidy_stacktrace, \
    get_stack


import eulfedora
from eulfedora.api import ApiFacade, ResourceIndex

# implementation based on django-debug-toolbar cache panel


api_called = Signal(providing_args=[
    "time_taken", "method", "url", "args", "kwargs"])


class ApiTracker(ApiFacade):
    # subclass api request method in order to api query calls

    # all rest api methods go through _make_request
    def _make_request(self, reqmeth, url, *args, **kwargs):
        start = time.time()
        response = super(ApiTracker, self)._make_request(reqmeth, url,
                                                         *args, **kwargs)
        total_time = time.time() - start
        api_called.send(sender=self.__class__, time_taken=total_time,
                        method=reqmeth, url=url, response=response,
                        args=args, kwargs=kwargs)
        return response


class ResourceIndexTracker(ResourceIndex):

    # all risearch methods go through _query
    def _query(self, *args, **kwargs):
        start = time.time()
        response = super(ResourceIndexTracker, self)._query(*args, **kwargs)
        total_time = time.time() - start
        # FIXME: response is currently a csv.DictReader, which
        # can only be read once, so response can't currently be displayed
        # in debug panel output
        api_called.send(sender=self.__class__, time_taken=total_time,
                        method='risearch', url='', response=response,
                        args=args, kwargs=kwargs)
        return response



class FedoraPanel(Panel):

    name = 'Fedora'
    has_content = True

    template = 'eulfedora/debug_panel.html'

    def __init__(self, *args, **kwargs):
        super(FedoraPanel, self).__init__(*args, **kwargs)
        self.total_time = 0
        self.api_calls = []

        api_called.connect(self._store_api_info)

    def _store_api_info(self, sender, time_taken=0, method=None, url=None,
                        response=None, args=None, kwargs=None, **kw):

        time_taken *= 1000
        self.total_time += time_taken

        # use debug-toolbar utilities to get & render stacktrace
        # skip last two entries, which are in eulfedora.debug_panel
        if dt_settings.CONFIG['ENABLE_STACKTRACES']:
            stacktrace = tidy_stacktrace(reversed(get_stack()))[:-2]
        else:
            stacktrace = []

        try:
            method_name = method.__name__.upper()
        except AttributeError:
            method_name = method

        self.api_calls.append({
            'time': time_taken,
            'method': method_name,
            'url': url,
            'args': args,
            'kwargs': kwargs,
            'response': response,
            'stack': render_stacktrace(stacktrace)
        })

    @property
    def nav_title(self):
        return self.name

    def url(self):
        return ''

    def title(self):
        return self.name

    def nav_subtitle(self):
        return "%(calls)d API calls in %(time).2fms" % \
               {'calls': len(self.api_calls), 'time': self.total_time}

    def enable_instrumentation(self):
        # patch tracking api facade subclass in for the real one
        eulfedora.server.RealApiFacade = eulfedora.server.ApiFacade
        eulfedora.server.RealResourceIndex = eulfedora.server.ResourceIndex
        eulfedora.models.RealResourceIndex = eulfedora.models.ResourceIndex

        eulfedora.server.ApiFacade = ApiTracker
        eulfedora.server.ResourceIndex = ResourceIndexTracker
        eulfedora.models.ResourceIndex = ResourceIndexTracker

    def disable_instrumentation(self):
        eulfedora.server.ApiFacade = eulfedora.server.RealApiFacade
        eulfedora.server.ResourceIndex = eulfedora.server.RealResourceIndex
        eulfedora.models.ResourceIndex = eulfedora.models.RealResourceIndex

    def generate_stats(self, request, response):
        # statistics for display in the template
        self.record_stats({
            'total_calls': len(self.api_calls),
            'api_calls': self.api_calls,
            'total_time': self.total_time,
        })
