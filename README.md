# Reverse engineering Aqara E1 wireless switch and E1 USB hub
Notes on reverse engineering some Aqara devices — wireless E1 mini switch and E1 USB hub  
Keywords: `lumi.remote.acn003`, `lumi.remote.acn004`, `WXKG16LM`, `WXKG17LM`, `aqara`, `switch`, `E1`, `wireless`, `tlsr8258`, `zigbee`  

## The problem and the task
I have a bunch of Aqara E1 switches (ones with relays and wireless ones) and I want to use Zigbee binding.  
Binding allows simple automations (this wireless switch controls that wired one) to work when hub is down (or there is interferention on coordinator).  
The original firmware does not support binding (you can bind, but switches ignore that), so I needed to use some custom firmware.  
FW development itself is a good task itself, and I used `simpleSwitch` demo from Telink Zigbee SDK with minimal modifications.  

I soldered some wires to one switch and was able to read the original firmware and write a custom one.  
[TLSRPGM](https://github.com/pvvx/TLSRPGM) after recompilation just works on TLSR8258 (e.g. EBYTE Z5812 module).  

I want to flash custom firmware using Zigbee OTA because I don't want to disassemble every switch and solder wires to it.  
So, OTA using z2m didn't just work. Logs showed the proper Manufacturer code and Image type, also current file version.  
Even with matching IDs the switch ignored OTA, so I supposed there is some manufacturer-specific magic and was going to investigate it.  

Also reverting to the original firmware via OTA would be great, and I didn't have an OTA image for that.

## What didn't work
At first I was going to sniff traffic in order to see how the proprietary hub does the OTA.  
I paired a switch and dumped flash contents (needed some tricks for that), compared it with clean dump and a dump when paired to my z2m with known key.  
So I got a network key and a channel. Later I discovered I could just check hub info in app for channel and sniff a join dialog for the key.  

There seemed to be few ways I possibly could see an OTA in action:
  * just native update (if there was a fresh FW from Xiaomi)
  * maybe my custom firmware could join the proprietary network and report an old version to get a current one
  * maybe I could modify the original dump to make it report an older version and receive an OTA

All that failed.
  * My switch had a fresh version (`0.0.0-0009`, file version 9)
  * The hub uses some crypted handshake when joining a device (some varying data to device and some varying data back) and didn't accept my firmware
  * I changed some bytes in original dump from 9 to 8, that changed a version z2m sees when attempting an OTA, but vendor app continued to report `0.0.0-0009` version

Also I took a risk of losing telnet and upgraded the hub (hoping it then would suggest a fresh FW for the switch). Still no update, but it took few hours for me to restore telnet.  
  * [Enable telnet by button clicks](https://github.com/niceboygithub/AqaraGateway/blob/master/README.md#manually-enable-telnet): 5-2-2-2-2-2 (led blinks green 2 times)
  * [Make telnet persistent](https://github.com/zvldz/aqcn02_fw/tree/main/update#the-easy-way) -- that also gives you `socat`

## Looking for other ways to attack the hub
So, if I could not hijack the Zigbee part, maybe I could interfere on the hub software on other level?  
```mermaid
graph LR
EFR32 --> mZ3GatewayHost_MQTT --> MQTT --> miio_client --> Cloud
Cloud --> miio_client --> MQTT --> mZ3GatewayHost_MQTT --> EFR32
```
There is a `miio_agent` on top of that which restart these processes if they die.  
Luckily, the software components have `--help` and allow verbose logging to a shell.  

First, I made `mZ3GatewayHost_MQTT` verbose and saw some proprietary stuff going between radio and MQTT.  
```shell
# killall -9 mZ3GatewayHost_MQTT; mZ3GatewayHost_MQTT -n 1 -b 115200 -p /dev/ttyS1 -d /data/ -r c
```
Then, I restarted the MQTT broker (Mosquitto) with verbose logging and saw the same traffic as events.  
```shell
# killall -9 mosquitto; mosquitto -v
```
`miio_client` also has quite interesting logs (lots of stuff) on many things.  
```shell
# killall -9 miio_client; miio_client -l0 -d /data/miio/ -n128
```
The connection to the cloud is protected (obviously), so before messing with TLS MITM, I concentrated on MQTT side.

### Version report in MQTT
I started socat as a TCP proxy `1884 -> localhost:1883`, connected with MQTT client (MQTTX in my case) and subscribed to the topics `miio_client` subscribes.  
Found lots of events, and payload in one of them was ending with `302E302E302D30303039` — which is the version `0.0.0-0009` shown by the app. Nice! Let's try to hijack that thing!  
Using the MQTTX I copy-pasted the original message and changed last char from 9 to 8. Et voilà! The app reported `0.0.0-0008` but still no update.  
![manual version fix](pictures/manual_version_fix.png)
I tried changing other bytes of that message but for no avail.  
Repeating that message on other handshake didn't work at all.  

Manual repeating was quite hard and unreliable, I wanted to modify the message on the fly.

### Spoofing the version in real time
I needed some way to modify the original message. I was thinking on some MQTT proxy between the vendor software and MQTT.  
I started Mosquitto on my laptop (allowing anonymous connections from external addresse),
restarted Mosquitto on the hub to listen on different port (to make supervisor happy),
used socat to forward traffic:  
```
# killall -9 mosquitto; mosquitto -p 1884 -d
# socat tcp-listen:1883,fork,reuseaddr tcp-connect:172.31.31.108:1883
```
The hub was still functioning, it was time to modify the message.  

The only proxy I could find was [Janus](https://github.com/phoenix-mstu/janus-mqtt-proxy), but I didn't figure out how to configure it.  
So I went with other option — run an MQTT broker I could easily hack. As I'm familiar with [Erlang](https://www.erlang.org/), I was looking for a broker in this language.  
[emqx](https://github.com/emqx/emqx) turned out to be a huge monstruosity, and I looked for something else.  
[VerneMQ](https://github.com/vernemq/vernemq) is much better for me. I started it and ensured the hub was still functional with it.  
I used `console` command to keep the broker in foreground and to have a shell:
```
$ make rel
$ cd $VERNEMQ/_build/default/rel/vernemq
$ bin/vernemq console
```

After reading the sources and tracing some calls I found VerneMQ has quite powerful [Webhooks](https://docs.vernemq.com/plugin-development/webhookplugins) — much easier for a one-off hack than a full native plugin.  
You may reuse my config `mqtt-mitm/vernemq.conf` or create your own.

A simple Flask/Python script — and I could not just view messages but modify their payloads.  
You can find the full script I used in `mqtt-mitm/webhook_verchange.py`, here is the main transformation:
```python
@api.route('/verchange', methods=['POST'])      
def verchange():      
    req = request.get_json(force=True)
    print(req)
    topic = req['topic']
    payload = json.loads(req['payload'])
    if (topic[0:3] == "gw/") and (topic[19:] == "/MessageReceived") and ('APSPlayload' in payload):               
        aps = payload['APSPlayload']
        if (aps[0:8] == "0x1D5F11") and (aps[20:42] == "0A302E302E305F30303039"):
            payload['APSPlayload'] = aps.replace('0A302E302E305F30303039', '0A302E302E305F30303031')
            return json.dumps({"result":"ok", "modifiers": {"payload": json.dumps(payload)}})
    return json.dumps({"result":"ok"})
```

I tried to guess the format of the version message. Some bytes looked like magic header, one byte was clearly a sequence number (that's why repeating on other handshake didn't work), `0A` looked like the string length, other ones maybe some numeric version and data tags and types.  

So I just matched the original version string in a payload of given length, replaced it with `0.0.0-0001` and… It works!  
The app showed my spoofd version and suggested an OTA to a `0.0.0-3`.  
Wait, but there is `0.0.0-9` already on my switch! OK, just let's see what happens.  

### Getting the outdated OTA
The update didn't work. I tried several times but to no avail. The progress starts and freezes at few percent.  
What's wrong?  
There was no file in `/data` (or I haven't noticed it), but definitely something was going on.  
I started `miio_client` again with verbose logging, retried the OTA and scrolled through the ton of logs, down to top.  
Here it downloads the update binary, well, here the progress is about 0%, and BINGO! Here is a download URL.  
I was able to `wget` the URL, but in a couple of minutes the url was dead.  
So, I finally had an OTA file for FW version `0.0.0-0003`.  

## Restoring the fresh OTA
I looked at `hexdump` of the `0.0.0-0003` OTA and fast-forwarded to the very end. It has some strings, some bytes, some `FF`s, 4 bytes of something like checksum and then EOF.  
I opened the original flash dump, found a very similar part, and exported a range from the beginning to the checksum.  
Starting from `00040000` there is other firmware copy (one of them works, other is used for OTA). I exported that too.  

`make_ota.py` from [z03mmc project](https://github.com/devbis/z03mmc) handled all three files well. Time to try updating with z2m.  

## Messing with file versions
And as earlier the update did not work — the switch ignored the command. Also the hub itself could not apply the OTA. But it should work somehow!  
Maybe firmware ensures it is upgrading to the greater version. Maybe I could make the file look like a more fresh one?

Yes, I can!
  * `make_ota.py -v 13 lumi.remote.acn003-0003.bin`
  * `node scripts/add.js ../115f-2b0b-00000007-lumi.remote.acn003-0003.zigbee`
  * It upgrades!

So, if I change the version in an image header to 13, the firmware "upgrades" even from version 9 to version 3.  
It was surprising for me that version 3 I got from Xiaomi cloud is not accepted by the hub, but works well with z2m.  
There are no issues with a custom firmware, it may be downgraded to original FW.  

Now I can do OTA from original firmware to a custom one, then go back to original, using simple tools.  
TODO: merge with a more mature switch firmware, extend some tools.
