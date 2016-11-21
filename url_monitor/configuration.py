#!/usr/bin/python
# -*- coding: utf-8 -*-
import logging
import logging.handlers
import logging.handlers
import socket
import sys

import yaml

import commons
import exception
from url_monitor import package as packagemacro


class baseConfig():
    """
    Base class for ConfigObject
    """

    def __init__(self):
        self.config = None
        self.checks = None
        self.constant_syslog_port = 514

    def load_yaml_file(self, config=None):
        """
        Loads a yaml file as a dict
        :param config: yaml file
        :return: dict
        """
        if config == None:
            config = "/etc/url_monitor.yaml"

        with open(config, 'r') as stream:
            try:
                self.config = (yaml.load(stream))
                return self.config
            except yaml.YAMLError as exc:
                print("Exception: YAML Parse Error!\n{exc}".format(exc=exc))
                sys.exit(1)

    def load(self):
        """ This is the main config load function to pull in
            configurations to convienent and common namespace.
        """
        return {'checks': self._load_checks(),
                'config': self.raw,
                'identity_providers': self.identity_providers}

    def _load_checks(self, withIdentityProvider=None):
        """ Loads the checks for work to be run.
            Default loads all checks, withIdentityProvider option will limit
            checks returned by identity provider (useful for smart async
            request grouping)
        """
        loaded_checks = []

        if withIdentityProvider:
            # Useful if doing grouping async requests with a identityprovider
            #  and then spawning async call
            for checkdata in self.test_sets:
                if checkdata['data'][
                        'identity_provider'].lower() == withIdentityProvider.lower():
                    # loaded_checks.append({'data': checkdata['data']})
                    loaded_checks.append(checkdata)

        else:
            loaded_checks = self.test_sets

        return loaded_checks

    def _uniq(self, seq):
        """
        Returns a unique list when a list of
        non unique items are put in.

        :return list:
        """
        set = {}
        map(set.__setitem__, seq, [])
        return set.keys()


class configProperties():
    """
    Contains property methods to help out ConfigObject
    """
    @property
    def raw(self):
        """
        Return base config
        """
        return self.config['config']

    @property
    def identity_providers(self):
        """
        This fetches out a list of identity providers kwarg configs
        from main config
        """
        providers = {}

        for provider_config_alias, v in self.raw[
                'identity_providers'].iteritems():
            # Add each provider and config to dictionary from yaml file.
            providers[provider_config_alias] = v
        # Return a list of the config
        return providers

    @property
    def test_sets(self):
        """ Used to prepare format of data for the checker functions.

        [
            {
                  "data": {
                       "identity_provider": "None",
                       "testElements": [
                            {
                                 "datatype": "string",
                                 "jsonvalue": "./value/to/look/for[0]",
                                 "unit_of_measure": "events",
                                 "key": "zabbix_key",
                                 "metricname": "a friendly name"
                            },
                       ],
                       "response_type": "json",
                       "ok_http_code": 200,
                       "uri": "https://localhost"
                  },
                  "key": "testSetName"
             },
             {
                  "data": {
                       "identity_provider": "my_identity_alias
                       "testElements": [
                            {
                                 "datatype": "string",
                                 "jsonvalue": "./value/to/look/for[1]",
                                 "unit_of_measure": "events",
                                 "key": "zabbix_key",
                                 "metricname": "a friendly name"
                            },
                       ],
                       "response_type": "json",
                       "ok_http_code": 200,
                       "uri": "https://localhost"
                  },
                  "key": "testSetName2"
             }
        ]
        """

        checks = []
        for k, v in self.config['testSet'].iteritems():
            checks.append({'key': k, 'data': v})

        return checks

    @property
    def skip_conditions(self):
        """
        Returns a parsed list of skippable conditions from the configuration
        file. This is used with the skip_run_when feature.

        returns a list.
        """
        config = self.load()
        config = config['config']

        skip_conditions = []  # dict of skip conditions
        config = config.get('skip_run_when')

        # Skip if puppet fact exists
        facter = config.get('puppet_facter', False)

        if config and facter:
            script = facter.get('script')
            fact = facter.get('fact')
            value = facter.get('value')

            # assume facter in env $PATH since user doesnt know
            if not script:
                script = "facter"

            if not fact:
                raise exception.RequiredConfigMissing(
                    "config:\n\t"
                    "skip_run_when:\n\t\t"
                    "puppet_facter:\n\t\t\t"
                    "fact: <MISSING KEY>".expandtabs(2)
                )

            if not value:
                raise exception.RequiredConfigMissing(
                    "config:\n\t"
                    "skip_run_when:\n\t\t"
                    "puppet_facter:\n\t\t\t"
                    "value: <MISSING KEY>".expandtabs(2)
                )

            skip_conditions.append(
                {"facter": (script, fact, value)}
            )

        # Skip if shell output result exists
        shell = config.get('shell', False)
        if config and shell:
            script = shell.get('script')
            stdout = shell.get('stdout')
            code = shell.get('code')

            if not script:
                raise exception.RequiredConfigMissing(
                    "config:\n\t"
                    "skip_run_when:\n\t\t"
                    "shell:\n\t\t\t"
                    "script: <MISSING KEY>".expandtabs(2)
                )

            if not stdout:
                raise exception.RequiredConfigMissing(
                    "config:\n\t"
                    "skip_run_when:\n\t\t"
                    "shell:\n\t\t\t"
                    "stdout: <MISSING KEY>".expandtabs(2)
                )

            if not code:
                code = 0
            else:
                code = int(code)

            skip_conditions.append(
                {"shell": (script, stdout, code)}
            )

        # Skip if shell output result exists
        environment = config.get('environment', False)
        if config and environment:
            envkey = environment.get('variable')
            shellvar = environment.get('value')

            if not envkey:
                raise exception.RequiredConfigMissing(
                    "config:\n\t"
                    "skip_run_when:\n\t\t"
                    "environment:\n\t\t\t"
                    "variable: <MISSING KEY>".expandtabs(2)
                )

            if not shellvar:
                raise exception.RequiredConfigMissing(
                    "config:\n\t"
                    "skip_run_when:\n\t\t"
                    "environment:\n\t\t\t"
                    "value: <MISSING KEY>".expandtabs(2)
                )
            skip_conditions.append(
                {"env": (envkey, shellvar)}
            )

        return skip_conditions


class ConfigObject(baseConfig, configProperties):
    """ This class makes YAML configuration
    available as python datastructure. """

    def get_test_set(self, testSet):
        """
        return specific values of interest from a test set

        :return dict:
        """
        ts = {'data': {}}
        # get uri
        try:
            ts['data']['uri'] = testSet['data']['uri']
        except KeyError as err:
            # We're missing the uri aren't we?
            error = ("Error: Missing {err} under testSet item {item}, "
                     "check cannot run.").format(err=err, item=testSet['key'])
            raise Exception("KeyError: " + str(err) + str(error))

        # get ok_http_code
        try:
            ts['data']['ok_http_code'] = testSet['data']['ok_http_code']
        except KeyError as err:
            # We're missing the uri aren't we?
            error = ("Error: Missing {err} under testSet item {item}, "
                     "check cannot run.").format(err=err, item=testSet['key'])
            raise Exception("KeyError: " + str(err) + str(error))

        # get identity_provider
        try:
            ts['data']['identity_provider'] = testSet['data'][
                'identity_provider']
        except KeyError as err:
            # We're missing the uri aren't we?
            error = ("Error: Missing {err} under testSet item {item}, "
                     "check cannot run.").format(err=err, item=testSet['key'])
            raise Exception("KeyError: " + str(err) + str(error))

        return ts

    def get_request_timeout(self, testSet):
        """
        Getter to return a requests.timeout setting.

        Grab local the testSet request timeout else
        defer to global setting.

        :param testSet:   name of the current testset
        :return integer:  for requests.timeout
        """
        config = self.load()
        defined = False
        try:
            timeout = int(testSet['data']['request_timeout'])
            defined = True
        except KeyError, err:
            err = err

        try:
            timeout = int(config['config']['request_timeout'])
            defined = True
        except KeyError, err:
            err = err

        if not defined:
            error = "KeyError configs missing `config: config: {err}:` "
            "structure. (Default timeout missing) Can't continue.".format(
                err=err
            )
            logging.exception(error)
            exit(1)
        else:
            return timeout

    def get_verify_ssl(self, testSet):
        """
        Getter bool around require SSL within requests lib.

        :param testSet:   name of the current testset
        :return bool:
        """
        config = self.load()
        # SSL validation
        defined = False
        try:  # Use SSL local security (if available)
            require_ssl = commons.string2bool(testSet['data'][
                'request_verify_ssl'])
            defined = True
        except:
            pass

        try:  # Try global setting, else require_ssl=True
            if not defined:
                require_ssl = commons.string2bool(
                    config['config']['request_verify_ssl'])
        except:
            require_ssl = True  # No setting, secure by default.

        return require_ssl

    def datatypes_valid(self, check):
        """
        Lints datatypes out of the config file.

        Return true if datatypes ok,
        false if warnings occured.

        :return str:
        """

        exception_string = (
            "Error: Missing {error} under testSet item {test_set}, "
            "check has been skipped."
        )
        for testSet in self._load_checks():
            checkname = testSet['key']
            if checkname == check:
                try:
                    uri = testSet['data']['uri']
                except KeyError as err:
                    error = exception_string.format(
                        error=err,
                        test_set=testSet['key']
                    )
                    logging.error("KeyError: " + str(err) + str(error))
                    return False

                try:
                    testSet['data']['testElements']
                except KeyError as err:
                    error = exception_string.format(
                        error=err,
                        test_set=testSet['key']
                    )
                    logging.error("KeyError: " + str(err) + str(error))
                    return False

                for element in testSet['data']['testElements']:  # for every element
                    try:
                        datatypes = element['datatype'].split(',')
                    except KeyError as err:
                        error = exception_string.format(
                            error=err,
                            test_set=testSet['key']
                        )
                        logging.error("KeyError: " + str(err) + str(error))
                        return False

                    try:
                        datatypes = element['response_type']
                    except KeyError as err:
                        error = exception_string.format(
                            error=err,
                            test_set=testSet['key']
                        )
                        logging.error("KeyError: " + str(err) + str(error))
                        return False

                    try:
                        datatypes = element['key']
                    except KeyError as err:
                        error = exception_string.format(
                            error=err,
                            test_set=testSet['key']
                        )
                        logging.error("KeyError: " + str(err) + str(error))
                        return False

        return True

    def get_datatypes_list(self):
        """
        Used by the discover command to identify a list of valid datatypes

        :return str:
        """
        exception_string = (
            "Error: Missing {error} under testSet item {test_set}, "
            "discover cannot run."
        )

        possible_datatypes = []
        for testSet in self._load_checks():
            checkname = testSet['key']
            try:
                uri = testSet['data']['uri']
            except KeyError as err:
                error = exception_string.format(
                    error=err,
                    test_set=testSet['key']
                )
                raise Exception("KeyError: " + str(err) + str(error))
                return 1

            try:
                testSet['data']['testElements']
            except KeyError as err:
                error = exception_string.format(
                    error=err,
                    test_set=testSet['key']
                )
                logging.error("KeyError: " + str(err) + str(error))
                return 1

            for element in testSet['data']['testElements']:  # for every element
                try:
                    datatypes = element['datatype'].split(',')
                except KeyError as err:
                    error = exception_string.format(
                        error=err,
                        test_set=testSet['key']
                    )
                    raise Exception("KeyError: " + str(err) + str(error))
                    return 1
                for datatype in datatypes:
                    possible_datatypes.append(datatype)

        return str(self._uniq(possible_datatypes))

    def get_log_level(self, debug_level=None):
        """
        Allow user-configurable log-leveling
        """
        try:
            if debug_level == None:
                debug_level = self.config['config']['logging']['level']
        except KeyError as err:
            print("Error: Missing {key} in config under config: loglevel.\n"
                  "Try config: loglevel: Exceptions".format(
                      key=err)
                  )
            print("1")
            exit(1)
        if (debug_level.lower().startswith('err') or
            debug_level.lower().startswith('exc')
            ):
            return logging.ERROR
        elif debug_level.lower().startswith('crit'):
            return logging.CRITICAL
        elif debug_level.lower().startswith('warn'):
            return logging.WARNING
        elif debug_level.lower().startswith('info'):
            return logging.INFO
        elif debug_level.lower().startswith('debu'):
            return logging.DEBUG
        else:
            return logging.ERROR

    def get_logger(self, loglevel):
        """
        Returns a logger instance, used throughout codebase.
        This will set up a logger using syslog or file logging (or both)
        depending on the setting used in configuration.

        This supports two types of logging options
        One by file:
          logging:
            level: debug
            outputs: file
            logfile: /var/log/url_monitor.log
            logformat: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

        One by syslog:
          logging:
            level: debug
            outputs: syslog
            syslog:
                server: 127.0.0.1:514
                socket: tcp
            logformat: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

        You can also enable both by setting outputs with commas.
        """
        try:  # Basic config lint
            self.config['config']['logging']['outputs']
            self.config['config']['logging']['level']
            self.config['config']['logging']['logformat']
        except KeyError, err:
            error = "KeyError missing {key} structure under config "
            "property. Ensure `config: {err}:` is defined. Can't"
            " continue.".format(
                key=err
            )
            logging.exception(error)
            exit(1)

        self.logger = logging.getLogger(packagemacro)
        loglevel = self.get_log_level(loglevel)
        formatter = logging.Formatter(
            self.config['config']['logging']['logformat'])

        log_outputs = self.config['config']['logging']['outputs'].split(',')

        if "file" in log_outputs:
            # Add handler for file outputs
            try:  # Quick validation
                filehandler = logging.FileHandler(
                    self.config['config']['logging']['logfile'])
            except KeyError, err:
                error = "KeyError missing {err} structure under config"
                " property. Ensure `config: {err}:` is defined. Can't "
                "continue.".format(
                    err=err
                )
                exit(1)
            filehandler.setLevel(loglevel)
            self.logger.addHandler(filehandler)
            filehandler.setFormatter(formatter)

        if "syslog" in log_outputs:
            # Add handler for syslog outputs

            try:  # Quick validation
                self.config['config']['logging']['syslog']
                self.config['config']['logging']['syslog']['server']
                self.config['config']['logging']['syslog']['socket']
            except KeyError, err:
                error = "KeyError missing {err} structure under config "
                "property. Ensure `config: {err}:` is defined. "
                "Can't continue.".format(
                    err=err
                )
                logging.exception(error)
                exit(1)
            sysloghost = commons.get_hostport_tuple(
                dport=self.constant_syslog_port,
                dhost=self.config['config']['logging']['syslog']['server']
            )

            socktype = self.config['config']['logging']['syslog']['socket']
            if socktype == "tcp":
                socktype = socket.SOCK_STREAM
            else:
                socktype = socket.SOCK_DGRAM

            try:
                sysloghandler = logging.handlers.SysLogHandler(
                    address=sysloghost, socktype=socktype)
            except TypeError:
                # Py 2.6 doesnt support custom socktypes
                self.logger.warning("Python 2.6 only supports TCP for syslog"
                                    "handling, ignoring syslog socket settin"
                                    "gs.")
                sysloghandler = logging.handlers.SysLogHandler(
                    address=sysloghost)

            try:
                sysloghandler.setLevel(loglevel)
                self.logger.addHandler(sysloghandler)
                sysloghandler.setFormatter(formatter)
            except socket.error, err:
                error = "Syslog error using socket.write() on host "
                "{host}:{port} error: {err}".format(
                    err=err,
                    host=sysloghost[0],
                    port=sysloghost[1]
                )
                logging.exception(error)

        logging.basicConfig(level=loglevel)
        self.logger.info("Logger initialized.")
        return self.logger

    def pre_flight_check(self):
        """ 
        Trys loading all the config objects for zabbix conf. This can be
        expanded to do all syntax checking in this config class, instead of 
        in the program logic as it is mostly right now.

        It is a check class. This should NOT be used for program references.
        (Doesnt use logger for exceptions as it pre-dates logger
        instanciation.)
        """
        # Ensure pidfile defined
        try:
            self.config['config']['pidfile']
        except KeyError:
            logging.error("Error: `pidfile` not defined in yaml config")
            exit(1)

        # Ensure base config elements exist.
        try:
            self.config['config']
        except KeyError, err:
            error = "KeyError configs missing `zabbix: {key}` structure."
            " Can't continue.".format(
                key=err
            )
            logging.exception(error)
            exit(1)

        try:
            self.config['config']['zabbix']
        except KeyError, err:
            error = "KeyError configs missing `zabbix: {key}` structure."
            " Can't continue.".format(
                key=err
            )
            logging.exception(error)
            exit(1)

        try:
            self.config['config']['zabbix']['server']
            self.config['config']['zabbix']['host']
            self.config['config']['zabbix']['item_key_format']
            self.config['config']['zabbix']['checksummary_key_format']
        except KeyError, err:
            error = "KeyError configs missing `config: zabbix: {key}:`"
            " structure. Can't continue.".format(
                key=err
            )
            logging.exception(error)
            exit(1)

        # Ensure identity items exist
        try:
            self.config['config']['identity_providers']
        except KeyError, err:
            error = "KeyError configs missing `config: config: {key}:`"
            " structure. (Identity Providers) Can't continue.".format(
                key=err)
            logging.exception(error)
            exit(1)

        try:
            for provider in self.identity_providers:
                provider
        except AttributeError, err:
            error = "KeyError configs missing {key} structure in `config: "
            "identity_providers`. Can't continue.".format(
                key=err)
            logging.exception(error)
            exit(1)

        for provider in self.identity_providers:
            provider
            for module, kwargs in self.config['config'][
                    'identity_providers'][provider].iteritems():
                module.split('/')
                for kwarg in kwargs:
                    kwarg

        self.logger.info("Pre-flight config test OK")


if __name__ == "__main__":
    x = ConfigObject()
    x.load_yaml_file(config=None)
    a = x.checks
    print(a)
    print(x.get_datatypes_list())
