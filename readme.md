# ebusd plugin for Domoticz

This is a plugin for [Domoticz](https://domoticz.com), for Domoticz to communicate directly with [ebusd](https://github.com/john30/ebusd) daemon. Ebus is a protocol to communicate mainly with Vaillant and Saunier-Duval boilers.

## Warning

This is a hobby project, use it if you know what you are doing and at your own risks, I cannot be held responsible for toying and erasing your boiler configuration or breaking your underfloor heating system. I strongly advise to an hardware protection device for your underfloor heating system, for instance an aquastat on the "burner off" input, that opens at 50°C (protection in case of programming error, or piracy...).

## Prerequisites

You need to have [ebusd](https://github.com/john30/ebusd) daemon installed, maybe you can install a package directly from [releases](https://github.com/john30/ebusd/releases), and you need to install it with its [configuration files](https://github.com/john30/ebusd-configuration), accessible from network to Domoticz and obviously, a [hardware supported by ebusd](https://github.com/john30/ebusd/wiki/6.-Hardware).
The plugin has been tested with ebusd version 3.0.595c7c0 and a Vaillant ecoTEC plus VUI FR 306/5-5 R5 boiler with a calorMATIC VRC470f wireless remote control and VR61/4 underfloor heating system kit.
Check first that ebusd is working properly with the following command directly on the device hosting ebusd:
```
ebusctl find
```

Then check that ebusd telnet connection is available from the device hosting Domoticz (change IP address to ebusd hosting device IP address or name, 8888 is default ebusd port, change it to your telnet port number if different):
```
telnet 192.168.0.10 8888
find
quit
```
You should get the same list as the previous command.

I advise to limit telnet access on you ebusd hosting device to the device hosting Domoticz, for instance, I added the following to my "/etc/rc.local":
```
iptables -A INPUT -p tcp ! -s 192.168.0.11 --dport 8888 -j DROP

```
Change IP address to Domoticz hosting device IP address, change port to your telnet port number if different. 

For the plugin to work, ebusd must be started with HTTP JSON --httpport option, for instance on port 8889. I had to change my "/etc/default/ebusd" after installing the .deb package for raspberry pi:

```
# /etc/default/ebusd:
# config file for ebusd service.

# Options to pass to ebusd (run "ebusd -?" for more info):
EBUSD_OPTS="--scanconfig --httpport 8889"
```

Then restart the daemon:
```
sudo service ebusd restart
```

Then you can open and see available registers from your favorite internet browser, for instance at this address: [http://192.168.0.10:8889/data?def](http://192.168.0.10:8889/data?def) (change IP address to ebusd hosting device IP address or name, change 8889 port to whatever port you configured for HTTP JSON):
```
{
 "bai": {
  "messages": {
   "AccessoriesOne": {
    "name": "AccessoriesOne",
    "passive": false,
    "write": false,
    "lastup": 0,
    "zz": 8,
    "id": [181, 9, 13, 75, 4],
    "fielddefs": [
     { "name": "", "slave": true, "type": "UCH", "isbits": false, "length": 1, "values": { "1": "circulationpump", "2": "extheatingpump", "3": "storagechargingpump", "4": "fluegasflapextractorhood", "5": "externalgasvalve", "6": "externalerrormessage", "7": "solarpump", "8": "remotecontrol" }, "unit": "", "comment": "Accesory relay 1 function"}
    ]
   },
   "AccessoriesTwo": {
    "name": "AccessoriesTwo",
    "passive": false,
    "write": false,
    "lastup": 0,
    "zz": 8,
    "id": [181, 9, 13, 76, 4],
    "fielddefs": [
     { "name": "", "slave": true, "type": "UCH", "isbits": false, "length": 1, "values": { "1": "circulationpump", "2": "extheatingpump", "3": "storagechargingpump", "4": "fluegasflapextractorhood", "5": "externalgasvalve", "6": "externalerrormessage", "7": "solarpump", "8": "remotecontrol" }, "unit": "", "comment": "Accesory relay 2 function"}
    ]
   },
   "ACRoomthermostat": {
    "name": "ACRoomthermostat",
    "passive": false,
    "write": false,
    "lastup": 0,
    "zz": 8,
    "id": [181, 9, 13, 42, 0],
    "fielddefs": [
     { "name": "onoff", "slave": true, "type": "UCH", "isbits": false, "length": 1, "values": { "0": "off", "1": "on" }, "unit": "", "comment": "External controls heat demand (Clamp 3-4)"}
    ]
   },
...
```

## Installing

Copy the plugin.py to domoticz directory/plugins/DomoticzEbusd or change directory to domoticz directory/plugins and issue the following command:

```
git clone https://github.com/guillaumezin/DomoticzEbusd
```

To update, overwrite plugin.py or change directory to domoticz directory/plugins/DomoticzEbusd and issue the following command:
```
git pull
```

Give the execution permission, for Linux:
```
chmod ugo+x plugin.py
```

Restart Domoticz.

## Configuration
Add the ebusd-bridge hardware in Domoticz hardware configuration tab, giving the ebusd hosting device IP address or name, the telnet port, the HTTP JSON port, the registers, and set the refresh rate, read-only mode and debug mode. The refresh rate reads the registers values at the given rate in seconds. You can add many registers separated by space. The registers must be given with the following convention:
```
broadcast:outsidetemp f47:RoomTemp:0 f47:Hc1OPMode mc:InternalOperatingMode470 mc:Flow1Sensor mc:FlowTempDesired bai:FlowTemp bai:ReturnTemp bai:FlowTempDesired bai:StorageTemp
```
Warning: this is case sensitive. The first part of a register is the circuit name, the second part must be a message name (third level of JSON data), and the third part is the index of field in fielddefs of a message in JSON data, and is optional (field index 0 by default). To see available registers, open your favorite internet browser, for instance at this address: [http://192.168.0.10:8889/data?def](http://192.168.0.10:8889/data?def) (change IP address to ebusd hosting device IP address or name, change 8889 port to whatever port you configured for HTTP JSON):

You can add more than one ebusd-bridge hardware to Domoticz, for instance to get some registers as read-only and others as writable.

## Authors

* **Guillaume Zin** - *Initial work* - [DomoticzEbusd](https://github.com/guillaumezin/DomoticzEbusd)

See also the list of [contributors](https://github.com/guillaumezin/DomoticzEbusd/contributors) who participated in this project.

## License

This project is licensed under the MIT license - see the [LICENSE](LICENSE) file for details

## Acknowledgments

* John30 for ebusd
* Domoticz team
