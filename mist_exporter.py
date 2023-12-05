#!/usr/bin/env python3

"""Mist API Prometheus exporter.

This script will export device metrics of MIST Access Points from the MIST API.
The format of the exported metrics can be used in Prometheus.
This script is well suited to be called from exporter_exporter.

Last Change: 04.12.2023 M. Lueckert

"""

import sys
import argparse
import requests as req
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import re

def main(arguments):
    try:
        parser = argparse.ArgumentParser(
            description=__doc__,
            formatter_class=argparse.RawDescriptionHelpFormatter)
        parser.add_argument('--api_token', help="API Token", required=True)
        parser.add_argument('--org_id', help="Organisation ID", required=True)
        parser.add_argument('--site_name_filter',
                            help="Filter Sites by Name (Regex)", default=".*")
        parser.add_argument('--log_fullpath',
                            help="Location of logfile. Will be rotated after 8hours with 5 backups.", default="mist_exporter.log")
        parser.add_argument(
            '--debug', help="Set loglevel to debug. Prints out a lot of json.", action="store_true")
        parser.add_argument('--baseurl', help="API URL if not EU",
                            default="https://api.eu.mist.com/api/v1")

        args = parser.parse_args(arguments)
        api_token = args.api_token
        org_id = args.org_id
        baseurl = args.baseurl
        site_name_filter = args.site_name_filter
        log_fullpath = args.log_fullpath
        logformat = "%(asctime)s:%(levelname)s:%(funcName)s:%(message)s"
        handler = TimedRotatingFileHandler(
            filename=log_fullpath, when="h", interval=8, backupCount=5, encoding="utf-8")
        logging.basicConfig(handlers=[handler], level=logging.INFO,
                            format=logformat)
        if args.debug:
            logging.getLogger().setLevel(logging.DEBUG)
            for myhandler in logging.getLogger().handlers:
                myhandler.setLevel(logging.DEBUG)
        logging.info("Mist Exporter starting")
        headers = {"Authorization": f"Token {api_token}",
                   'Content-Type': 'application/json'}
        sites = get_sites(baseurl, org_id, site_name_filter, headers)
        #self_info = get_self(baseurl, headers)
        siteids = [x['id'] for x in sites]
        devices = get_devices(baseurl, siteids, headers)
        metrics = get_device_metrics(devices)
        metrics.append("mist_exporter_status 1")
        print("\n".join(metrics))
    except:
        print("mist_exporter_status 0")
        logging.exception('')

    logging.info("Mist Exporter finished")


def get_sites(baseurl, org_id, site_filter, headers) -> list:
    """Retrieves sites from MIST API.

    Retrieves sites from the API. Can be filtered with site_filter.

    Args:
        baseurl: The baseurl of the MIST API.
        org_id: The organisation ID.
        site_filter: A valid regex string. If the returned sitename
            matches this regex it will be considered for further processing.
        headers: The authentication headers required for the API.

    Returns:
        A list with the filtered json object of the sites.
    """
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


def get_devices(baseurl, siteids: list, headers) -> list:
    """Retrieves devices from MIST API.

    Retrieves devices from the API.

    Args:
        baseurl: The baseurl of the MIST API.
        siteids: List with all siteids to look for devices.
        headers: The authentication headers required for the API.

    Returns:
        A list with json object of all device details.
    """
    json_list = []
    for siteid in siteids:
        url = f"{baseurl}/sites/{siteid}/stats/devices"
        response = req.get(url, headers=headers)
        json_list = json_list + response.json()
    logging.debug(str(json_list))
    return json_list


def get_self(baseurl, headers) -> json:
    url = f"{baseurl}/self"
    response = req.get(url, headers=headers)
    return response.json()


def format_metric(metric_name: str, labeldict: dict, value: str) -> str:
    """Creates a Prometheus metric string.

    Returns a string in Prometheus format with metric, labels and value

    Args:
        metric_name: The metric name.
        labeldic: Dictionary with multiple label:labelvalue pairs.
        value: The value of the metric

    Returns:
        A valid Prometheus metric string
        mist_device_info{hostname="testdevice"} 255
    """
    string_labels = ""
    if labeldict:
        formatted_labels = [
            f'{x[0].lower()}="{x[1]}"' for x in labeldict.items()]
        string_labels = ", ".join(formatted_labels)
    time_series = f"{metric_name.lower()}{{{string_labels}}} {value}"
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


def get_device_metrics(devices: dict) -> list:
    """Retrieves the defined metrics from the device json.

    If a metric is not found we log it and add a value of 0 (maybe not ideal in all cases).
    To add new metrics for devices add them to the metric_list variable

    Args:
        devices: json with all devices where we want the metrics.

    Returns:
        List will all metric strings in Prometheus format.
    """
    count = len(devices)
    logging.info(f"Getting information for {count} devices from API")
    metrics_list = []
    metrics_list.append("# HELP mist_device Mist device metrics")
    for device in devices:
        device_name = get_value_from_path(device, "name")
        #The metric_list dict has the following format
        #[metric_name, value from json, {dict with labels}]
        metric_list = [
            ["mist_device_uptime_seconds",
                get_value_from_path(device, "uptime"), {}],
            ["mist_device_status", get_value_from_path(device, "status"), {}],
            ["mist_device_last_seen_seconds", get_value_from_path(device, "last_seen"), {}],
            ["mist_device_num_clients", get_value_from_path(
                device, "num_clients"), {}],
            ["mist_device_port_stat_tx_bytes", get_value_from_path(
                device, "port_stat.eth0.tx_bytes"), {"ifName": "eth0"}],
            ["mist_device_port_stat_rx_bytes", get_value_from_path(
                device, "port_stat.eth0.rx_bytes"), {"ifName": "eth0"}],
            ["mist_device_radio_stat_util_all", get_value_from_path(
                device, "radio_stat.band_6.util_all"), {"band": "6"}],
            ["mist_device_radio_stat_util_all", get_value_from_path(
                device, "radio_stat.band_5.util_all"), {"band": "5"}],
            ["mist_device_radio_stat_util_all", get_value_from_path(
                device, "radio_stat.band_24.util_all"), {"band": "24"}],
        ]

        # These labels will be added to all metrics
        all_labels_dict = {
            "hostname": device_name.upper()
        }
        # These labels will be added to the device_info metric just for information purposes
        details_labels_dict = {
            "serial": get_value_from_path(device, "serial"),
            "model": get_value_from_path(device, "model"),
            "hw_rev": get_value_from_path(device, "hw_rev"),
        }
        metrics_list.append(format_metric(
            "mist_device_info", {**details_labels_dict, **all_labels_dict}, 1))
        # Merge of metrics and labels
        for item in metric_list:
            name = item[0]
            value = item[1]
            device_labels_dict = item[2]
            labels_merged = {**all_labels_dict, **device_labels_dict}
            if value != "False":
                value = convert_string_value_to_bool(value)
            else:
                value = 0
                logging.warning(
                    f'{device_name} - Metric {name} not found for device. Setting 0 value.')
            metrics_list.append(format_metric(name, labels_merged, value))
    device_count = len(devices)
    metric_count = len(metrics_list)
    logging.info(
        f"Got {len(metrics_list)} metrics for {device_count} device(s) from API")
    metrics_list.append(format_metric(
        "mist_device_total_count", [], device_count))
    metrics_list.append(format_metric(
        "mist_device_metric_total_count", [], metric_count))
    return metrics_list


def convert_string_value_to_bool(metric_value: str):
    """Map string values to bool.

    Some string values from the API needs to be mapped to bool because we
    want to use them as values for our metric.

    Args:
        metric_name: String metric value (e.g. connected).

    Returns:
        Mapped bool for the value defined
    """
    if(metric_value in ["connected"]):
        return 0
    elif(metric_value in ["disconnected"]):
        return 1
    else:
        return metric_value


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
