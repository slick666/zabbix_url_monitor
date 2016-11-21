#!/usr/bin/python
# -*- coding: utf-8 -*-
from __future__ import print_function

import argparse
import logging
import sys

import lockfile

import action
import commons
import configuration
from url_monitor import authors as authorsmacro
from url_monitor import authors as emailsmacro
from url_monitor import description as descriptionmacro
from url_monitor import project as projectmacro
from zbxsend import Metric

__doc__ = """Program entry point / arg handling / check passfail review"""


def return_epilog():
    """ Formats the eplig footer generated by help """
    author_strings = []
    for name, email in zip(authorsmacro, emailsmacro):
        author_strings.append('Author: {0} <{1}>'.format(name, email))
    return (
        "{project}\n"
        "{footerline}\n"
        "{authors}"
    ).format(
        footerline=str('-' * 72),
        project=projectmacro,
        authors='\n'.join(author_strings)
    )


def main(arguments=None):
    """
    Program entry point.

    :param arguments:
    :return:
    """
    try:
        if arguments is None:  # __name__=__main__
            arguments = sys.argv[1:]
            progname = sys.argv[0]
        else:  # module entry
            arguments = arguments[1:]
            progname = arguments[0]
    except IndexError:
        print(return_epilog() + "\n")
        logging.error("Invalid options. Use --help for more information.")
        sys.exit(1)

    arg_parser = argparse.ArgumentParser(
        prog=progname,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=descriptionmacro,
        epilog=return_epilog())
    arg_parser.add_argument('COMMAND')
    arg_parser.add_argument(
        "-V",
        "--version",
        action='version',
        version='UNSUPPORTED OPTION'
    )
    arg_parser.add_argument(
        "--key",
        "-k",
        nargs='?',
        default=None,
        help="Optional with `check` command. Can be used to run checks on"
        " a limited subset of item headings under testSet from the yaml "
        "config."
    )
    arg_parser.add_argument(
        "--datatype",
        "-t",
        nargs='?',
        default=None,
        help="Required with `discover` command. This filters objects from"
        " the config that have a particular datatype. This data is used by"
        " low level discovery in Zabbix."
    )
    arg_parser.add_argument(
        "-c",
        "--config",
        default=None,
        help="Specify custom config file, system default /etc/url_monitor."
        "yaml"
    )
    arg_parser.add_argument(
        "--loglevel",
        default=None,
        help="Specify custom loglevel override. Available options [debug,"
        " info, wrna, critical, error, exceptions]"
    )

    inputflag = arg_parser.parse_args(args=arguments)

    configinstance = configuration.ConfigObject()
    configinstance.load_yaml_file(inputflag.config)
    logger = configinstance.get_logger(inputflag.loglevel)

    configinstance.pre_flight_check()
    config = configinstance.load()

    # stage return code
    set_rc = 0

    # skip if skip conditions exist (for standby nodes)
    conditional_skip_queue = configinstance.skip_conditions
    if inputflag.COMMAND == "discover":
        conditional_skip_queue = []  # no need to disable this
    if len(conditional_skip_queue) > 0:
        logger.info("Checking {0} standby conditions to see if test execution"
                    " should skip.".format(len(conditional_skip_queue)))
    for test in conditional_skip_queue:
        for condition, condition_args in test.items():
            if commons.skip_on_external_condition(
                    logger, condition, condition_args):
                exit(0)

    if inputflag.COMMAND == "check":
        try:
            lock = lockfile.FileLock(config['config']['pidfile'])
        except lockfile.NotMyLock as e:
            logger.error(
                "lockfile exception: it appears this is not my lockfile {0}".format(e))
            exit(1)
        except Exception as e:
            logger.error("lockfile exception: a general exception occured while acquiring "
                         "lockfile.FileLock {0}".format(e))
            exit(1)

        if lock.is_locked():
            logger.critical(
                " Fail! Process already running with PID {0}. EXECUTION STOP.".format(lock.pid))
            exit(1)
        with lock:  # context will .release() automatically
            logger.info(
                "PID lock acquired {0} {1}".format(lock.path, lock.pid))

            # run check
            completed_runs = []  # check results
            for checkitem in config['checks']:
                try:
                    if (inputflag.key is not None and
                            checkitem['key'] == inputflag.key):
                        # --key defined and name matched! only run 1 check
                        rc, checkobj = action.check(
                            checkitem, configinstance, logger
                        )
                        completed_runs.append(
                            (
                                rc,
                                checkitem['key'],
                                checkobj
                            )
                        )
                    elif not inputflag.key:
                        # run all checks
                        rc, checkobj = action.check(
                            checkitem, configinstance, logger
                        )
                        completed_runs.append(
                            (
                                rc,
                                checkitem['key'],
                                checkobj
                            )
                        )
                except Exception as e:
                    logger.exception(e)

            # set run status overall
            for check in completed_runs:
                rc, name, values = check
                if rc == 0 and set_rc == 0:
                    set_rc = 0
                else:
                    set_rc = 1

            # report errors
            badmsg = "with errors    [FAIL]"
            if set_rc == 0:
                badmsg = "without errors    [ OK ]"
            logger.info("Checks have completed {0}".format(badmsg))

            # Report final conditions to zabbix (so informational alerting can
            # be built around failed script runs, exceptions, network errors,
            # timeouts, etc)
            logger.info(
                "Sending execution summary to zabbix server as Metrics objects"
            )

            if not values:  # Do you see uncaught requests.exceptions?
                values = {'EXECUTION_STATUS': 1}  # trigger an alert

            metrickey = config['config'][
                'zabbix']['checksummary_key_format']

            check_completion_status = [Metric(
                config['config']['zabbix']['host'], metrickey, set_rc
            )]

            logger.debug("Summary: {0}".format(check_completion_status))
            if not action.transmitfacade(config, check_completion_status, logger=logger):
                logger.critical(
                    "Sending execution summary to zabbix server failed!")
                set_rc = 1
    if inputflag.COMMAND == "discover":
        action.discover(inputflag, configinstance, logger)
        set_rc = 0

    # drop lockfile, then exit (if check mode is active)
    if inputflag.COMMAND == "check":
        print(set_rc)  # don't need print retcode in discover
        exit(set_rc)


def entry_point():
    """Zero-argument entry point for use with setuptools/distribute."""
    raise SystemExit(main(sys.argv))

if __name__ == "__main__":
    entry_point()
