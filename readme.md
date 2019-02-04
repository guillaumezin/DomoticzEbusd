# ebusd plugin for Domoticz

This is a plugin for [Domoticz](https://domoticz.com), for Domoticz to communicate directly with [ebusd](https://github.com/john30/ebusd) daemon. Ebus is a protocol to communicate mainly with Vaillant and Saunier-Duval boilers.

## Warning

This is a hobby project, use it if you know what you are doing and at your own risks, I cannot be held responsible for toying and erasing your boiler configuration or breaking your underfloor heating system. I strongly advise to install an hardware protection device for your underfloor heating system, for instance an aquastat on the "burner off" input, that opens at 50°C (protection in case of programming error, or piracy...).

## Prerequisites

Domoticz version must be at least 3.9085.

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
   "SetMode": {
    "name": "SetMode",
    "passive": true,
    "write": true,
    "lastup": 1518368270,
    "zz": 8,
    "id": [181, 16, 0],
    "fields": {
     "hcmode": {"value": "auto"},
     "flowtempdesired": {"value": 46.5},
     "hwctempdesired": {"value": 55.0},
     "hwcflowtempdesired": {"value": null},
     "disablehc": {"value": 0},
     "disablehwctapping": {"value": 0},
     "disablehwcload": {"value": 0},
     "remoteControlHcPump": {"value": 0},
     "releaseBackup": {"value": 0},
     "releaseCooling": {"value": 0}
    },
    "fielddefs": [
     { "name": "hcmode", "slave": false, "type": "UCH", "isbits": false, "length": 1, "values": { "0": "auto", "1": "off", "2": "water" }, "unit": "", "comment": "Boiler Modus"},
     { "name": "flowtempdesired", "slave": false, "type": "D1C", "isbits": false, "length": 1, "unit": "°C", "comment": "Temperatur"},
     { "name": "hwctempdesired", "slave": false, "type": "D1C", "isbits": false, "length": 1, "unit": "°C", "comment": "Temperatur"},
     { "name": "hwcflowtempdesired", "slave": false, "type": "UCH", "isbits": false, "length": 1, "unit": "°C", "comment": "Temperatur"},
     { "name": "", "slave": false, "type": "IGN", "isbits": false, "length": 1, "unit": "", "comment": ""},
     { "name": "disablehc", "slave": false, "type": "BI0", "isbits": true, "length": 1, "unit": "", "comment": ""},
     { "name": "disablehwctapping", "slave": false, "type": "BI1", "isbits": true, "length": 1, "unit": "", "comment": ""},
     { "name": "disablehwcload", "slave": false, "type": "BI2", "isbits": true, "length": 1, "unit": "", "comment": ""},
     { "name": "", "slave": false, "type": "IGN", "isbits": false, "length": 1, "unit": "", "comment": ""},
     { "name": "remoteControlHcPump", "slave": false, "type": "BI0", "isbits": true, "length": 1, "unit": "", "comment": ""},
     { "name": "releaseBackup", "slave": false, "type": "BI1", "isbits": true, "length": 1, "unit": "", "comment": ""},
     { "name": "releaseCooling", "slave": false, "type": "BI2", "isbits": true, "length": 1, "unit": "", "comment": ""}
    ]
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
broadcast:outsidetemp bai:SetMode:hcmode bai:SetMode:2 bai:SetMode:hwcflowtempdesired f47:RoomTemp:0 f47:Hc1OPMode mc:InternalOperatingMode470 mc:Flow1Sensor mc:FlowTempDesired bai:FlowTemp bai:ReturnTemp bai:FlowTempDesired bai:StorageTemp f47:Hc1SFMode f47:Hc2SFMode bai:WaterPressure f47:Hc1HolidayStartPeriod f47:Hc1HolidayEndPeriod f47:Hc2HolidayStartPeriod f47:Hc2HolidayEndPeriod
```
This is case insensitive (since version 1.1.7). The first part of a register is the circuit name, the second part must be a message name (third level of JSON data), and the third part is the index, or the name (possible only if different than "") of field in fielddefs of a message in JSON data, and is optional (field index 0 by default). For instance "bai:SetMode:2" in my case gives "hwctempdesired" fielddefs value, i.e. the desired hot water  temperature, because it is the second field of bai->messages->SetMode register. It could have been configured with "bai:SetMode:hwctempdesired" directly. Starting version 1.3.8, fielddefs type "IGN" are ignored for index counting and name searching. For instance "bai:SetMode:4" give the same result as "bai:SetMode:disablehc". To see available registers, open your favorite internet browser, for instance at this address: [http://192.168.0.10:8889/data?def](http://192.168.0.10:8889/data?def) (change IP address to ebusd hosting device IP address or name, change 8889 port to whatever port you configured for HTTP JSON):

You can add more than one ebusd-bridge hardware to Domoticz, for instance to get some registers as read-only and others as writable.

## Particular case of holiday mode
Holiday mode can be activated only by setting a start and end date. If you set "holiday" to Hc1SFMode or Hc2SFMode, it won't be effective. Domoticz doesn't handle date devices, so f47:Hc1HolidayStartPeriod f47:Hc1HolidayEndPeriod f47:Hc2HolidayStartPeriod f47:Hc2HolidayEndPeriod will appear as read-only text devices. To set holiday mode from Domoticz, you can create a virtual switch and create a Lua or dzVents script, here is an example where "Holiday mode" is a virtual switch:
```
return {
	on = {
		devices = {
			'Holiday mode'
		}
	},
	execute = function(domoticz, device)
		domoticz.log('Device ' .. device.name .. ' was changed', domoticz.LOG_ERROR)
	        if (device.active) then
	            domoticz.devices("ebusd bridge - f47:hc1holidaystartperiod - date").update(0, "01.01.2010")
	            domoticz.devices("ebusd bridge - f47:hc2holidaystartperiod - date").update(0, "01.01.2010")
	            domoticz.devices("ebusd bridge - f47:hc1holidayendperiod - date").update(0, "01.01.2090")
	            domoticz.devices("ebusd bridge - f47:hc2holidayendperiod - date").update(0, "01.01.2090")
	        else
	            domoticz.devices("ebusd bridge - f47:hc1holidaystartperiod - date").update(0, "01.01.2010")
	            domoticz.devices("ebusd bridge - f47:hc2holidaystartperiod - date").update(0, "01.01.2010")
	            domoticz.devices("ebusd bridge - f47:hc1holidayendperiod - date").update(0, "01.01.2010")
	            domoticz.devices("ebusd bridge - f47:hc2holidayendperiod - date").update(0, "01.01.2010")
	       end
	end
}
```
Now you can set "On" and "Off", even using Timers, on "Holiday mode" virtual switch, to disable heating circuits. Hot water production will be disabled automatically when all heating circuits are in holiday mode with my calorMATIC VRC470f control. This will work with Domoticz from version 3.9415 onwards, because on earlier version, update() methods from Lua and dzVents event scripts are not passed to python plugins.

## Script examples

dsVents script to automatically switch from summer mode to auto mode
```
-- temperature to decide summer mode
highTempLevel = 20
-- temperature to decide winter mode
lowTempLevel = highTempLevel - 4
-- consecutive days to watch
nDaysToWatch = 3
-- temperature device
temperatureDevice = "Température extérieure"
-- heating device 1
heating1Device = "Mode chauffage RDC"
-- heating device 2
heating2Device = "Mode chauffage étage"
-- selector switch level for summer mode
summerModeLevel = 40
-- selector switch level for winter mode
winterModeLevel = 10

return {
	on = {
		timer = {
		    "at 20:00"
		},
	},
	data = {
	    history = { initial = 0 },
	    mode  = { initial = -1 }
	},
	execute = function(domoticz, item)
    	temperature = domoticz.devices(temperatureDevice).temperature
    	if (domoticz.data.mode == winterModeLevel) then
    	    if (temperature >= highTempLevel) then
    	        if domoticz.data.history < nDaysToWatch then
    	            domoticz.data.history = domoticz.data.history + 1
    	            if domoticz.data.history == nDaysToWatch then
                	    domoticz.log("Switching heating to summer mode")
                	    domoticz.data.mode = summerModeLevel
            	        domoticz.data.history = 0
                		domoticz.devices(heating1Device).switchSelector(domoticz.data.mode)
                		domoticz.devices(heating2Device).switchSelector(domoticz.data.mode)
    	            end
                end
    	    else
    	        domoticz.data.history = 0
            end
        else
    	    if (temperature <= lowTempLevel) then
    	        if domoticz.data.history < nDaysToWatch then
    	            domoticz.data.history = domoticz.data.history + 1
    	            if domoticz.data.history == nDaysToWatch then
                	    domoticz.log("Switching heating to winter mode")
                	    domoticz.data.mode = winterModeLevel
            	        domoticz.data.history = 0
                		domoticz.devices(heating1Device).switchSelector(domoticz.data.mode)
                		domoticz.devices(heating2Device).switchSelector(domoticz.data.mode)
    	            end
                end
	        else
   	            domoticz.data.history = 0
            end
	    end
    end
}
```

## Authors

* **Guillaume Zin** - *Initial work* - [DomoticzEbusd](https://github.com/guillaumezin/DomoticzEbusd)

See also the list of [contributors](https://github.com/guillaumezin/DomoticzEbusd/contributors) who participated in this project.

## License

This project is licensed under the MIT license - see the [LICENSE](LICENSE) file for details

## Acknowledgments

* John30 for ebusd
* Domoticz team
