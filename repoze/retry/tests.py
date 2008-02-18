import unittest

class CEBase:

    def _getConflictError(self):
        from repoze.retry import ConflictError
        return ConflictError

    ConflictError = property(_getConflictError,)

_MINIMAL_HEADERS = [('Content-Type', 'text/plain')]

def _faux_start_response(result, headers):
    pass

class RetryTests(unittest.TestCase, CEBase):

    _dummy_start_response_result = None

    def _getTargetClass(self):
        from repoze.retry import Retry
        return Retry

    def _makeOne(self, *arg, **kw):
        return self._getTargetClass()(*arg, **kw)

    def _makeEnv(self, **kw):
        return {}

    def test_conflict_not_raised_start_response_not_called(self):
        application = DummyApplication(conflicts=1)
        retry = self._makeOne(application, tries=4,
                              retryable=(self.ConflictError,))
        result = retry(self._makeEnv(), _faux_start_response)
        self.assertEqual(list(result), ['hello'])
        self.assertEqual(application.called, 1)

    def test_conflict_raised_start_response_not_called(self):
        application = DummyApplication(conflicts=5)
        retry = self._makeOne(application, tries=4,
                              retryable=(self.ConflictError,))
        self.failUnlessRaises(self.ConflictError,
                              retry, self._makeEnv(), _faux_start_response)
        self.assertEqual(application.called, 4)

    def _dummy_start_response(self, *arg):
        self._dummy_start_response_result = arg

    def test_conflict_raised_start_response_called(self):
        application = DummyApplication(conflicts=5, call_start_response=True)
        retry = self._makeOne(application, tries=4,
                              retryable=(self.ConflictError,))
        self.failUnlessRaises(self.ConflictError, retry, self._makeEnv(),
                              self._dummy_start_response)
        self.assertEqual(application.called, 4)
        self.assertEqual(self._dummy_start_response_result,
                         ('200 OK', _MINIMAL_HEADERS))

    def test_conflict_not_raised_start_response_called(self):
        application = DummyApplication(conflicts=1, call_start_response=True)
        retry = self._makeOne(application, tries=4,
                              retryable=(self.ConflictError,))
        result = retry(self._makeEnv(), self._dummy_start_response)
        self.assertEqual(application.called, 1)
        self.assertEqual(self._dummy_start_response_result,
                         ('200 OK', _MINIMAL_HEADERS))
        self.assertEqual(list(result), ['hello'])

    def test_alternate_retryble_exception(self):
        application = DummyApplication(conflicts=1, exception=Retryable)
        retry = self._makeOne(application, tries=4, retryable=(Retryable,))
        result = retry(self._makeEnv(), _faux_start_response)
        self.assertEqual(list(result), ['hello'])
        self.assertEqual(application.called, 1)

    def test_alternate_retryble_exceptions(self):
        app1 = DummyApplication(conflicts=1)
        app2 = DummyApplication(conflicts=1, exception=Retryable)

        retry1 = self._makeOne(app1, tries=4,
                               retryable=(self.ConflictError, Retryable,))
        result = retry1(self._makeEnv(), _faux_start_response)
        self.assertEqual(list(result), ['hello'])
        self.assertEqual(app1.called, 1)

        retry2 = self._makeOne(app2, tries=4,
                               retryable=(self.ConflictError, Retryable,))
        result = retry2(self._makeEnv(), _faux_start_response)
        self.assertEqual(list(result), ['hello'])
        self.assertEqual(app2.called, 1)

class WSGIConformanceTests(RetryTests):

    def setUp(self):
        import warnings
        warnings.filterwarnings(action='error')

    def tearDown(self):
        import warnings
        warnings.resetwarnings()

    def _makeOne(self, app, *arg, **kw):
        from wsgiref.validate import validator
        rhs = validator(app)
        retry = self._getTargetClass()(rhs, *arg, **kw)
        lhs = validator(retry)
        return lhs

    def _makeEnv(self, **kw):
        from wsgiref.util import setup_testing_defaults
        env = {}
        setup_testing_defaults(env)
        env.update(kw)
        env['QUERY_STRING'] = ''
        return env

class FactoryTests(unittest.TestCase, CEBase):

    def test_make_retry_defaults(self):
        from repoze.retry import make_retry #FUT
        app = object()
        middleware = make_retry(app, {})
        self.failUnless(middleware.application is app)
        self.assertEqual(middleware.tries, 3)
        self.assertEqual(middleware.tries, 3)
        self.assertEqual(middleware.retryable, (self.ConflictError,))

    def test_make_retry_override_tries(self):
        from repoze.retry import make_retry #FUT
        app = object()
        middleware = make_retry(app, {}, tries=4)
        self.failUnless(middleware.application is app)
        self.assertEqual(middleware.tries, 4)
        self.assertEqual(middleware.retryable, (self.ConflictError,))

    def test_make_retry_override_retryable_one(self):
        from repoze.retry import make_retry #FUT
        app = object()
        middleware = make_retry(app, {}, retryable='%s:Retryable' % __name__)
        self.failUnless(middleware.application is app)
        self.assertEqual(middleware.tries, 3)
        self.assertEqual(middleware.retryable, (Retryable,))

    def test_make_retry_override_retryable_multiple(self):
        from repoze.retry import make_retry #FUT
        app = object()
        middleware = make_retry(app, {},
                                retryable='%s:Retryable %s:AnotherRetryable'
                                    % (__name__, __name__))
        self.failUnless(middleware.application is app)
        self.assertEqual(middleware.tries, 3)
        self.assertEqual(middleware.retryable, (Retryable, AnotherRetryable))

class Retryable(Exception):
    pass

class AnotherRetryable(Exception):
    pass

class IterCallsStartResponse:
    """ This is a wrapper to appease the lint checker:  if the app
        does *not* call 'start_response' itself, then the checker barfs
        if the returned iterable does not call 'start_response' before
        returning the first chunk.
    """
    def __init__(self, start_response, *args):
        self.start_response = start_response
        self.args = args

    def __iter__(self):
        if self.start_response:
            self.start_response('200 OK', _MINIMAL_HEADERS)
            del self.start_response
        return iter(self.args)
 
class DummyApplication(CEBase):
    def __init__(self, conflicts, call_start_response=False,
                 exception=None):
        self.called = 0
        self.conflicts = conflicts
        self.call_start_response = call_start_response
        if exception is None:
            exception = self.ConflictError
        self.exception = exception

    def __call__(self, environ, start_response):
        if self.call_start_response:
            start_response('200 OK', _MINIMAL_HEADERS)
        if self.called < self.conflicts:
            self.called += 1
            raise self.exception
        if self.call_start_response:
            return ['hello']
        # Dead chicken (see above)
        return IterCallsStartResponse(start_response, 'hello')

def test_suite():
    import sys
    return unittest.findTestCases(sys.modules[__name__])

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
