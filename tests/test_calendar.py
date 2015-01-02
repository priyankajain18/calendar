# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
import unittest
import trytond.tests.test_tryton
from trytond.tests.test_tryton import test_view, test_depends, test_menu_action


class CalendarTestCase(unittest.TestCase):
    'Test Calendar module'

    def setUp(self):
        trytond.tests.test_tryton.install_module('calendar')

    def test0005views(self):
        'Test views'
        test_view('calendar')

    def test0006depends(self):
        'Test depends'
        test_depends()

    def test0007menu_actions(self):
        'Test menu actions'
        test_menu_action('calendar')


def suite():
    suite = trytond.tests.test_tryton.suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
        CalendarTestCase))
    return suite
