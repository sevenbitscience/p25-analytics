This should describe how to create the full pod for dsd-fme + parser + opensearch

# DSD-FME

I created a container that builds and runs the latest version of dsd-fme

```
cd dsd-fme
podman build -t dsd-fme .
```

To get it to work with an RTL-SDR I needed add myself to the rtlsdr group.
With that working, here's the command I ended up with to run that on it's own,
tracking the control channel.

```
podman run --rm -it --privileged --security-opt label=disable --device /dev/bus/usb -v /dev/bus/usb:/dev/bus/usb \
 -v ./logs/events.log:/tmp/events.log -v ./channel_map.csv:/data/channel_map.csv --net=host \
 dsd-fme:latest -ft -ma -T -C /data/channel_map.csv -i rtl:0:856.5865M:0:0 -o null -J /tmp/events.log
```

# dsd-ingest

This links dsd-fme to a custom python script that sends control channel data
over to opensearch.

This image takes 2 environment variables for its configuration

```
FREQ=856.5865M
CHAN_MAP=/data/channel_map.csv
```

# Full pod configuration

## 1. Build the DSD-FME container image

```
cd dsd-fme
podman build -t dsd-fme .
```

## 2. Build the dsd-ingest container image

```
cd ingest
podman build -t dsd-ingest .
```

## 3. Create the pod

tbd opensearch security

Also make a storage volume for opensearch

```
podman pod create --name p25-analytics -p 5601:5601
podman volume create opensearch-data


podman run -d --pod p25-analytics --name opensearch-core -e "discovery.type=single-node" -e "DISABLE_SECURITY_PLUGIN=true" docker.io/opensearchproject/opensearch
podman run -d --pod p25-analytics --name opensearch-dashboards --replace -e "SERVER_HOST=0.0.0.0" -e "DISABLE_SECURITY_DASHBOARDS_PLUGIN=true" docker.io/opensearchproject/opensearch-dashboards
podman run -d --pod p25-analytics --name dsd-ingest --privileged --security-opt label=disable --device /dev/bus/usb -v /dev/bus/usb:/dev/bus/usb -v ~/p25-analytics/channel_map.csv:/data/channel_map.csv -e FREQ=856.59M -e CHAN_MAP=/data/channel_map.csv dsd-ingest:latest
```

Should work
Tested for a day or so on the laptop
tbd deployment on the server.

tbd make it persistent across reboots.
