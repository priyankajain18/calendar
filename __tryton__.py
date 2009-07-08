# -*- coding: utf-8 -*-
#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
{
    'name' : 'Calendar',
    'version' : '0.0.1',
    'author' : 'B2CK',
    'email': 'info@b2ck.com',
    'website': 'http://www.tryton.org/',
    'description': 'Add CalDAV support',
    'depends' : [
        'ir',
        'res',
        'webdav',
    ],
    'xml' : [
        'calendar.xml',
    ],
    'translation': [
    ],
}
