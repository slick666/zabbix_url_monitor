#!/usr/bin/python
# -*- coding: utf-8 -*-
import json
import logging
from urlparse import urlparse

import commons
import zbxsend

__doc__ = """Action on backends after entry points are handled in main"""


def webfacade(testSet, configinstance, webcaller, config):
    """
    Perform the web request for a check.
    (Called upon by check())

    :param testSet: Name of testset to pull values
    :param configinstance: config class object
    :return requests output:
    """

    # config getters
    tmout = configinstance.get_request_timeout(testSet)
    vfyssl = configinstance.get_verify_ssl(testSet)
    testset = configinstance.get_test_set(testSet)

    # dispatch request
    out = webcaller.run(config,
                        testset['data']['uri'],
                        verify=vfyssl,
                        expected_http_status=str(
                            testset['data']['ok_http_code']),
                        identity_provider=testset[
                            'data']['identity_provider'],
                        timeout=tmout)

    if out == False:  # webcaller.run has requests.exceptions
        logging.error("Spawn request failed, skipping."
                      " url={0}".format(testset['data']['uri']))
        return False
    else:  # it works!
        logging.debug("Spawn request OK (at webfacade)")
        return out


def transmitfacade(configinstance, metrics, logger):
    """
    Send a list of Metric objects to zabbix.
    Called by check()

    param configinstance: The current configinstance object
    param metrics: list of Metrics for zbxsend
    Returns True if succcess.
    """
    constant_zabbix_port = 10051
    try:
        z_host, z_port = commons.get_hostport_tuple(
            constant_zabbix_port,
            configinstance['config']['zabbix']['server']
        )
    except:
        logging.error('Could not reference config: zabbix: server in conf')
        return False

    try:
        # Assume 30.0 if key is empty
        timeout = float(configinstance['config'][
            'zabbix'].get('send_timeout', 30.0))
    except:
        logging.error("Could not reference config: zabbix entry in conf")
        return False

    msg = "Transmitting metrics to zabbix"
    logging.debug(
        "{m}: {telem}".format(
            m=msg, telem=metrics
        )
    )
    logging.info(
        "{m} host {zbxhost}:{zbxport}".format(
            m=msg, metrics=metrics, zbxhost=z_host, zbxport=z_port, logger=logger
        )
    )

    # Send metrics to zabbix
    try:
        zbxsend.send_to_zabbix(
            metrics=metrics,
            zabbix_host=z_host,
            zabbix_port=z_port,
            timeout=timeout,
            logger=logger
        )
    except:
        logging.debug("event.send_to_zabbix({0},{1},{2},{3}) failed in"
                      " transmitfacade()".format(metrics, z_host, z_port, timeout))
        return False
    # success
    return True


def check(testSet, configinstance, logger):
    """
    Perform the checks when called upon by argparse in main()

    :param testSet:
    :param configinstance:
    :param logger:
    :return: tuple (statcode, check)
    """

    testset = configinstance.get_test_set(testSet)

    config = configinstance.load()
    webinstance = commons.WebCaller(logger)

    # Make a request and check a resource
    response = webfacade(testSet, configinstance, webinstance, config)
    if not response:
        return (1, None)  # caught request exception!

    # This is the host defined in your metric.
    # This matches the name of your host in zabbix.
    zabbix_metric_host = config['config']['zabbix']['host']

    zabbix_telemetry = []
    report_bad_health = False

    # For each testElement do our path check and capture results

    for check in testSet['data']['testElements']:
        if not configinstance.datatypes_valid(check):
            return (1, check)

        try:
            datatypes = check['datatype'].split(',')
        except KeyError as err:
            logging.error("Uncaught unknown error")
            return (1, check)
        # We need to make a metric for each explicit data type
        # (string,int,count)
        for datatype in datatypes:
            try:
                api_res_value = commons.omnipath(response.content, testSet[
                    'data']['response_type'], check)
            except KeyError as err:
                logging.error("Uncaught unknown error")
                return (1, check)

            # Append to the check things like response, statuscode, and
            # the request url, I'd like to monitor status codes but don't
            # know what that'll take.

            check['datatype'] = datatype
            check['api_response'] = api_res_value
            check['request_statuscode'] = response.status_code
            check['uri'] = testset['data']['uri']

            # Determines the host of the uri

            try:
                check['originhost'] = urlparse(
                    check['uri']).netloc.split(':')[0]
            except:
                logging.error(
                    "Could not use urlparse on '{0}'".format(check['uri']))
                return (1, check)

            try:
                check['key']
            except KeyError as err:
                logging.error("Uncaught unknown error")
                return (1, check)

            # There was no value associated for the desired key.
            # This is considered a failing check, as datatype is unsupported
            if api_res_value == None:
                logging.warning("{0} check failed check="
                                "{1}".format(check['originhost'], check))
                report_bad_health = True

            # Print out each k,v
            logging.debug(" Found resource {uri}||{k} value ({v})".format(
                uri=check['uri'], k=check['key'], v=check['api_response']))

            # Applies a key format from the configuration file, allowing
            # custom zabbix keys for your items reporting to zabbix. Any
            # check in testSet can be substituted, the {uri} and
            # Pdatatype} are also made available.
            metrickey = config['config']['zabbix'][
                'item_key_format'].format(**check)

            zabbix_telemetry.append(
                zbxsend.Metric(zabbix_metric_host, metrickey, check['api_response'])
            )

    logger.info("Sending telemetry to zabbix server as Metrics objects")
    logger.debug("Telemetry: {0}".format(zabbix_telemetry))
    if not transmitfacade(configinstance=config, metrics=zabbix_telemetry, logger=logger):
        logger.critical("Sending telemetry to zabbix failed!")

    if report_bad_health:
        return (1, check)
    else:
        return (0, check)


def discover(args, configinstance, logger):
    """
    Perform the discovery when called upon by argparse in main()

    :param args:
    :param configinstance:
    :param logger:
    :return:
    """
    configinstance.load_yaml_file(args.config)
    config = configinstance.load()

    discover = True
    if not args.datatype:
        logging.error(
            "\nError: Invalid options\n"
            "       Requires `datatype` flag with --datatype\n"
            "       Possible values: {0} (based on current config)\n"
            "       Define additional datatypes within a testElement\n"
            "       Define Datatype Example:\n"
            "       testSet->your_test_name->testElements->datatype->"
            "your_datatype"
            "\n\n".format(
                configinstance.get_datatypes_list()
            )
        )
        discover = False

    discovery_dict = {'data': []}

    for testSet in config['checks']:
        checkname = testSet['key']

        uri = testSet['data']['uri']

        for discoveryitem in testSet['data']['testElements']:  # For every item
            datatypes = discoveryitem['datatype'].split(',')
            for datatype in datatypes:  # For each datatype in testElements
                if datatype == args.datatype:  # Only add if datatype relevant
                    # Add more useful properties to the discovery discoveryitem
                    discoveryitem.update(
                        {'checkname': checkname,
                         'resource_uri': uri}
                    )

                    # Apply Zabbix low level discovery formating to key names
                    #  (shift to uppercase)
                    for old_key in discoveryitem.keys():
                        new_key = "{#" + old_key.upper() + "}"
                        discoveryitem[new_key] = discoveryitem.pop(old_key)

                    # Add this test discoveryitem to the discovery dict.
                    logger.debug('Item discovered ' + str(discoveryitem))
                    discovery_dict['data'].append(discoveryitem)
    # Print discovery dict.
    if discover:
        print(json.dumps(discovery_dict, indent=3))
