#!/usr/bin/env python
# vim: tabstop=4 softtabstop=4 shiftwidth=4 textwidth=80 smarttab expandtab
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
from recordclass import recordclass

ConfMemberMetrics = recordclass('ConfMemberMetrics', (
    'id',
    'uuid',
    'input_buflen',
    'output_buflen',
    'input_frames_count',
    'input_flush_count',
    'input_hiccups_count',
    'input_max_time',
    'input_avg_time',
    'output_frames_count',
    'output_flush_count',
    'output_hiccups_count',
    'output_max_time',
    'output_avg_time'
))


ModuleInfo = recordclass('ModuleInfo', (
    'type',
    'name',
    'ikey',
    'filename'
))


TimerSample = recordclass('TimerSample', (
    'timer',
    'iter',
    'target',
    'value'
))


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


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


class FreeSWITCHMetricsCollector(object):
    """ Collect FreeSWITCH Metrics and expose
        them using the influxdb line protocol """

    def __init__(self):
        self.metrics = []
        self._modules = []
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
        count_match = re.search(r'\n(\d+).+-\s+peak\s+(\d+).+5min\s+(\d+)',
                                status, re.IGNORECASE)
        if count_match:
            fields.update({
                'concurrent': int(count_match.group(1)),
                'concurrent_peak': int(count_match.group(2)),
                'concurrent_5min': int(count_match.group(3))
            })
        cps_match = re.search(r'\n(\d+).+per\s+Sec.+peak\s+(\d+).+5min\s+(\d+)',
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
        if not status:
            return
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

    def _parse_conf_loop_metrics(self, output, fields):
        if not output:
            return
        field_map = {
            'Time Hiccups': 'hiccups',
            'Max Wait': 'max_time',
            'Min Wait': 'min_time',
            'Avg Wait': 'avg_time'
        }
        field_prefix = ''
        for line in output.split('\n'):
            if '-- Timer' in line:
                field_prefix = 'timer_'
            elif '-- Mixing' in line:
                field_prefix = 'mixloop_'
            if not field_prefix:
                continue
            if ':' not in line:
                continue
            k, v = [v.strip() for v in line.split(':')]
            if k not in field_map:
                continue
            m = re.search(r'^(\d+).*', line.split(':')[1].strip())
            if not m:
                continue
            fields[field_prefix + field_map[k]] = int(m.group(1))

    def _collect_conference_metrics(self):
        """ Collect FreeSWITCH Conference Metrics """
        output = self._api('conference list')
        if not output:
            return
        confs = []
        for line in output.split('\n'):
            confmatch = re.search(r'Conference\s+(\w+).+', line, re.IGNORECASE)
            if not confmatch:
                continue
            confs.append(confmatch.group(1))
        if not confs:
            return
        for conf in confs:
            output = self._api('conference {} debug_all'.format(conf))
            if not output or 'not found' in output:
                continue

            # Right now we only care about input/output buffer sizes,
            # max wait and time hiccup counters
            max_metrics = ConfMemberMetrics(*((0, ) * len(ConfMemberMetrics._fields)))
            exclude = ('id', 'uuid')
            cmfields = [f for f in ConfMemberMetrics._fields if f not in exclude]
            for line in output.split('\n'):
                if not line:
                    continue
                metrics = ConfMemberMetrics(*line.split(';'))
                for field in cmfields:
                    v = getattr(metrics, field)
                    if not is_number(v):
                        continue
                    v = int(v)
                    m = int(getattr(max_metrics, field))
                    if v > m:
                        setattr(max_metrics, field, v)
            fields = {}
            for field in cmfields:
                fields['max_' + field] = getattr(max_metrics, field)

            # Now add conference mixing thread metrics
            output = self._api('conference {} debug'.format(conf))
            self._parse_conf_loop_metrics(output, fields)

            self.metrics.append(
                Metric('freeswitch_conference_metrics', fields,
                       {'confname': conf})
            )

    def _get_modules(self):
        if self._modules:
            return self._modules
        self._modules = []
        output = self._api('show modules')
        if not output:
            return self._modules
        for line in output.split('\n'):
            if ',' not in line or line.startswith('type'):
                continue
            self._modules.append(ModuleInfo(*line.split(',')))
        return self._modules

    def _collect_core_timing_metrics(self):
        """ Collect FreeSWITCH Core Timing Metrics """
        time_modules = [m for m in self._get_modules() if m.type == 'timer']
        if not time_modules:
            return
        # Unfortunately timer_test currently provides limited output
        # this collector is assuming a patched FS version (FIXME: Submit patch)
        interval = 20
        samples = 50
        threshold_50 = (interval * 1.5) * 1000
        threshold_100 = (interval * 2) * 1000
        for mod in time_modules:
            output = self._api('timer_test {} {} {}'.format(interval, samples, mod.name))
            if not output:
                continue
            min_time = float('inf')
            max_time = 0
            avg_time = 0
            higher_count_50 = 0
            higher_count_100 = 0
            for line in output.split('\n'):
                line = line.strip()
                if not line:
                    continue
                if 'Avg:' in line:
                    # Last line, just get the average and exit loop
                    m = re.search(r'.*Avg:\s+([\d\.]+)ms.*', line, re.IGNORECASE)
                    if not m:
                        return
                    avg_time = float(m.group(1)) * 1000 # get it in microseconds
                    break
                sample = TimerSample(*line.split(';'))
                value = float(sample.value)
                max_time = max(value, max_time)
                min_time = min(value, min_time)
                if value >= threshold_100:
                    higher_count_100 += 1
                elif value >= threshold_50:
                    higher_count_50 += 1

            if min_time == float('inf'):
                min_time = 0

            fields = {
                'min_time': int(min_time),
                'max_time': int(max_time),
                'avg_time': int(avg_time),
                'percent_higher_50_count': int(higher_count_50),
                'percent_higher_100_count': int(higher_count_100)
            }
            self.metrics.append(
                Metric('freeswitch_core_timing', fields,
                       {'timer': mod.name})
            )

    def collect(self):
        """ Collect FreeSWITCH Metrics """
        self._collect_core_status_metrics()
        self._collect_core_timing_metrics()
        self._collect_sofia_status_metrics()
        self._collect_conference_metrics()

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
