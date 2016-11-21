#!/usr/bin/python
# -*- coding: utf-8 -*-
import logging
import socket
import struct
import time

try:
    import json
except:
    import simplejson as json


# TODO: fill in documentation block below
class Metric(object):
    """

    """
    def __init__(self, host, key, value, clock=None):
        self.host = host
        self.key = key
        self.value = value
        self.clock = clock

    def __repr__(self):
        if self.clock is None:
            return 'Metric(%r, %r, %r)' % (self.host, self.key, self.value)

        return 'Metric(%r, %r, %r, %r)' % (
            self.host, self.key, self.value, self.clock
        )


# TODO: fill in documentation block below
def send_to_zabbix(logger, metrics, zabbix_host='127.0.0.1',
                   zabbix_port=10051, timeout=15):
    """
    Send set of metrics to Zabbix server.

    :param: logger:
    :param metrics:
    :param zabbix_host:
    :param zabbix_port:
    :param timeout:
    :return:
    """

    jason_dump = json.dumps
    # Zabbix has very fragile JSON parser, and we cannot use json to dump
    # whole packet
    metrics_data = []
    for metric in metrics:
        # TODO: should time.time be time.now()?
        clock = metric.clock or time.time()
        metrics_data.append(
            ('\t\t{\n'
             '\t\t\t"host":%s,\n'
             '\t\t\t"key":%s,\n'
             '\t\t\t"value":%s,\n'
             '\t\t\t"clock":%s}').format(
                host=jason_dump(metric.host),
                key=jason_dump(metric.key),
                value=jason_dump(metric.value),
                clock=clock))
    json_data = ('{\n'
                 '\t"request":"sender data",\n'
                 '\t"data":[\n%s]\n'
                 '}') % (',\n'.join(metrics_data))

    data_len = struct.pack('<Q', len(json_data))
    packet = 'ZBXD\1' + data_len + json_data
    try:
        zabbix = socket.socket()
        zabbix.connect((zabbix_host, zabbix_port))
        zabbix.settimeout(timeout)
        # send metrics to zabbix
        logger.debug('Sent payload: %s' % str(packet))
        zabbix.sendall(packet)
        # get response header from zabbix
        resp_hdr = _recv_all(zabbix, 13)
        if not resp_hdr.startswith('ZBXD\1') or len(resp_hdr) != 13:
            logger.error('Wrong zabbix response')
            return False
        resp_body_len = struct.unpack('<Q', resp_hdr[5:])[0]
        # get response body from zabbix
        resp_body = zabbix.recv(resp_body_len)
        resp = json.loads(resp_body)
        logger.debug('Got response from Zabbix: %s' % resp)
        logger.info(resp.get('info'))
        if resp.get('response') != 'success':
            logger.error('Got error from Zabbix: %s', resp)
            return False
        return True
    except socket.timeout as e:
        logger.error("zabbix timeout: " + str(e))
        return False
    except Exception as e:
        logger.exception('Error while sending data to Zabbix: ' + str(e))
        return False
    finally:
        zabbix.close()


logger = logging.getLogger('zbxsender')


def _recv_all(sock, count):
    """

    :param sock:
    :param count:
    :return:
    """
    buf = ''
    while len(buf) < count:
        chunk = sock.recv(count - len(buf))
        if not chunk:
            return buf
        buf += chunk
    return buf


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    send_to_zabbix([Metric('localhost', 'bucks_earned', 99999)],
                   'localhost', 10051)
