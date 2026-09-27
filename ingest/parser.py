
"""
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
import requests

class DSDParser:
    def __init__(self, opensearch_addr="127.0.0.1", opensearch_port="5601"):
        self.opensearch_addr=opensearch_addr
        self.opensearch_port=opensearch_port
        self.opensearch_url = f"http://{self.opensearch_addr}:{self.opensearch_port}"

    """
    0: "2026-09-26 01:45:45 P25p2 TGT: 00000318"
    1: "SRC: 05544753"
    2: "NAC: 6E1"
    3: "NET_STS: BEE00:6EB:1.1"
    4: "Group"
    5: "SName: SP-275-CARLSON"
    6: "Mode: D"
    """
    def read_line(self, line):
        data = {"message": {}, "FQ_SUID": {}}
        try:
            for idx, chunk in enumerate(line.split("; ")):
                sentence = chunk.split(" ")

                if (len(chunk) == 0 or chunk == " "): 
                    continue

                if chunk[0] == ' ':
                    if idx == 1: # We have a talker alias, process separately
                        FQ_SUID = {"WACN": sentence[2].split(':')[0],
                                   "SYSID": sentence[2].split(':')[1].split('.')[0],
                                   "SUBID": sentence[2].split(':')[1].split('.')[1],
                                   "SRC": sentence[3][1:-1]
                                   }
                        data["FQ_SUID"] = FQ_SUID
                    continue
                elif idx == 0 and sentence[0] != ' ': # Timestamp info + TGT
                    data["message"]["date"] = sentence[0]
                    data["message"]["time"] = sentence[1]
                    data["message"]["TGT"]  = sentence[4] # Talkgroup ID
                elif "SRC" in sentence[0]: # Source ID
                    data["message"]["SRC"] = int(sentence[1])
                elif "NAC" in sentence[0]:
                    data["message"]["NAC"] = sentence[1]
                elif "NET_STS" in sentence[0]:
                    data["message"]["NET_STS"] = sentence[1]
                elif "Group" in sentence[0]:
                    data["message"]["call_type"] = sentence[0] # e.g. Group for a group call
                elif "ENC" in sentence[0]:
                    data["message"]["call_type"] = sentence[0] # e.g. ENC for an encrypted call
                elif "SName" in sentence[0]:
                    data["message"]["SName"] = sentence[1]
                elif "Mode" in sentence[0]:
                    data["message"]["Mode"] = sentence[1]
                elif "KID" in sentence[0]:
                    data["message"]["KID"] = sentence[1]
                elif "ALG" in sentence[0]:
                    data["message"]["ALG"] = sentence[1]
                else:
                    print(f"[ERROR] Couldn't handle sentence f{sentence}")
        except Exception as e:
            print(f"[WARN] Failed to parse line\n{line}\n{e}")
        # Send the data to opensearch
        try:
            self._send(data)
        except requests.exceptions.RequestException as e:
            print(f"[WARN] Failed uploading to opensearch\n{e}")

    """
    Send data to opensearch
    expects a dict data of format
    {"message": {}, "FQ_SUID": {}}
    where there would be some info in those, if applicable.
    message and FQ_SUID are mutually exclusive
    """
    def _send(self, data):
        print(data)
        url = f"{self.opensearch_url}"
        if len(data["message"]) > 0:
            requests.post(f"{self.opensearch_url}/messages/_doc", data["message"])
        if len(data["FQ_SUID"]) > 0:
            requests.post(f"{self.opensearch_url}/aliases/_doc", data["FQ_SUID"])

if __name__ == "__main__":
    # Initialize the parser
    parser = DSDParser()

    # We need to read lines from stdin and pass them over to opensearch
    for line in sys.stdin:
        clean_line = line.rstrip('\n')
        parser.read_line(clean_line)

