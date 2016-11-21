#!/usr/bin/python
# -*- coding: utf-8 -*-

import subprocess
from os import environ

import requests
from facter import Facter
from requests.auth import HTTPBasicAuth
from requests.auth import HTTPDigestAuth
from requests_oauthlib import OAuth1

from jpath import jpath


def run_command(command):
    """
    Runs a command, returns retval and stdout as tuple

    """

    child = subprocess.Popen(command, stdout=subprocess.PIPE)
    streamdata = child.communicate()[0]

    rc = child.returncode
    return (rc, streamdata)


# TODO: fill in documentation block below
def skip_on_external_condition(logging, condition, argv):
    """
    Checks and skips execution if a shell command, env var, or puppet fact
    returns true if we should skip

    :param logging:
    :param condition:
    :param argv:
    :return:
    """
    skip_summary = ", skipping execution due to config option."
    if condition == "facter":
        facter_binpath = argv[0]
        fact_condition = argv[1]
        value_condition = argv[2]

        facter = Facter(facter_path=facter_binpath)
        real_value = facter.get(fact_condition)
        if value_condition == real_value:
            logging.warn(
                "Warning: {bin} value {{:{fact} => \"{val}\"}},"
                " skipping execution due to config option.".format(
                    bin=facter_binpath,
                    fact=fact_condition,
                    val=value_condition,
                )
            )
            return True

    elif condition == "shell":
        script = argv[0]
        stdout = argv[1]
        expect_code = argv[2]

        rc, data = run_command(script)

        if data.strip() == stdout:
            logging.warn(
                "Warning: shell `{sh}` stdout was `{val}`{fin}".format(
                    sh=script,
                    val=stdout,
                    fin=skip_summary,
                )
            )
            return True
        if expect_code == rc:
            logging.warn(
                "Warning: shell `{sh}` return code was `{code}`{fin}".format(
                    sh=script,
                    code=expect_code,
                    fin=skip_summary
                )
            )
            return True
    elif condition == "env":
        shellvar = argv[0]
        expected_value = argv[1]

        if environ.get(shellvar) == expected_value:
            logging.warn(
                "Warning: Bash environment has export "
                "{env}=\"{val}\"`{fin}".format(
                        env=shellvar,
                        val=expected_value,
                        fin=skip_summary
                    )
            )
            return True
    return False


# TODO: fill in documentation block below
def get_hostport_tuple(dport, dhost):
    """
    Tool to take a hostport combination 'localhost:22' string
    and return a tuple ('localhost', 22). If no : seperator
    is given then assume a default port passed as argv1

    :param dport:
    :param dhost:
    :return:
    """
    # Detect if port is designated
    if ":" in dhost:
        host = dhost.split(':')[0]
        port = int(dhost.split(':')[1])
        return host, port
    else:  # Use default port
        return dhost, dport


# TODO: fill in documentation block below
def string_to_bool(input_string):
    """
    Tries to return a boolean from a string input if possible,
    else it just returns the original item, allegedly a string.

    :param input_string:
    :return:
    """

    return input_string.lower() in ['t', 'true', '1']


# TODO: fill in documentation block below
def omnipath(data_object, type, element, throw_error_or_mark_none='none'):
    """
    Used to pull path expressions out of json or java path.

    :param data_object:
    :param type:
    :param element:
    :param throw_error_or_mark_none:
    :return:
    """
    value = None
    if type == 'json':
        try:
            value = jpath(data_object, element['jsonvalue'])

        except:
            if throw_error_or_mark_none == 'none':
                value = None
            else:
                raise KeyError
    if type == 'xml':
        raise NotImplementedError('Be the first to implement xpath.')

    metric = value
    return metric


class WebCaller(object):
    """
    Performs web functions for API's we're running check"s on
    """

    # TODO: fill in documentation block below
    def __init__(self, logging):
        """
        Initialize web instance.
        Bring logging instance in.
        Set session.auth and session_headers to none by default
        :param logging:
        """
        self.logging = logging

        self.session = None
        self.session_headers = None

    # TODO: fill in documentation block below
    def auth(self, config, identity_provider):
        """
        Start a requests session with this instance.
        This is also where we apply authentication schemes.
        :param config:
        :param identity_provider:
        :return:
        """
        identity_providers = config['identity_providers']
        try:
            identity_provider = identity_providers[identity_provider]
            auth_kwargs = identity_provider.values()[0]
        except KeyError as err:
            error = ("KeyError {err} defined in test_set as identity_provider "
                     "but is undeclared in identity_providers!").format(err=err)
            self.logging.exception(error)

        # If provider is undefined, we get TypeError
        try:
            provider_name = str([x for x in identity_provider][0]).lower()
        except TypeError:
            provider_name = "none"

        self.session = requests.Session()
        self.session_headers = {
            'content-type': 'application/json',
            'accept': 'application/json',
            'user-agent': 'python/url_monitor (A zabbix monitoring plugin)'
        }
        if provider_name == "none":
            self.session.auth = None

        elif provider_name == "httpbasicauth":
            self.session.auth = HTTPBasicAuth(**auth_kwargs)

        elif provider_name == "httpdigestauth":
            self.session.auth = HTTPDigestAuth(**auth_kwargs)

        elif provider_name == "oauth1":
            self.session.auth = OAuth1(**auth_kwargs)

        else:
            # We must assume we want to load in the format of
            # requests_python_module/requestAuthClassname from the config entry
            # Split the / to determine import statements t.
            try:
                module_strname = [
                    x for x in identity_provider
                    ][0].split('/')[0]
                class_strname = [x for x in identity_provider][
                    0].split('/')[1]
            except IndexError as err:
                error = (
                    "IndexError {err} {provider_name} is incomplete "
                    "missing '/' char to seperate Module_Name from "
                    "Class_Namebut is undeclared in identity_providers!").format(
                        err=err,
                        provider_name=provider_name
                    )
                self.logging.exception(error)

            # Try to import the specified module
            try:
                _module = __import__(module_strname)
            except ImportError as err:
                error = (
                    "{module_strname}/{class_strname} might be an invalid "
                    "module/class pairing at {module_strname}"
                ).format(
                    module_strname=module_strname,
                    class_strname=class_strname
                )
                self.logging.exception("ImportError: " + str(err) + str(error))

            # And try to reference a class instance
            try:
                external_requests_auth_class = getattr(_module, class_strname)
            except AttributeError as err:
                error = (
                    "{module_strname}.{class_strname} might be an invalid "
                    "class name at {class_strname}"
                ).format(
                    module_strname=module_strname,
                    class_strname=class_strname
                )
                self.logging.exception(
                    "AttributeError: " + str(err) + str(error))

            # Set the external auth handler.
            self.session.auth = external_requests_auth_class(**auth_kwargs)

            # Filters possibly exposing kwargs from debug logs
            LOGGING_BLACKLIST = [
                'password',
                'extra_auth_data',
                'oauthv1-application-secret',
                'oauthv1-token_secet'
            ]
            filtered_kwargs = {}
            for potential_breach, unfiltered_input in auth_kwargs.iteritems():
                if potential_breach in LOGGING_BLACKLIST:
                    filtered_kwargs[potential_breach] = "****FILTERED****"
                else:  # not in blacklist
                    filtered_kwargs[potential_breach] = unfiltered_input

            # Debug message
            self.logging.debug("Spawn session.auth {pyobject}"
                               " with kwargs {arglst} ".format(
                pyobject=self.session.auth,
                arglst=filtered_kwargs
            )
            )

    # TODO: fill in documentation block below
    def run(self, config, url, verify, expected_http_status, identity_provider,
            timeout):
        """
        Executes a http request to gather the data.
        expected_http_status can be a list of expected codes.

        :param config:
        :param url:
        :param verify:
        :param expected_http_status:
        :param identity_provider:
        :param timeout:
        :return:
        """

        self.auth(config, identity_provider)

        try:
            request = self.session.get(
                url,
                headers=self.session_headers,
                verify=verify,
                timeout=timeout
            )
            self.logging.debug(
                "Spawn request {pyobject} url={url} headers={head}".format(
                    pyobject=request,
                    head=self.session_headers,
                    url=url
                )
            )
        except requests.exceptions.ConnectTimeout as e:
            err = "requests.exceptions.ConnectTimeout: {e}".format(e=e)
            self.logging.exception(err)
            return False

        except requests.exceptions.RequestException as e:
            err = "requests.exceptions.RequestException: {e}".format(e=e)
            self.logging.exception(err)
            return False

        except:
            err = "Unhandled requests exception occured during web_request()"
            self.logging.exception(err)
            return False

        # Turns comma seperated string from config to a list, then lower it
        expected_codes = [c.lower() for c in expected_http_status.split(',')]

        # Cast response code into a list
        resp_code = str(request.status_code).split()

        if 'any'.lower() in expected_codes:
            # Allow any HTTP code ranges within RFC 2616 - Hypertext Transfer
            # Protocol -- HTTP/1.1
            expected_codes.remove('any')
            codes = [
                range(100, 104),  # Informational
                range(200, 227),  # Success!
                range(300, 309),  # Redirection
                range(400, 452),  # Client Error
                range(500, 511),  # Internal Error
            ]
            for code in codes:
                expected_codes += code
            expected_codes = map(str, expected_codes)

        # filter returns empty if code not found, returns found expected_codes
        # if they are found.
        valid_response_code = filter(lambda item: any(
            x in item for x in resp_code), expected_codes)

        if not valid_response_code:
            error = "Bad HTTP response."
            "Expected {expect} recieved {got}".format(
                expect=expected_codes,
                got=resp_code
            )
            self.logging.error(error)
            return False
        return request
