#!/usr/bin/env python
"""
FreeSWITCH Input for Telegraf

This outputs FreeSWITCH measurements in native influxdb line protocol
and can be executed with the Telegraf exec input plugin
"""
from __future__ import print_function
import re
import argparse
import greenswitch
import xml.etree.ElementTree as ET
from itertools import chain


class Metric(object):
    def __init__(self, measurement, fields, tags={}):
        self.measurement = measurement
        if isinstance(fields, dict):
            self.fields = fields
        else:
            self.fields = {'value': float(fields)}
        self.tags = tags

    def __str__(self):
        tags = [''] + ['{}={}'.format(k, v)
                       for k, v in self.tags.iteritems()]
        fields = ['{}={}'.format(k, v)
                  for k, v in self.fields.iteritems()]
        return '{}{} {}'.format(
            self.measurement,
            ','.join(tags),
            ','.join(fields)
        )


class FreeSWITCHMetricsCollector(object):
    """ Collect FreeSWITCH Metrics and expose
        them using the influxdb line protocol """

    def __init__(self):
        self.metrics = []
        parser = argparse.ArgumentParser(
            description='Collect FreeSWITCH Metrics'
        )
        parser.add_argument('--host', metavar='HOST',
                            default='127.0.0.1',
                            help='FreeSWITCH ESL Host')
        parser.add_argument('-p', '--port', metavar='PORT',
                            default=8021,
                            help='FreeSWITCH ESL Port')
        parser.add_argument('-s', '--secret', metavar='PASSWORD',
                            default='ClueCon',
                            help='FreeSWITCH ESL Password')
        args = parser.parse_args()
        self.fs = greenswitch.InboundESL(host=args.host,
                                         port=args.port,
                                         password=args.secret)
        self.fs.connect()

    def _collect_core_status_metrics(self):
        """ Collect core status metrics """
        fields = {}
        status = self._api('status')
        if not status:
            return
        total_match = re.search(r'(\d+).+session.+since.+startup',
                                status, re.IGNORECASE)
        if total_match:
            fields.update({
                'total': int(total_match.group(1)),
            })
        count_match = re.search(r'\n(\d+).+-.+peak.+(\d+).+5min.+(\d+)',
                                status, re.IGNORECASE)
        if count_match:
            fields.update({
                'concurrent': int(count_match.group(1)),
                'concurrent_peak': int(count_match.group(2)),
                'concurrent_5min': int(count_match.group(3))
            })
        cps_match = re.search(r'\n(\d+).+per.+Sec.+peak.+(\d+).+5min.+(\d+)',
                              status, re.IGNORECASE)
        if cps_match:
            fields.update({
                'per_second': int(cps_match.group(1)),
                'per_second_peak': int(cps_match.group(2)),
                'per_second_5min': int(cps_match.group(3))
            })
        if fields:
            self.metrics.append(Metric('freeswitch_sessions', fields))

    def _collect_sofia_status_metrics(self):
        """ Colect sofia profile metrics """
        # First, gather all profile names
        status = self._api('sofia xmlstatus')
        try:
            root = ET.fromstring(status)
            profiles = {e.text for e in
                        chain.from_iterable(root.findall('profile'))
                        if e.tag == 'name'}
        except ET.ParseError:
            return
        for profile in profiles:
            status = self._api(
                'sofia xmlstatus profile {}'.format(profile)
            )
            try:
                root = ET.fromstring(status)
            except ET.ParseError:
                continue
            info = root.find('profile-info')
            if info is None:
                continue
            fields = {
                'total_inbound': int(info.find('calls-in').text),
                'total_outbound': int(info.find('calls-out').text),
                'failed_inbound': int(info.find('failed-calls-in').text),
                'failed_outbound': int(info.find('failed-calls-out').text)
            }
            self.metrics.append(
                Metric('freeswitch_sofia_profile_sessions', fields,
                       {'profile': profile})
            )

    def collect(self):
        """ Collect FreeSWITCH Metrics """
        self._collect_core_status_metrics()
        self._collect_sofia_status_metrics()

    def _api(self, api):
        """ Execute FreeSWITCH API """
        response = self.fs.send('api {}'.format(api))
        if not response or response.data.startswith('-ERR'):
            return None
        return response.data

    def __str__(self):
        s = ''
        for m in self.metrics:
            s += '{}\n'.format(m)
        return s.strip()


def main():
    """ Run FreeSWITCH Metrics collector """
    collector = FreeSWITCHMetricsCollector()
    collector.collect()
    print(collector)


if __name__ == '__main__':
    main()
