#!/usr/bin/env python3

"""Mist API Prometheus exporter.

This script will export device metrics of MIST Access Points from the MIST API.
The format of the exported metrics can be used in Prometheus.
This script is well suited to be called from exporter_exporter.

Last Change: 22.01.2024 M. Lueckert

"""

import sys
import argparse
import requests as req
import urllib3
import json
import logging
from logging.handlers import RotatingFileHandler
import re


def main(arguments):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--api_token", help="API Token", required=True)
    parser.add_argument("--org_id", help="Organisation ID", required=True)
    parser.add_argument(
        "--site_name_filter", help="Filter Sites by Name (Regex)", default=".*"
    )
    parser.add_argument(
        "--ignore_ssl",
        help="Ignore self signed certificates in chain.",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--log_fullpath",
        help="Location of logfile. Will be rotated 5MB with 5 backups.",
        default="mist_exporter.log",
    )
    parser.add_argument(
        "--debug",
        help="Set loglevel to debug. Prints out a lot of json.",
        action="store_true",
    )
    parser.add_argument(
        "--baseurl", help="API URL if not EU", default="https://api.eu.mist.com/api/v1"
    )
    args = parser.parse_args(arguments)

    try:
        api_token = args.api_token
        org_id = args.org_id
        baseurl = args.baseurl
        site_name_filter = args.site_name_filter
        log_fullpath = args.log_fullpath
        logformat = "%(asctime)s:%(levelname)s:%(funcName)s:%(message)s"
        handler = RotatingFileHandler(
            filename=log_fullpath, maxBytes=(5242880), backupCount=5, encoding="utf-8"
        )
        logging.basicConfig(handlers=[handler], level=logging.INFO, format=logformat)
        if args.debug:
            logging.getLogger().setLevel(logging.DEBUG)
            for myhandler in logging.getLogger().handlers:
                myhandler.setLevel(logging.DEBUG)
        logging.info("Mist Exporter starting")
        if args.ignore_ssl:
            logging.info("Disable SSL verification")
            urllib3.disable_warnings()
            verify = False
        else:
            verify = True
        headers = {
            "Authorization": f"Token {api_token}",
            "Content-Type": "application/json",
        }

        sites = get_sites(baseurl, org_id, site_name_filter, headers, verify)
        # self_info = get_self(baseurl, headers)
        siteids = [x["id"] for x in sites]
        devices = get_devices(baseurl, siteids, headers, verify)
        device_metrics_dict = get_device_metrics(devices)
        edge_metrics_dict = get_edge_metrics(
            f"{baseurl}/orgs/{org_id}", headers, verify
        )
        metrics = device_metrics_dict + edge_metrics_dict
        metrics.append("mist_exporter_status 1")
        print("\n".join(metrics))
        logging.info("All went fine. Prometheus metrics printed to stdout.")

    except Exception as e:
        print("mist_exporter_status 0")
        logging.exception("An error occured. See error details.")

    logging.info("Mist Exporter finished")


def test_status_code(response):
    """
    Raises an exception if the response status code is not 200 (OK).

    Args:
        response: The response object from an API call (e.g., requests.Response).  Must have a `status_code` and `reason` attribute.

    Raises:
        Exception: If the status code is not 200. The exception message includes the status code and reason.
    """
    if response.status_code != 200:
        message = f"MIST API returned an error {response.status_code} {response.reason}"
        raise Exception(message)


def get_sites(baseurl, org_id, site_filter, headers, verify) -> list:
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
    response = req.get(url, headers=headers, verify=verify)
    test_status_code(response)
    sites = response.json()
    site_count = len(sites)
    sites_filtered = []
    for site in sites:
        if re.match(site_filter, site["name"]):
            sites_filtered.append(site)
    site_count_filtered = len(sites_filtered)
    logging.info(
        f"Got {site_count} site(s) from API. {site_count_filtered} site(s) after filtering with filter {site_filter}"
    )
    logging.debug(str(sites_filtered))
    return sites_filtered


def get_edge_metrics(baseurl, headers, verify) -> list:
    """Retrieves edge device stats from MIST API.

    Retrieves edge device stats from the API.

    Args:
        baseurl: The baseurl of the MIST API.
        siteids: List with all siteids to look for devices.
        headers: The authentication headers required for the API.

    Returns:
        A list with json object of all device details.
    """
    devices = []
    url = f"{baseurl}/stats/mxedges"
    response = req.get(url, headers=headers, verify=verify)
    test_status_code(response)
    devices = response.json()
    logging.debug(str(devices))
    metrics_list = []
    for device in devices:
        device_name = get_value_from_path(device, "name")
        if not device_name:
            continue
        metric_list = [
            ["mist_edge_uptime_seconds", get_value_from_path(device, "uptime"), {}],
            ["mist_edge_status", get_value_from_path(device, "status"), {}],
            [
                "mist_edge_cpu_usage_pct",
                get_value_from_path(device, "cpu_stat.usage"),
                {},
            ],
            [
                "mist_edge_memory_usage_pct",
                get_value_from_path(device, "memory_stat.usage"),
                {},
            ],
            [
                "mist_edge_temperatures_degree",
                get_value_from_path(device, "sensor_stat.temperatures.CPU1.degree"),
                {"component": "cpu1"},
            ],
            [
                "mist_edge_temperatures_degree",
                get_value_from_path(device, "sensor_stat.temperatures.CPU2.degree"),
                {"component": "cpu2"},
            ],
            [
                "mist_edge_temperatures_degree",
                get_value_from_path(device, "sensor_stat.temperatures.Exhaust.degree"),
                {"component": "exhaust"},
            ],
            [
                "mist_edge_temperatures_degree",
                get_value_from_path(device, "sensor_stat.temperatures.Inlet.degree"),
                {"component": "inlet"},
            ],
            [
                "mist_edge_psu_redundancies",
                get_psu_redundancy(device),
                {
                    "redundancy": get_value_from_path(
                        device, "sensor_stat.redundancies.PS.state"
                    )
                },
            ],
            [
                "mist_edge_fan_redundancies",
                get_fan_redundancy(device),
                {
                    "redundancy": get_value_from_path(
                        device, "sensor_stat.redundancies.Fan.state"
                    )
                },
            ],
        ]
        # These labels will be added to all metrics
        all_labels_dict = {"hostname": device_name.upper()}
        # These labels will be added to the device_info metric just for information purposes
        details_labels_dict = {
            "serial": get_value_from_path(device, "serial_no"),
            "model": get_value_from_path(device, "model"),
        }
        metrics_list.append(
            format_metric(
                "mist_edge_info", {**details_labels_dict, **all_labels_dict}, 1
            )
        )
        # Merge of metrics and labels
        for item in metric_list:
            name = item[0]
            value = item[1]
            device_labels_dict = item[2]
            metric_not_found_dict = {}
            if value != "False":
                value = map_string_value_to_int(value)
            else:
                value = 0
                metric_not_found_dict = {"error": "Metric not found"}
                logging.debug(
                    f"{device_name} - Metric {name} not found for device. Setting 0 value."
                )
            labels_merged = {
                **all_labels_dict,
                **device_labels_dict,
                **metric_not_found_dict,
            }
            metrics_list.append(format_metric(name, labels_merged, value))
    device_count = len(devices)
    metric_count = len(metrics_list)
    logging.info(
        f"Got {metric_count} metrics for {device_count} edge device(s) from API"
    )
    metrics_list.append(format_metric("mist_edge_total_count", [], device_count))
    metrics_list.append(format_metric("mist_edge_metric_total_count", [], metric_count))
    return metrics_list


def get_psu_redundancy(device_json):
    value = get_value_from_path(device_json, "sensor_stat.redundancies.PS.state")
    if value == "fullyredundant":
        return 0
    else:
        return 1


def get_fan_redundancy(device_json):
    value = get_value_from_path(device_json, "sensor_stat.redundancies.Fan.state")
    if value == "fullyredundant":
        return 0
    else:
        return 1


def get_devices(baseurl, siteids: list, headers, verify) -> list:
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
        response = req.get(url, headers=headers, verify=verify)
        test_status_code(response)
        rjson = response.json()
        if response.status_code != 200:
            logging.warning(
                f'Received http error {response.status_code} while retrieving device details for siteid "{siteid}". Json response: {str(rjson)}'
            )
        else:
            json_list = json_list + rjson
    logging.debug(str(json_list))
    return json_list


def get_self(baseurl, headers, verify) -> json:
    url = f"{baseurl}/self"
    response = req.get(url, headers=headers, verify=verify)
    test_status_code(response)
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
        formatted_labels = [f'{x[0].lower()}="{x[1]}"' for x in labeldict.items()]
        string_labels = ", ".join(formatted_labels)
    time_series = f"{metric_name.lower()}{{{string_labels}}} {value}"
    return time_series


def get_value_from_path(dictionary, parts):
    """extracts a value from a dictionary using a dotted path string"""
    if type(parts) is str:
        parts = parts.split(".")
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
        if not device_name:
            continue
        # The metric_list dict has the following format
        # [metric_name, value from json, {dict with labels}]
        metric_list = [
            ["mist_device_uptime_seconds", get_value_from_path(device, "uptime"), {}],
            ["mist_device_status", get_value_from_path(device, "status"), {}],
            [
                "mist_device_power_constrained",
                get_value_from_path(device, "power_constrained"),
                {},
            ],
            [
                "mist_device_last_seen_seconds",
                get_value_from_path(device, "last_seen"),
                {},
            ],
            ["mist_device_num_clients", get_value_from_path(device, "num_clients"), {}],
            [
                "mist_device_port_stat_tx_bytes",
                get_value_from_path(device, "port_stat.eth0.tx_bytes"),
                {"ifName": "eth0"},
            ],
            [
                "mist_device_port_stat_rx_bytes",
                get_value_from_path(device, "port_stat.eth0.rx_bytes"),
                {"ifName": "eth0"},
            ],
            [
                "mist_device_radio_stat_util_all",
                get_value_from_path(device, "radio_stat.band_6.util_all"),
                {"band": "6"},
            ],
            [
                "mist_device_radio_stat_util_all",
                get_value_from_path(device, "radio_stat.band_5.util_all"),
                {"band": "5"},
            ],
            [
                "mist_device_radio_stat_util_all",
                get_value_from_path(device, "radio_stat.band_24.util_all"),
                {"band": "24"},
            ],
        ]

        # These labels will be added to all metrics
        all_labels_dict = {"hostname": device_name.upper()}
        # These labels will be added to the device_info metric just for information purposes
        details_labels_dict = {
            "serial": get_value_from_path(device, "serial"),
            "model": get_value_from_path(device, "model"),
            "hw_rev": get_value_from_path(device, "hw_rev"),
        }
        metrics_list.append(
            format_metric(
                "mist_device_info", {**details_labels_dict, **all_labels_dict}, 1
            )
        )
        # Merge of metrics and labels
        for item in metric_list:
            name = item[0]
            value = item[1]
            device_labels_dict = item[2]
            labels_merged = {**all_labels_dict, **device_labels_dict}
            if value != "False":
                value = map_string_value_to_int(value)
            else:
                value = 0
                logging.debug(
                    f"{device_name} - Metric {name} not found for device. Setting 0 value."
                )
            metrics_list.append(format_metric(name, labels_merged, value))
    device_count = len(devices)
    metric_count = len(metrics_list)
    logging.info(f"Got {metric_count} metrics for {device_count} AP device(s) from API")
    metrics_list.append(format_metric("mist_device_total_count", [], device_count))
    metrics_list.append(
        format_metric("mist_device_metric_total_count", [], metric_count)
    )
    return metrics_list


def map_string_value_to_int(metric_value: str):
    """Map string values to bool.

    Some string values from the API needs to be mapped to int because we
    want to use them as values for our metric.

    Args:
        metric_name: String metric value (e.g. connected).

    Returns:
        Mapped int for the value defined
    """
    if metric_value in ["connected", "false", "FullyRedundant"]:
        return 0
    elif metric_value in ["disconnected", "true"]:
        return 1
    elif metric_value in ["upgrading"]:
        return 2
    elif metric_value in ["restarting"]:
        return 3
    else:
        return metric_value


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
