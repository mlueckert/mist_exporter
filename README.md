# Introduction

This is a Prometheus Exporter for Juniper Mist Access Point metrics gathered from the Mist Cloud API.  

Check the documentation of the mist_exporter.py for further details.  

## Exported Metrics

mist_device_num_clients{hostname="MISTDEVICE"} 2
mist_device_radio_stat_band_24_util_all{hostname="MISTDEVICE"} 31
mist_device_metric_total_count 11
mist_device_status{hostname="MISTDEVICE"} 1
mist_device_last_seen_seconds{hostname="MISTDEVICE"} 1.695123148e+09
mist_device_port_stat_eth0_rx_bytes{hostname="MISTDEVICE"} 4.143561699e+09
mist_device_radio_stat_band_6_util_all{hostname="MISTDEVICE"} 0
mist_device_radio_stat_band_5_util_all{hostname="MISTDEVICE"} 1
mist_device_info{serial="A18022302011B",model="AP34",hw_rev="AA",hostname="MISTDEVICE"} 1
mist_device_uptime_seconds{hostname="MISTDEVICE"} 358676
mist_device_port_stat_eth0_tx_bytes{hostname="MISTDEVICE"} 1.670463161e+09
mist_device_power_constrained{hostname="MISTDEVICE"} 0
mist_device_total_count 1
mist_exporter_status 0

## mist_device_status Values

0 = Connected or field not present in JSON
1 = Disconnected
2 = Upgrading
3 = Restarting
