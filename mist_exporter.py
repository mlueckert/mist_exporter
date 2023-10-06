#!/usr/bin/env python3

"""Mist API Prometheus exporter.

"""

import sys
import argparse
import requests as req
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import re

def main(arguments):
    logging.info("Mist Exporter starting")
    try:
        parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.RawDescriptionHelpFormatter)
        parser.add_argument('--api_token', help="API Token", required=True)
        parser.add_argument('--org_id', help="Organisation ID", required=True)
        parser.add_argument('--site_name_filter',
                            help="Filter Sites by Name (Regex)", default=".*")
        parser.add_argument('--log_fullpath',
                            help="Location of logfile. Will be rotated after 1day with 5 backups.", default="mist_exporter.log")
        parser.add_argument(
            '--debug', help="Set loglevel to debug. Prints out a lot of json.", action="store_true")
        parser.add_argument('--baseurl', help="API URL if not EU",
                            default="https://api.eu.mist.com/api/v1")

        args = parser.parse_args(arguments)
        api_token = args.api_token
        org_id = args.org_id
        baseurl = args.baseurl
        site_name_filter = args.site_name_filter
        if args.debug:
            logging.getLogger().setLevel(logging.DEBUG)
            for myhandler in logging.getLogger().handlers:
                myhandler.setLevel(logging.DEBUG)

        headers = {"Authorization": f"Token {api_token}",
                'Content-Type': 'application/json'}
        sites = get_sites(baseurl, org_id, site_name_filter, headers)
        self_info = get_self(baseurl, headers)
        siteids = [x['id'] for x in sites]
        devices = get_devices(baseurl, siteids, headers)
        metrics = get_device_metrics(devices)
        metrics.append("mist_exporter_status 1")
        print("\n".join(metrics))
    except:
        print("mist_exporter_status 0")
        logging.exception('')

    logging.info("Mist Exporter finished")

def get_sites(baseurl, org_id, site_filter, headers) -> json:
    url = f"{baseurl}/orgs/{org_id}/sites"
    response = req.get(url, headers=headers)
    sites = response.json()
    site_count = len(sites)
    sites_filtered = []
    for site in sites:
        if re.match(site_filter, site["name"]):
            sites_filtered.append(site)
    site_count_filtered = len(sites_filtered)
    logging.info(
        f"Got {site_count} site(s) from API. {site_count_filtered} site(s) after filtering with filter {site_filter}")
    logging.debug(str(sites_filtered))
    return sites_filtered


def get_devices(baseurl, siteids, headers) -> list:
    json_list = []
    for siteid in siteids:
        url = f"{baseurl}/sites/{siteid}/stats/devices"
        response = req.get(url, headers=headers)
        json_list = json_list + response.json()
    # https://api.eu.mist.com/api/v1/sites/:site_id/stats/devices
    logging.debug(str(json_list))
    return json_list


def get_self(baseurl, headers) -> json:
    url = f"{baseurl}/self"
    response = req.get(url, headers=headers)
    return response.json()


def format_metric(name: str, labeldict: dict, value: str) -> str:
    string_labels = ""
    if labeldict:
        formatted_labels = [
            f'{x[0].lower()}="{x[1]}"' for x in labeldict.items()]
        string_labels = ", ".join(formatted_labels)
    time_series = f"{name.lower()}{{{string_labels}}} {value}"
    return time_series


def get_value_from_path(dictionary, parts):
    """ extracts a value from a dictionary using a dotted path string """

    if type(parts) is str:
        parts = parts.split('.')

    try:
        if len(parts) > 1:
            return get_value_from_path(dictionary[parts[0]], parts[1:])
        return str(dictionary[parts[0]]).lower()
    except KeyError:
        return "False"


def get_device_metrics(devices: dict):
    count = len(devices)
    logging.info(f"Getting information for {count} devices from API")
    metrics_list = []
    metrics_list.append("# HELP mist_device Mist device metrics")
    for device in devices:
        device_name = get_value_from_path(device, "name")
        # TODO move eth0/band to labels
        # TODO change status 0 -> 1
        metric_dict = {
            "mist_device_uptime_seconds": get_value_from_path(device, "uptime"),
            "mist_device_status": get_value_from_path(device, "status"),
            "mist_device_num_clients": get_value_from_path(device, "num_clients"),
            "mist_device_port_stat_eth0_tx_bytes": get_value_from_path(device, "port_stat.eth0.tx_bytes"),
            "mist_device_port_stat_eth0_rx_bytes": get_value_from_path(device, "port_stat.eth0.rx_bytes"),
            "mist_device_radio_stat_band_6_util_all": get_value_from_path(device, "radio_stat.band_6.util_all"),
            "mist_device_radio_stat_band_5_util_all": get_value_from_path(device, "radio_stat.band_5.util_all"),
            "mist_device_radio_stat_band_24_util_all": get_value_from_path(device, "radio_stat.band_24.util_all"),
            "mist_device_last_seen_seconds": get_value_from_path(device, "last_seen"),
        }

        all_labels_dict = {
            "hostname": device_name.upper()
        }
        details_labels_dict = {
            "serial": get_value_from_path(device, "serial"),
            "model": get_value_from_path(device, "model"),
            "hw_rev": get_value_from_path(device, "hw_rev"),
        }
        metrics_list.append(format_metric(
            "mist_device_info", {**details_labels_dict,**all_labels_dict}, 1))
        for name, value in metric_dict.items():
            if value != "False":
                value = convert_string_value_to_bool(value)
                metrics_list.append(format_metric(name, all_labels_dict, value))
            else:
                logging.warning(
                    f'{device_name} - Metric {name} not found for device.')
    device_count = len(devices)
    metric_count = len(metrics_list)
    logging.info(
        f"Got {len(metrics_list)} metrics for {device_count} device(s) from API")
    metrics_list.append(format_metric("mist_device_total_count", [], device_count))
    metrics_list.append(format_metric(
        "mist_device_metric_total_count", [], metric_count))
    return metrics_list


def convert_string_value_to_bool(metric_value):
    if(metric_value in ["connected"]):
        return 0
    elif(metric_value in ["disconnected"]):
        return 1
    else:
        return metric_value

if __name__ == '__main__':
    handler = TimedRotatingFileHandler(
        filename="mist_exporter.log", when="d", interval=1, backupCount=5, encoding="utf-8")
    logging.basicConfig(handlers=[handler], level=logging.INFO,
                        format="%(asctime)s:%(levelname)s:%(funcName)s:%(message)s")
    sys.exit(main(sys.argv[1:]))
