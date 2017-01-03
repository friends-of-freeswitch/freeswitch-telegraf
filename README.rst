FreeSWITCH Telegraf Collector
-----------------------------

This package exposes FreeSWITCH metrics for scraping by
`Telegraf
<https://github.com/influxdata/telegraf>`_.

It is meant to be executed by the
`Telegraf input plugin
<https://github.com/influxdata/telegraf/tree/master/plugins/inputs/exec>`_.

Connectivity to FreeSWITCH is handled through
`GreenSWITCH
<https://github.com/EvoluxBR/greenswitch>`_.

Install
=======

Installation instructions::

    # Just copy the script to a suitable location
    $ python setup.py install

    # Execute it to make sure it's printing the metrics
    $ freeswitch-telegraf --host 127.0.0.1 -p 8021 -s ClueCon
      freeswitch_sessions concurrent=0,concurrent_peak=0,per_second=0,concurrent_5min=0,total=0,per_second_peak=0,per_second_5min=0
      freeswitch_sofia_profile_sessions,profile=external-ipv6 total_inbound=0,failed_inbound=0,total_outbound=0,failed_outbound=0
      freeswitch_sofia_profile_sessions,profile=internal-ipv6 total_inbound=0,failed_inbound=0,total_outbound=0,failed_outbound=0
      freeswitch_sofia_profile_sessions,profile=internal total_inbound=0,failed_inbound=0,total_outbound=0,failed_outbound=0
      freeswitch_sofia_profile_sessions,profile=external total_inbound=0,failed_inbound=0,total_outbound=0,failed_outbound=0

Configure
=========

Now you can configure Telegraf exec plugin to execute the script to collect the metrics. Make sure to configure the 'influx' data format
in your telegraf.conf exec configuration::

    [[inputs.exec]]
      ## Commands array
      commands = ["/usr/bin/freeswitch-telegraf --host 127.0.0.1 -p 8021 -s ClueCon"]

      ## Timeout for each command to complete.
      timeout = "5s"

      ## Data format to consume.
      ## Each data format has it's own unique set of configuration options, read
      ## more about them here:
      ## https://github.com/influxdata/telegraf/blob/master/docs/DATA_FORMATS_INPUT.md
      data_format = "influx"
