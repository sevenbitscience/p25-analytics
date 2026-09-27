r"""
podman run --rm -it --privileged --security-opt label=disable --device /dev/bus/usb -v /dev/bus/usb:/dev/bus/usb -v ./logs/events.log:/tmp/events.log -v ./channel_map.csv:/data/channel_map.csv --net=host \
  dsd -ft -ma -T -C /data/channel_map.csv -i rtl:0:856.5865M:0:0 -o null -J /tmp/events.log
"""

"""
Data is in this format
2026-09-26 00:40:29 P25p1 TGT: 00000102; SRC: 05548243; NAC: 6E1; NET_STS: BEE00:6EB:1.1; ENC; ALG: AA; KID: 6673; Group; SName: PP-2494-MCDONO; Mode: D;  
 Talker Alias: PP-2494-MCDONO;  FQ-SUID: BEE00:6EB.54A8D3 (5548243); 
2026-09-26 13:39:55 P25p2 TGT: 00000318; SRC: 05544563; NAC: 6E1; NET_STS: BEE00:6EB:1.1; Group; SName: SP-3570-FERDIN; Mode: D;  Slot 2; 
"""

import sys
import re
import time
import requests
from datetime import datetime, timezone

class DSDParser:
    def __init__(self, opensearch_url="http://127.0.0.1:9200"):
        self.opensearch_url = opensearch_url
        self.valid = False
        self.session = requests.Session()

    """
    Connect to the opensearch instance
    """
    def connect(self):
        if self.valid:
            return True

        # Wait until opensearch is up
        if not self._wait_for_opensearch():
            print("[ERROR] Failed to connect to opensearch", file=sys.stderr)
            return False

        # Set up indices
        # 1. messages index:
        messages_url = f"{self.opensearch_url}/messages"
        r = self.session.head(messages_url)
        if r.status_code != 200:
            mapping = {
                "mappings": {
                    "properties": {
                        "@timestamp": {"type": "date"},
                        "protocol": {"type": "keyword"},
                        "talkgroup": {"type": "keyword"},
                        "source": {"type": "keyword"},
                        "nac": {"type": "keyword"},
                        "network_status": {"type": "keyword"},
                        "call_type": {"type": "keyword"},
                        "shortname": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                        "mode": {"type": "keyword"},
                        "encrypted": {"type": "boolean"},
                        "slot": {"type": "integer"},
                        "key_id": {"type": "keyword"},
                        "algorithm_id": {"type": "keyword"},
                    }
                }
            }
            create_resp = self.session.put(messages_url, json=mapping, timeout=5)
            create_resp.raise_for_status()

        # 2. aliases index (with nested FQ_SUID mapping):
        aliases_url = f"{self.opensearch_url}/aliases"
        r_alias = self.session.head(aliases_url)
        if r_alias.status_code != 200:
            aliases_mapping = {
                "mappings": {
                    "properties": {
                        "@timestamp": {"type": "date"},
                        "talker_alias": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                        "FQ_SUID": {
                            "properties": {
                                "WACN": {"type": "keyword"},
                                "SYSID": {"type": "keyword"},
                                "SUBID": {"type": "keyword"},
                                "SRC": {"type": "keyword"},
                            }
                        }
                    }
                }
            }
            create_resp = self.session.put(aliases_url, json=aliases_mapping, timeout=5)
            create_resp.raise_for_status()

        self.valid = True
        return True

    def _wait_for_opensearch(self):
        print("Waiting for OpenSearch to come online...", file=sys.stderr)
        for _ in range(60):
            try:
                r = self.session.get(self.opensearch_url, timeout=3)
                if r.status_code == 200:
                    return True
            except requests.RequestException:
                pass
            time.sleep(2)

        return False

    def read_line(self, line):
        data = {"message": {}, "FQ_SUID": {}}
        raw = line.strip()
        if not raw:
            return

        # Skip initialization / banner messages
        if "DSD-FME Started" in raw or "Any decoded voice calls" in raw:
            return

        try:
            # Case 1: Talker Alias and FQ-SUID line
            # Example: Talker Alias: SP-5025-BALMER;  FQ-SUID: BEE00:6EB.549B7F (5544831);
            if "Talker Alias:" in raw or "FQ-SUID:" in raw:
                alias_match = re.search(r"Talker Alias:\s*([^;]+);", raw)
                fq_match = re.search(r"FQ-SUID:\s*([^;]+);", raw)

                fq_dict = {}
                if fq_match:
                    fq_raw = fq_match.group(1).strip()
                    m = re.match(r"([0-9A-Fa-f]+):([0-9A-Fa-f]+)\.([0-9A-Fa-f]+)\s+\((\d+)\)", fq_raw)
                    if m:
                        fq_dict = {
                            "WACN": m.group(1),
                            "SYSID": m.group(2),
                            "SUBID": m.group(3),
                            "SRC": m.group(4)
                        }

                data["FQ_SUID"] = {
                    "@timestamp": datetime.now(timezone.utc).isoformat(),
                    "talker_alias": alias_match.group(1).strip() if alias_match else None,
                    "FQ_SUID": fq_dict
                }

            # Case 2: Event message line
            else:
                chunks = [c.strip() for c in line.split(";") if c.strip()]
                if not chunks:
                    return

                first = chunks[0].split()
                if len(first) >= 5 and first[3] == "TGT:":
                    data["message"]["date"] = first[0]
                    data["message"]["time"] = first[1]
                    data["message"]["@timestamp"] = self._convert_time(first[0], first[1]).isoformat()
                    data["message"]["protocol"] = first[2]
                    data["message"]["talkgroup"] = first[4]
                    data["message"]["encrypted"] = False

                    for chunk in chunks[1:]:
                        if chunk == "ENC":
                            data["message"]["encrypted"] = True
                            data["message"]["call_type"] = "ENC"
                        elif chunk == "Group":
                            data["message"]["call_type"] = "Group"
                        elif chunk.startswith("Slot "):
                            data["message"]["slot"] = int(chunk.split()[1])
                        elif ":" in chunk:
                            key, val = chunk.split(":", 1)
                            key, val = key.strip(), val.strip()
                            if key == "SRC":
                                data["message"]["source"] = val
                            elif key == "NAC":
                                data["message"]["nac"] = val
                            elif key == "NET_STS":
                                data["message"]["network_status"] = val
                            elif key == "SName":
                                data["message"]["shortname"] = val
                            elif key == "Mode":
                                data["message"]["mode"] = val
                            elif key == "KID":
                                data["message"]["key_id"] = val
                            elif key == "ALG":
                                data["message"]["algorithm_id"] = val
                            else:
                                print(f"[ERROR] Couldn't handle chunk: {chunk}", file=sys.stderr)

        except Exception as e:
            print(f"[WARN] Failed to parse line\n{line}\n{e}", file=sys.stderr)

        # Send the data to opensearch
        if self.valid:
            try:
                self._send(data)
            except requests.exceptions.RequestException as e:
                print(f"[WARN] Failed uploading to opensearch\n{e}", file=sys.stderr)
        else:
            # Fallback output when running offline / dry-run
            if len(data["message"]) > 0:
                print(f"[EVENT] {data['message']}")
            if len(data["FQ_SUID"]) > 0:
                print(f"[ALIAS] {data['FQ_SUID']}")

    def _convert_time(self, date, time_val):
        dt_str = f"{date} {time_val}"
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone.utc)

    def _send(self, data):
        if len(data["message"]) > 0:
            resp = self.session.post(f"{self.opensearch_url}/messages/_doc", json=data["message"], timeout=5)
            resp.raise_for_status()
            print(f"[INGEST] Indexed message TG:{data['message'].get('talkgroup')} SRC:{data['message'].get('source')} ({data['message'].get('protocol')})", file=sys.stderr)
        if len(data["FQ_SUID"]) > 0:
            resp = self.session.post(f"{self.opensearch_url}/aliases/_doc", json=data["FQ_SUID"], timeout=5)
            resp.raise_for_status()
            print(f"[INGEST] Indexed alias: {data['FQ_SUID'].get('talker_alias')}", file=sys.stderr)

if __name__ == "__main__":
    parser = DSDParser()
    # Attempt to connect and initialize indices; if offline, dry-run parsing to stdout
    parser.connect()

    for line in sys.stdin:
        clean_line = line.rstrip('\n')
        parser.read_line(clean_line)


