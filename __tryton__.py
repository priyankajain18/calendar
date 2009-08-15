# -*- coding: utf-8 -*-
#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
{
    'name' : 'Calendar',
    'name_de_DE' : 'Kalender',
    'name_es_CO' : 'Calendario',
    'version' : '0.0.1',
    'author' : 'B2CK',
    'email': 'info@b2ck.com',
    'website': 'http://www.tryton.org/',
    'description': 'Add CalDAV support',
    'description_de_DE' : 'Fügt Unterstützung für CalDAV hinzu',
    'description_es_CO' : 'Añade soporte para CalDAV',
    'depends' : [
        'ir',
        'res',
        'webdav',
    ],
    'xml' : [
        'calendar.xml',
    ],
    'translation': [
        'de_DE.csv',
        'es_CO.csv',
    ],
}
