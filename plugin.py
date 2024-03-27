#           ebusd Plugin
#
#           Author:     Barberousse, z1mEk, 2017-2018
#           MIT license
#
"""
<plugin key="ebusd" name="ebusd bridge" author="Barberousse" version="2.0.0" externallink="https://github.com/guillaumezin/DomoticzEbusd">
    <params>
        <!-- <param field="Username" label="Username (left empty if authentication not needed)" width="200px" required="false" default=""/>
        <param field="Password" label="Password" width="200px" required="false" default="" password="true"/> -->
        <param field="Address" label="IP or named address" width="200px" required="true" default="127.0.0.1"/>
        <param field="Port" label="Telnet port" width="100px" required="true" default="8888"/>
        <param field="Mode1" label="JSON HTTP port" width="100px" required="true" default="8889"/>
        <param field="Mode2" label="Registers" width="1000px" required="false" default=""/>
        <param field="Mode3" label="Refresh rate (seconds)" width="100px" required="false" default="600"/>
        <param field="Mode4" label="Disable cache" width="100px">
            <options>
                <option label="True" value="True"/>
                <option label="False" value="False"  default="true" />
            </options>
        </param>
        <param field="Mode5" label="Read-only" width="100px">
            <options>
                <option label="True" value="True"/>
                <option label="False" value="False"  default="true" />
            </options>
        </param>
        <param field="Mode6" label="Debug" width="100px">
            <options>
                <option label="Advanced" value="2"/>
                <option label="Enabled" value="1"/>
                <option label="None" value="0"  default="true" />
            </options>
        </param>
    </params>
</plugin>
"""

# https://www.domoticz.com/wiki/Developing_a_Python_plugin

import DomoticzEx as Domoticz
import json
import time
import sys
from collections import deque
from collections import OrderedDict
if (sys.version_info.major == 3) and (sys.version_info.minor >= 10):
    from collections.abc import MutableMapping
    from collections.abc import Mapping
else:
    from collections import MutableMapping
    from collections import Mapping
import traceback
import re
import shlex

# https://github.com/requests/requests/blob/master/requests/structures.py
class CaseInsensitiveDict(MutableMapping):
    """A case-insensitive ``dict``-like object.
    Implements all methods and operations of
    ``MutableMapping`` as well as dict's ``copy``. Also
    provides ``lower_items``.
    All keys are expected to be strings. The structure remembers the
    case of the last key to be set, and ``iter(instance)``,
    ``keys()``, ``items()``, ``iterkeys()``, and ``iteritems()``
    will contain case-sensitive keys. However, querying and contains
    testing is case insensitive::
        cid = CaseInsensitiveDict()
        cid['Accept'] = 'application/json'
        cid['aCCEPT'] == 'application/json'  # True
        list(cid) == ['Accept']  # True
    For example, ``headers['content-encoding']`` will return the
    value of a ``'Content-Encoding'`` response header, regardless
    of how the header name was originally stored.
    If the constructor, ``.update``, or equality comparison
    operations are given keys that have equal ``.lower()``s, the
    behavior is undefined.
    """

    def __init__(self, data=None, **kwargs):
        self._store = OrderedDict()
        if data is None:
            data = {}
        self.update(data, **kwargs)
        
    # lower and remove substring between []
    def __lowerAndFilter(self, key):
        return re.sub(r'\[.+?\]', '', key).lower()

    def __setitem__(self, key, value):
        # Use the lowercased key for lookups, but store the actual
        # key alongside the value.
        self._store[self.__lowerAndFilter(key)] = (key, value)

    def __getitem__(self, key):
        return self._store[self.__lowerAndFilter(key)][1]

    def __delitem__(self, key):
        del self._store[self.__lowerAndFilter(key)]

    def __iter__(self):
        return (casedkey for casedkey, mappedvalue in self._store.values())

    def __len__(self):
        return len(self._store)

    def lower_items(self):
        """Like iteritems(), but with all lowercase keys."""
        return (
            (lowerkey, keyval[1])
            for (lowerkey, keyval)
            in self._store.items()
        )

    def __eq__(self, other):
        if isinstance(other, Mapping):
            other = CaseInsensitiveDict(other)
        else:
            return NotImplemented
        # Compare insensitively
        return dict(self.lower_items()) == dict(other.lower_items())

    # Copy is required
    def copy(self):
        return CaseInsensitiveDict(self._store.values())

    def __repr__(self):
        return str(dict(self.items()))

class BasePlugin:
    # string address port from parameters
    sParamAddress = ""
    # integer http port from parameters
    iParamTelnetPort = 8888
    # integer json port from parameters
    iParamJsonPort = 8889
    # integer refresh rate from parameters
    iParamRefreshRate = 600
    # boolean disable cache from parameters
    bParamDisableCache = False
    # boolean read-only from parameters
    bParamReadOnly = False
    # boolean debug from parameters
    iParamDebug = 0
    # boolean to check that we are started, to prevent error messages when disabling or restarting the plugin
    bIsStarted = None
    # boolean to ask restart of the plugin
    bShallRestart = None
    # telnet connection
    telnetConn = None
    # string buffer for telnet data
    sBuffer = None
    # json http connection
    jsonConn = None
    # boolean that indicates that some registers weren't found yet
    bStillToLook = None
    # integer that count number of json objects
    iJsonObjects = None
    # integer to keep time of last refresh
    iRefreshTime = None
    # integer to keep time of last search for new messages
    iRefreshFindDeviceTime = None
    # integer to force search for new messages every xxx seconds
    iRefreshFindDeviceRate = 600
    # regex to search message
    sRegExSearch = None
    # dictionnary of messages extracted from json, structured as keys wih circuit:message and circuit:message:fieldindex and pointing to json iFieldElement
    dMessages = None
    # dictionnary of dictonnaries, keyed by deviceid string (circuit:register:fieldindex, for instance "f47:OutsideTemp:0")
    #   "device": object: object corresponding in Devices dict
    #   "circuit": string: circuit name, for instance "f47"
    #   "message": string: register, for instance "OutsideTemp"
    #   "fieldindex": integer: field index (0 based)
    #   "fieldscount": integer: total number of fields
    #   "options": dictionnary: keyed by ebusd value, contains selector switch level integer value, empty if not selector switch
    #   "forcerefresh": boolean: to refresh device at creation
    #   "alwaysrefresh": boolean: to refresh at a regular basis
    #   "reverseoptions": dictionnary: keyed by selector switch level integer valu, contains selector switch ebusd string value, empty if not selector switch
    #   "domoticzoptions": dictionnary: options send during domoticz device type selector switch creation and update
    #   "fieldtype": string: cf. getFieldType() return value
    #   "fieldsvalues": string: fields values read after "readwhole" operation
    #   "fieldsvaluestimestamp": integer: time when fields values have been updated
    dUnitsByDeviceID = None
    # same dictionnary, but keyed by 3 dimensions: dUnits3D[circuit][register][fieldindex]
    dUnits3D = None
    # dequeue of dictionnaries
    #   "operation": string: can be "read", "readwhole", "write", "authenticate"
    #   "unit": dict contained in dUnitsByDeviceID
    #   "value": string: value to write in ebusd format, used only for "write" operation
    dqFifo = None
    # string that contains the connection step: "idle", then "connecting", then "connected", then "data sending"
    sConnectionStep = None
    # integer: time when connection step has been updated
    iConnectionTimestamp = None
    # string: keep track of current operation, see dfFifo
    sCurrentCommand = None
    # integer: timeout in s
    iTimeoutConstant = 10
    # integer: max heartbeat interval in s
    iMaxHeartbeatInterval = 30
    # integer: time when discovering starts
    iDiscoverStartTime = None
    # integer: time for messages discovering before deciding timeout in s
    iDiscoverTime = 300
    # integer: debug level
    iParamDebug = 0
    
    def __init__(self):
        self.bIsStarted = False
        self.bShallRestart = False
        self.telnetConn = None
        self.jsonConn = None
        self.sRegExSearch = None
        self.dMessages = {}
        self.dUnitsByDeviceID = {}
        self.dUnits3D = {}
        self.sBuffer = ""
        self.bStillToLook = True
        self.iJsonObjects = 0
        timeNow = time.time()
        self.iRefreshTime = timeNow
        self.iRefreshFindDeviceTime = timeNow
        self.iDiscoverStartTime = timeNow
        self.dqFifo = deque()
        self.sConnectionStep = "idle"
        self.iConnectionTimestamp = 0
        self.sCurrentCommand = ""

    def myDebug(self, message):
        if self.iParamDebug:
            Domoticz.Log(message)

    # Connect to JSON HTTP port to get list of ebusd devices
    def findDevices(self):
        if self.jsonConn == None:
            self.myDebug("findDevices() create connection to " + self.sParamAddress + ":" + str(self.iParamJsonPort))
            self.jsonConn = Domoticz.Connection(Name="JSON HTTP", Transport="TCP/IP", Protocol="HTTP", Address=self.sParamAddress, Port=str(self.iParamJsonPort))

        if not self.jsonConn.Connected():
            self.myDebug("Connect")
            self.jsonConn.Connect()
        else:
            self.myDebug("Find")
            # we connect with def and write to get complete list of fields and writable registers
            sendData = { "Verb" : "GET",
                        "URL"  : "/data?def&write",
                        "Headers" : { "Content-Type": "text/xml; charset=utf-8", \
                                        "Connection": "keep-alive", \
                                        "Accept": "Content-Type: text/html; charset=UTF-8", \
                                        "Host": self.sParamAddress+":"+str(self.iParamJsonPort), \
                                        "User-Agent":"Domoticz/1.0" }
                       }
            self.jsonConn.Send(sendData)            
     
    # Parse received data from telnet connection in localStrBuffer
    def parseTelnet(self, localStrBuffer):
        self.myDebug("Parse telnet buffer size " + str(len(localStrBuffer)))
        # We are interested only in first line
        lLines = localStrBuffer.splitlines()
        sReadValue = lLines[0]
        # Check if we received an error message
        if sReadValue[:5] == "ERR: ":
            self.myDebug("Error from telnet client: " + sReadValue[5:])
        else:
            self.myDebug("Reveived value: " + repr(sReadValue))
            # We sould receive something like "f47 OutsideTemp temp=9.56;sensor=ok"
            # Split by space
            lParams = sReadValue.split(" ", 2)
            if len(lParams) >= 3:
                # Split received fields by ;
                sFields = lParams[2].split(";")
                lFieldsValues = []
                sCircuit = lParams[0].lower()
                sMessage = lParams[1].lower()
                # Look for corresponding circuit and register
                if (sCircuit in self.dUnits3D) and (sMessage in self.dUnits3D[sCircuit]):
                    # Extract read fields
                    for sField in sFields:
                        # Keep only the right of =
                        sFieldContent = sField.split("=")
                        # Sanity check
                        if len(sFieldContent) == 2:
                                # Keep read values in lFieldsValues
                                lFieldsValues.append(sFieldContent[1])
                        else:
                                Domoticz.Error("Parsing error on field for value " + sReadValue)
                    
                    # Save whole values for later use with a timestamp
                    sFieldsValues = ";".join(lFieldsValues)
                    iFieldsValuesTimestamp = time.time()
                    for dUnit in self.dUnits3D[sCircuit][sMessage].values():
                        dUnit["fieldsvalues"] = sFieldsValues
                        dUnit["fieldsvaluestimestamp"] = iFieldsValuesTimestamp
                        self.myDebug("Save whole fields values " + dUnit["fieldsvalues"])						
                        # Distribute read values for each field we are interested into
                        if dUnit["fieldindex"] < len(lFieldsValues):
                            sFieldValue = lFieldsValues[dUnit["fieldindex"]]
                            iValue, sValue = valueEbusdToDomoticz(dUnit, sFieldValue)
                            oUnit = dUnit["device"]
                            if oUnit is not None:
                                if (oUnit.nValue != iValue) or (oUnit.sValue != sValue):
                                    oUnit.nValue = iValue
                                    oUnit.sValue = sValue
                                    oUnit.Update(Log=True)
                                    oUnit.Parent.TimedOut=0
                                    dUnit["forcerefresh"] = False
                                elif dUnit["forcerefresh"] or dUnit["alwaysrefresh"] or oUnit.Parent.TimedOut:
                                    oUnit.Parent.TimedOut=0
                                    oUnit.Touch()
                                    dUnit["forcerefresh"] = False
                                else:
                                    oUnit.Touch()
                            else:
                                Domoticz.Error("Received unexpected value " + sReadValue + " for device not anymore in dictionnary")
                        else:
                            Domoticz.Error("Field not found in unit dictionaries for circuit " + dUnit["circuit"] + " message " + dUnit["message"] + " field " + str(dUnit["fieldindex"]) + " for value " + sReadValue)
                else:
                        Domoticz.Error("Received unexpected value " + sReadValue)
                            
        # Data received, going back to "connected" connection step
        self.sConnectionStep = "connected"
        # Handle fifo if there are still command to proceed
        self.handleFifo()

    # parse JSON data received from ebusd
    #   sData: string: data received
    def parseJson(self, sData):
        self.bStillToLook = False
        try:
            dJson = json.loads(sData, object_pairs_hook= lambda dict: CaseInsensitiveDict(dict))
            # dJson = json.loads(sData)
        except Exception as e:
            self.bStillToLook = True
            Domoticz.Error("Impossible to parse JSON (buffer size " + str(len(sData)) + "). " + traceback.format_exc())
            return     

        iCount = 0
        if ("global" in dJson) and ("messages" in dJson["global"]):
            iCount = dJson["global"]["messages"]
        if iCount == 0:
            self.bStillToLook = True
            return
        if iCount == self.iJsonObjects:
            return
        
        # self.myDebug("Building messages list for " + str(iCount) + " messages")
        self.bStillToLook = True
        self.iJsonObjects = iCount
        if iCount:
            self.dMessages = {}
            for sCircuit, dItem in dJson.items():
                sCircuit = sCircuit.lower()
                if sCircuit == "global":
                    continue
                if sCircuit.startswith("scan."):
                    continue
                # self.myDebug("Exploring circuit " + sCircuit)
                if ("messages" in dItem) and (sCircuit != "global"):
                    for sMessage, dMessageItem in dItem["messages"].items():                                                         
                        # self.myDebug("Exploring message " + sMessage)
                        if ("name" in dMessageItem) and dMessageItem["name"] and ("fielddefs" in dMessageItem) and (len(dMessageItem["fielddefs"]) > 0):
                            sMessage = sMessage.lower()
                            sMessage = re.sub(r'\[.*\]', '', sMessage)
                            if sMessage.endswith("-w"):
                                continue
                            # self.myDebug("Add " + sCircuit+":"+sMessage + " to messages list")
                            # self.dMessages[sCircuit+":"+sMessage] = dMessageItem
                            for iFieldIndex, iFieldElement in enumerate(dMessageItem["fielddefs"]):
                                # self.myDebug("Add " + sCircuit+":"+sMessage+":"+str(iFieldIndex) + " to messages list")
                                self.dMessages[sCircuit+":"+sMessage+":"+str(iFieldIndex)] = dMessageItem
                                for dField in dMessageItem["fielddefs"]:
                                    if "name" in dField and dField["name"]:
                                        self.dMessages[sCircuit+":"+sMessage+":"+dField["name"]] = dMessageItem
                                        # self.myDebug("Add " + sCircuit+":"+sMessage+":"+dField["name"] + " to messages list")
                
        timeNow = time.time()
        
        if not self.sRegExSearch:
            sUnits = self.sParamRegisters.strip()
            if len(sUnits) == 0 :
                self.sRegExSearch = re.compile(".*", re.IGNORECASE)
            else:
                self.sRegExSearch = re.compile("|".join(shlex.split(sUnits)), re.IGNORECASE)
        
        self.myDebug("Search pattern is " + str(self.sRegExSearch))
            
        for sRegister in self.dMessages:
            # sDeviceIDField0 = sRegister + ":0"
            # if not (sRegister in self.dUnitsByDeviceID) and (self.sRegExSearch.search(sRegister) or self.sRegExSearch.fullmatch(sDeviceIDField0)):
            if self.sRegExSearch.search(sRegister):
                # now split device in circuit/message/fieldnumber
                #lPath = sRegister.split("-")
                lPath = sRegister.split(":")
                # if it seems incorrect
                sCircuit = lPath[0]
                sMessage = lPath[1]
                sFieldIndex = lPath[2]
                # check if writable
                sWKey = sMessage + "-w"
                if (not self.bParamReadOnly) and (sWKey in dJson[sCircuit]["messages"]) and ("write" in dJson[sCircuit]["messages"][sWKey]) and dJson[sCircuit]["messages"][sWKey]["write"] :
                    self.myDebug("Writable")
                    dMessage = dJson[sCircuit]["messages"][sWKey]
                    bWritable = True
                else:
                    dMessage = dJson[sCircuit]["messages"][sMessage]
                    bWritable = False

                # try to get fieldnumber, if not an integer, try by name
                self.myDebug("Look for field " + sFieldIndex + " in JSON data")
                iFieldsCount = 0
                iFieldAbsoluteIndex = -1
                if sFieldIndex.isdigit():
                    iFieldIndex = int(sFieldIndex)
                    for iAllFieldsIndex, dAllFieldDefs in enumerate(dMessage["fielddefs"]):
                        sAllFieldType = getFieldType(dAllFieldDefs["unit"], dAllFieldDefs["name"], dAllFieldDefs["type"])
                        if sAllFieldType != "ignore":
                            if iFieldIndex == iFieldsCount:
                                iFieldAbsoluteIndex = iAllFieldsIndex                                    
                            iFieldsCount += 1
                else:
                    for iAllFieldsIndex, dAllFieldDefs in enumerate(dMessage["fielddefs"]):
                        sAllFieldType = getFieldType(dAllFieldDefs["unit"], dAllFieldDefs["name"], dAllFieldDefs["type"])
                        if sAllFieldType != "ignore":
                            if dAllFieldDefs["name"].lower() == sFieldIndex:
                                iFieldIndex = iFieldsCount
                                iFieldAbsoluteIndex = iAllFieldsIndex                                    
                                self.myDebug("Field number of device " + sRegister + " is " + str(iFieldIndex))
                            iFieldsCount += 1
                if iFieldAbsoluteIndex < 0:
                        Domoticz.Error("Cannot find usable field for device " + sRegister)
                        # error on this item, mark device as erroneous and go to next item
                        self.dUnitsByDeviceID[sRegister] = "no usable field for device"
                        continue                               
                #flen = len(dMessage["fielddefs"])
                #if bWritable and (flen > 1):
                    #Domoticz.Error("Register " + sCircuit + "-" + sMessage + " has " + str(flen) + " fields and is writable, more than one field and writable isn't supported yet, the register will be read only")
                    #bWritable = False
                #flen = len(dMessage["fielddefs"])
                #if bWritable and (flen > 1):
                    #Domoticz.Error("Register " + sCircuit + "-" + sMessage + " has " + str(flen) + " fields and is writable, more than one field and writable isn't supported yet, the register will be read only")
                    #bWritable = False
                    
                # count fields and keep track of field index, absolute and relative (ignoring IGN fields)
                sDeviceIntegerID = sCircuit + ":" + sMessage + ":" + str(iFieldIndex)
                
                # we skip if already added (by field id or field name or previous parse)
                if sDeviceIntegerID in self.dUnitsByDeviceID:
                    continue
                
                dFieldDefs = dMessage["fielddefs"][iFieldAbsoluteIndex]
                sFieldType = getFieldType(dFieldDefs["unit"], dFieldDefs["name"], dFieldDefs["type"])

                #sTypeName = ""
                iSwitchType = -1
                dValues = None
                dOptions = {}
                dOptionsMapping = {}
                dReverseOptionsMapping = {}
                bAlwaysRefresh = False
                # now we try to get the best match between domoticz sensor and ebusd field type
                # https://github.com/domoticz/domoticz/blob/master/hardware/hardwaretypes.h ligne 42
                # https://github.com/domoticz/domoticz/blob/master/hardware/plugins/PythonObjects.cpp ligne 410
                sFieldType = getFieldType(dFieldDefs["unit"], dFieldDefs["name"], dFieldDefs["type"])
                self.myDebug("Field is type " + sFieldType)
                # on/off type
                #if (sFieldType == "switch") and bWritable:
                if (sFieldType == "switchonoff") or (sFieldType == "switchyesno"):
                    iMainType = 0xF4
                    iSubType = 0x49
                    if bWritable:
                        iSwitchType = 0
                    else:
                        iSwitchType = 2
                    bHandleTimeout = True
                # selector switch type
                elif ("values" in dFieldDefs):
                    if bWritable:
                        #sTypeName = "Selector Switch"
                        iMainType = 0xF4
                        iSubType = 0x3E
                        iSwitchType = 18
                    else:
                        #sTypeName = "Text"
                        iMainType = 0xF3
                        iSubType = 0x13
                    dValues = dFieldDefs["values"]
                    sLevelActions = "|"
                    sLevelNames = "|"
                    for iIndexValue, sValue in enumerate(sorted(dValues.values())):
                        if iIndexValue > 0:
                            sLevelActions += "|"
                            sLevelNames += "|"
                        sLevelNames += str(sValue)
                        iIndexValue += 1
                        iIndexValue *= 10
                        if bWritable:
                            dOptionsMapping[sValue] = iIndexValue
                        else:
                            dOptionsMapping[sValue] = sValue
                        dReverseOptionsMapping[iIndexValue] = sValue
                    self.myDebug("LevelNames for Domoticz are " + sLevelNames)
                    dOptions = {"LevelActions": sLevelActions, "LevelNames": sLevelNames, "LevelOffHidden": "true", "SelectorStyle": "1"}
                # number type, probably to improve
                elif (sFieldType == "number") or (sFieldType == "custom"):
                    #sTypeName = "Custom"
                    iMainType = 0xF3
                    iSubType = 0x1F
                    dOptions = { "Custom": "1;" + str(dFieldDefs["unit"])}
                # setpoint type
                elif (sFieldType == "temperature") and bWritable:
                    iMainType = 0xF2
                    iSubType = 0x01
                # read-only temperature type
                elif (sFieldType == "temperature"):
                    #sTypeName = "Temperature"
                    iMainType = 0x50
                    iSubType = 0x05
                    bAlwaysRefresh = True
                # pressure type
                elif (sFieldType == "pressure"):
                    #sTypeName = "Pressure"
                    iMainType = 0xF3
                    iSubType = 0x09
                    bAlwaysRefresh = True
                # else text type
                else:
                    #sTypeName = "Text"
                    iMainType = 0xF3
                    iSubType = 0x13
                    
                # check if device is already in domoticz database, based on deviceid
                bFound = False
                bForceRefresh = False
                for sCurrentDeviceID, oDevice in Devices.items():
                    # .lower() for backward compatibility
                    if sCurrentDeviceID.lower() == sDeviceIntegerID:
                        sDeviceIntegerID = sCurrentDeviceID
                        for iIndexUnit, oUnit in oDevice.Units.items():
                            if (oUnit.Type != iMainType) or (oUnit.SubType != iSubType):
                                Domoticz.Log("Device " + oUnit.Name + " type changed, updating Domoticz database")
                                bForceRefresh = True
                                if iSwitchType >= 0:
                                    oUnit.SwitchType=iSwitchType
                                oUnit.Type=iMainType
                                oUnit.SubType=iSubType
                                oUnit.Options=dOptions
                                oUnit.Update(Log=False)
                                oUnit.Parent.TimedOut=0
                            # log device found, with dFieldDefs["name"] and dFieldDefs["comment"] giving hints on how to use register
                            Domoticz.Log("Device " + oUnit.Name + " unit " + str(iIndexUnit) + " and deviceid " + sDeviceIntegerID + " detected: " + dFieldDefs["name"] + " - " + dFieldDefs["comment"])
                            # if found, continue loop to next item
                            bFound = True
                            break
                        break

                # not in database: add device
                if not bFound:
                    bForceRefresh = True
                    # domoticz database doesn't handle more than 256 devices per plugin !
                    iIndexUnit = 1
                    # Create name
                    sCompleteName = sCircuit + " - " + sMessage
                    if dFieldDefs["name"] != "":
                        sCompleteName += " - " + dFieldDefs["name"]
                    else:
                        sCompleteName += " - " + sFieldIndex
                    # create device, log dFieldDefs["name"] and dFieldDefs["comment"] giving hints on how to use register
                    if iSwitchtype >= 0:
                        Domoticz.Unit(Name=sCompleteName, Unit=iIndexUnit, Type=iMainType, Subtype=iSubType, Switchtype=iSwitchType, Description=dFieldDefs["comment"], Options=dOptions, Used=1, DeviceID=sDeviceIntegerID).Create()
                        if (sDeviceIntegerID in Devices) and (iIndexUnit in Devices[sDeviceIntegerID].Units):
                            Domoticz.Log("Add device " + sDeviceIntegerID + " unit " + str(iIndexUnit) + " as type " + str(iMainType) + ", subtype " + str(iSubType) + " and switchtype " + str(iSwitchType) + ": " + dFieldDefs["name"] + " - " + dFieldDefs["comment"])
                        else:
                            Domoticz.Error("Cannot add device " + sDeviceIntegerID + " unit " + str(iIndexUnit) + ". Check in settings that Domoticz is set up to accept new devices")
                            self.bStillToLook = True
                            break
                    else:
                        Domoticz.Unit(Name=sCompleteName, Unit=iIndexUnit, Type=iMainType, Subtype=iSubType, Description=dFieldDefs["name"] + " - " + dFieldDefs["comment"], Options=dOptions, Used=1, DeviceID=sDeviceIntegerID).Create()
                        if (sDeviceIntegerID in Devices) and (iIndexUnit in Devices[sDeviceIntegerID].Units):
                            Domoticz.Log("Add device " + sDeviceIntegerID + " unit " + str(iIndexUnit) + " as type " + str(iMainType) + " and subtype " + str(iSubType) + ": " + dFieldDefs["name"] + " - " + dFieldDefs["comment"])
                        else:
                            Domoticz.Error("Cannot add device " + sDeviceIntegerID + " unit " + str(iIndexUnit) + ". Check in settings that Domoticz is set up to accept new devices")
                            self.bStillToLook = True
                            break
                    
                # incorporate found or created device to local self.dUnits dictionnaries, to keep additionnal parameters used by the plugin
                self.dUnitsByDeviceID[sDeviceIntegerID] = { "device":Devices[sDeviceIntegerID].Units[iIndexUnit], "circuit":sCircuit, "message":sMessage, "fieldindex":iFieldIndex, "fieldscount":iFieldsCount, "options":dOptionsMapping, "reverseoptions":dReverseOptionsMapping, "domoticzoptions": dOptions, "fieldtype": sFieldType, "forcerefresh": bForceRefresh, "alwaysrefresh": bAlwaysRefresh }
                # set fieldsvaluestimestamp for read then write timeout
                self.dUnitsByDeviceID[sDeviceIntegerID]["fieldsvaluestimestamp"] = timeNow - (2 * self.iTimeoutConstant)
                if not sCircuit in self.dUnits3D:
                    self.dUnits3D[sCircuit] = {}
                if not sMessage in self.dUnits3D[sCircuit]:
                    self.dUnits3D[sCircuit][sMessage] = {}
                self.dUnits3D[sCircuit][sMessage][iFieldIndex] = self.dUnitsByDeviceID[sDeviceIntegerID]
                # place a read command in the queue for each device to refresh its value asap
                self.read(self.dUnitsByDeviceID[sDeviceIntegerID])

    def onStart(self):
        Domoticz.Debug("onStart called")
        # Ignore username and password, I'm not sure when I should authenticate and it can be handled by ACL file directly by ebusd
        #Domoticz.Log("Username set to " + Parameters["Username"])
        self.sParamAddress = Parameters["Address"]
        try:
            self.iParamTelnetPort = int(Parameters["Port"])
        except ValueError:
            Domoticz.Error("HTTP port parameter incorrect, set to its default value")
        try:
            self.iParamJsonPort = int(Parameters["Mode1"])
        except ValueError:
            Domoticz.Error("JSON port parameter incorrect, set to its default value")
        self.sParamRegisters = Parameters["Mode2"]
        try:
            self.iParamRefreshRate = int(Parameters["Mode3"])
        except ValueError:
            Domoticz.Error("Refresh rate parameter incorrect, set to its default value")
        self.bParamDisableCache = Parameters["Mode4"] == "True"
        self.bParamReadOnly = Parameters["Mode5"] == "True"
        try:
            self.iParamDebug = int(Parameters["Mode6"])
        except ValueError:
            Domoticz.Error("Debug level parameter incorrect, set to its default value")

        matchVersions = re.search(r"(\d+)\.(\d+)", Parameters["DomoticzVersion"])
        if (matchVersions):
            iVersionMaj = int(matchVersions.group(1))
            iVersionMin = int(matchVersions.group(2))
            iVersion = (iVersionMaj * 1000000) + iVersionMin
            if iVersion < 2024000001:
                Domoticz.Error("Your Domoticz version is too old for the plugin to work properly, you might observe unexpected behavior")

        Domoticz.Log("This plugin is compatible with Domoticz version 2024.1 onwards")
        Domoticz.Log("IP or named address set to " + self.sParamAddress)
        Domoticz.Log("Telnet port set to " + str(self.iParamTelnetPort))
        Domoticz.Log("JSON  HTTP port set to " + str(self.iParamJsonPort))
        Domoticz.Log("Refresh rate set to " + str(self.iParamRefreshRate))
        Domoticz.Log("Registers set to " + self.sParamRegisters)
        Domoticz.Log("Disable cache set to " + str(self.bParamDisableCache))
        Domoticz.Log("Read-only set to " + str(self.bParamReadOnly))
        Domoticz.Log("Debug set to " + str(self.iParamDebug))
            
        # most init
        self.__init__()

        # enable debug if required
        if self.iParamDebug > 1:
            Domoticz.Debugging(1)            

        # set heartbeat interval	
        if self.iParamRefreshRate < self.iMaxHeartbeatInterval:
            Domoticz.Heartbeat(self.iParamRefreshRate)
        else:
            Domoticz.Heartbeat(self.iMaxHeartbeatInterval)

        # we need to let at least 2 heartbeats before discovering to launch discovering then populate dUnits dict
        if self.iDiscoverTime < (3 * self.iParamRefreshRate):
            self.iDiscoverTime = 3 * self.iParamRefreshRate

        # now we can enabling the plugin
        self.bIsStarted = True
        # Ignore username and password, I'm not sure when I should authenticate and it can be handled by ACL file directly by ebusd
        #if Parameters["Username"] != "":
            #self.dqFifo.append({"operation":"authenticate"})
        # first scan of available registers
        self.findDevices()

    def onStop(self):
        Domoticz.Debug("onStop called")
        # prevent error messages during disabling plugin
        self.bIsStarted = False
        # close connections
        if self.telnetConn != None:
            if self.telnetConn.Connected():
                self.telnetConn.Disconnect()
        if self.jsonConn != None:
            if self.jsonConn.Connected():
                self.jsonConn.Disconnect()
        self.__init__()        

    def onConnect(self, Connection, Status, Description):
        Domoticz.Debug("onConnect called")
        if self.bIsStarted:
            if ((Connection == self.jsonConn) and (Status == 0)):
                self.myDebug("onConnect for json called")
                self.findDevices()
            elif ((Connection == self.telnetConn) and (Status == 0)):
                self.myDebug("onConnect for telnet called")
                self.sConnectionStep = "connected"
                self.handleFifo()

    def onMessage(self, Connection, Data):
        Domoticz.Debug("onMessage called")

        # if started and not stopping
        if self.bIsStarted:
            # message for finddevices: JSON HTTP response, buffer completion is handled by domoticz HTTP protocol
            if (Connection == self.jsonConn):       
                sData = Data["Data"].decode("utf-8", "ignore")
                Status = int(Data["Status"])

                if (Status == 200):
                    self.myDebug("Good Response received from ebusd : length " + str(len(sData)))
                    #self.jsonConn.Disconnect()
                    # now parse
                    self.parseJson(sData)
                else:
                    Domoticz.Error("ebusd JSON HTTP interface returned a status: " + str(Status))
            # telnet answer, buffer may be incomplete, we wait for \n\n to be sure to get complete response, buffer completion is not handled by domoticz line protocol
            else:
                sData = Data.decode("utf-8", "ignore")
                # self.myDebug("Received data size " + str(len(sData)) + ": '"+sData+"'")
                # we limit buffer size to keep memory, telnet answer shouldn't be big, as used by the plugin
                if len(self.sBuffer) > 100000:
                    self.sBuffer = ""
                self.sBuffer += sData
                # \n\n is the end of telnet response send by ebusd
                if sData.endswith("\n\n"):
                    # self.myDebug("Received buffer size " + str(len(self.sBuffer)) + ": '"+self.sBuffer+"'")
                    # now parse
                    self.parseTelnet(self.sBuffer)
                    # empty buffer
                    self.sBuffer = ""

    def onCommand(self, DeviceID, Unit, Command, Level, Hue):
        Domoticz.Debug("onCommand called for device " + str(DeviceID) + " unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level) + ", Hue: " + str(Hue))
        # if started and not stopping
        if self.bIsStarted:
            # add write to the queue
            self.write(DeviceID, Command, Level, "")

    def onDeviceModified(self, DeviceID, Unit):
        Domoticz.Debug("onDeviceModified called for device " + str(DeviceID) + " unit " + str(Unit))
        # if started and not stopping
        if self.bIsStarted:
            # add write to the queue
            self.write(DeviceID, Unit, "udevice", Devices[DeviceID].Units[Unit].nValue, Devices[DeviceID].Units[Unit].sValue)

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Debug("onNotification called: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(Priority) + "," + Sound + "," + ImageFile)

    def onDisconnect(self, Connection):
        Domoticz.Debug("onDisconnect called")

    # Add a read command to the queue
    #   dUnit: dict
    def read(self, dUnit):
        if type(dUnit) is dict:
            self.myDebug("read called for circuit " + dUnit["circuit"] + " message " + dUnit["message"] + " field " + str(dUnit["fieldindex"]))
            self.dqFifo.append({"operation":"read", "unit":dUnit})
            self.handleFifo()
        else:
            Domoticz.Error("Cannot read device that is in error state: " + dUnit)
    
    # Will write a value to ebusd
    #   sDeviceID: string: device in Devices dict
    #   ifLevel: integer or float: value to write
    def write(self, sDeviceID, iUnitNumber, sCommand, ifValue, sValue):
        Domoticz.Debug("write called for device " + str(sDeviceID) + " command " + sCommand + " value " + str(ifValue) + " / " + sValue)
        if self.bParamReadOnly:
            Domoticz.Debug("Cannot write device " + str(sDeviceID) + " because the read-only parameter is set")
            return
        elif sDeviceID in self.dUnitsByDeviceID:
            dUnit = self.dUnitsByDeviceID[sDeviceID]
            # convert domoticz command and level to ebusd string value
            sValue = valueDomoticzToEbusd(dUnit, sCommand, ifValue, sValue, Devices[DeviceID].Units[iUnitNumber].nValue, Devices[DeviceID].Units[iUnitNumber].sValue)
                    
            # if there are more than one field, we must read all fields, modify the required field and write back all fields at once
            iFieldsCount = dUnit["fieldscount"]
            if iFieldsCount <= 1:
                self.myDebug("Will write " + sValue)
                self.dqFifo.append({"operation":"write", "unit":dUnit, "value":sValue})
                # write then read to update Domoticz interface
                self.dqFifo.append({"operation":"read", "unit":dUnit})
                # launch commands in the queue
                self.handleFifo()
            else:
                self.myDebug("Will write (more than one field) " + sValue)
                # read all fields first before write one field when more than one field in the message
                self.dqFifo.append({"operation":"read", "unit":dUnit})
                self.dqFifo.append({"operation":"write", "unit":dUnit, "value":sValue})
                # write then read to update Domoticz interface
                self.dqFifo.append({"operation":"read", "unit":dUnit})
                # launch commands in the queue
                self.handleFifo()
        else:
            Domoticz.Error("Cannot write device " + str(sDeviceID) + " that doesn't exist")

    # Handle the connection to Telnet port and the command queue
    def handleFifo(self):
        Domoticz.Debug("handleFifo() called")
        timeNow = time.time()
        # init of self.iConnectionTimestamp
        if self.iConnectionTimestamp == 0 :
            self.iConnectionTimestamp = timeNow
        # telnet connection not connected yet or no data processing
        if ((self.sConnectionStep == "idle") or (self.sConnectionStep == "connected")) and (len(self.dqFifo) > 0):
            # record time
            self.iConnectionTimestamp = timeNow
            # create connection
            if self.telnetConn == None:
                self.myDebug("handleFifo() create connection to " + self.sParamAddress + ":" + str(self.iParamTelnetPort))
                self.telnetConn = Domoticz.Connection(Name="Telnet", Transport="TCP/IP", Protocol="", Address=self.sParamAddress, Port=str(self.iParamTelnetPort))
            if not self.telnetConn.Connected():
                self.myDebug("Connect")
                self.sConnectionStep = "connecting"
                self.telnetConn.Connect()
            # or process queue
            else:
                self.myDebug("Handle")
                # pop command from queue (first in first out)
                # pop command from queue (first in first out)
                sCommand = self.dqFifo.popleft()
                dUnit = sCommand["unit"]
                self.sConnectionStep = "data sending"
                if type(dUnit) is dict:
                    self.sCurrentCommand = sCommand["operation"]
                    # read command
                    if self.sCurrentCommand == "read":
                        #self.telnetConn.Send("read -c " + dUnit["circuit"] + " " + dUnit["message"] + "\r\n")
                        #self.telnetConn.Send("read -c " + dUnit["circuit"] + " " + dUnit["message"] + " " + dUnit["fieldname"] + "." + str(dUnit["fieldindex"]) + "\r\n")
                        # telnet read command in verbose mode
                        sRead = "read "
                        # if no cache
                        if self.bParamDisableCache :
                            sRead = sRead + "-f "
                        sRead = sRead + " -v -c " + dUnit["circuit"] + " " + dUnit["message"] + "\r\n"
                        self.myDebug("Telnet write: " + sRead)
                        self.telnetConn.Send(sRead)
                    # write command
                    elif self.sCurrentCommand == "write" and (not self.bParamReadOnly):
                        iFieldsCount = dUnit["fieldscount"]
                        # we have more than one field, retrieve all fields value (from last read) if not too old, modify the field and write
                        if iFieldsCount > 1:
                            if ((dUnit["fieldsvaluestimestamp"] + self.iTimeoutConstant) >= timeNow):
                                # fields in a string are separated by ;
                                lData = dUnit["fieldsvalues"].split(";")
                                # sanity check
                                if len(lData) != iFieldsCount: 
                                    Domoticz.Error("Field count is not " + str(iFieldsCount) + " as expected")
                                else:
                                    # modify register
                                    lData[dUnit["fieldindex"]] = sCommand["value"]
                                    # rebuild the fields for the message, in a string, with ; as separator
                                    sData = ";".join(lData)
                                    # telnet write command
                                    sWrite = "write -c " + dUnit["circuit"] + " " + dUnit["message"] + " " + sData + "\r\n"
                                    self.myDebug("Telnet write: " + sWrite)
                                    self.telnetConn.Send(sWrite)
                            else:
                                Domoticz.Error("Data cached is too old or inexistent, won't take the risk to modify many fields at once")
                        else:
                            # telnet write command if only one field in message
                            sWrite = "write -c " + dUnit["circuit"] + " " + dUnit["message"] + " " + sCommand["value"] + "\r\n"
                            self.myDebug("Telnet write: " + sWrite)
                            self.telnetConn.Send(sWrite)
                    # Ignore username and password, I'm not sure when I should authenticate and it can be handled by ACL file directly by ebusd
                    #elif self.sCurrentCommand == "authenticate":
                            #sWrite = "auth " + Parameters["Username"] + " " + Parameters["Password"] + "\r\n"
                            #self.myDebug("Telnet write:" + sWrite)
                else:
                    Domoticz.Error("Received command for unit in error state: " + dUnit)
        # the plugin seems blocked in connecting or data sending step, restart the plugin
        elif (len(self.dqFifo) > 0) and (timeNow >= (self.iConnectionTimestamp + self.iTimeoutConstant)) :
            Domoticz.Error("Timeout during handleFifo, ask to restart plugin")
            self.bShallRestart = True
            return
        
    def onHeartbeat(self):
        Domoticz.Debug("onHeartbeat() called")
        # if started and not stopping
        if self.bIsStarted:
            # restart pending ?
            if self.bShallRestart:
                self.onStop()
                self.onStart()
            else:
                timeNow = time.time()
                # refresh
                if (timeNow >= (self.iRefreshTime + self.iParamRefreshRate)) :
                    # refresh values of already detected registers
                    for sCircuit in self.dUnits3D:
                        for sMessage in self.dUnits3D[sCircuit]:
                            # only refresh first found field, read operation will read all declared fields anyway
                            dUnit = next(iter(self.dUnits3D[sCircuit][sMessage].values()), None)
                            if dUnit:
                                self.read(dUnit)
                    # check for timeouts
                    for sDeviceID, oDevice in Devices.items():
                        if not oDevice.TimedOut:
                            bTimedOut = False                    
                            if sDeviceID in self.dUnitsByDeviceID:
                                dUnit = self.dUnitsByDeviceID[sDeviceID]
                                if (dUnit["fieldsvaluestimestamp"] + (3 * self.iParamRefreshRate)) < timeNow:
                                    bTimedOut = True
                            else:
                                if timeNow >= (self.iDiscoverStartTime + self.iDiscoverTime):
                                    bTimedOut = True
                            if bTimedOut:
                                Domoticz.Error("DeviceID " + oDevice.DeviceID + " timed out")
                                oDevice.TimedOut=1
                    # we still not have detected all registers given in configuration, retry JSON search
                    if self.bStillToLook or (timeNow >= (self.iRefreshFindDeviceTime + self.iRefreshFindDeviceRate)) :
                        self.findDevices()
                        self.iRefreshFindDeviceTime = timeNow
                    self.iRefreshTime = timeNow

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onConnect(Connection, Status, Description):
    global _plugin
    _plugin.onConnect(Connection, Status, Description)

def onMessage(Connection, Data):
    global _plugin
    _plugin.onMessage(Connection, Data)

def onCommand(DeviceID, Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(DeviceID, Unit, Command, Level, Hue)

def onDeviceAdded(DeviceID, Unit):
    global _plugin

def onDeviceModified(DeviceID, Unit):
    global _plugin
    _plugin.onDeviceModified(DeviceID, Unit)

def onDeviceRemoved(DeviceID, Unit):
    global _plugin

def onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile):
    global _plugin
    _plugin.onNotification(Name, Subject, Text, Status, Priority, Sound, ImageFile)

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

# Generic helper functions
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device timeout: " + str(Devices[x].TimedOut))
        Domoticz.Debug("Units count: " + str(len(Devices[x].Units)))
        for y in Devices[x].Units:
            Domoticz.Debug("Device:           " + str(y) + " - " + str(Devices[x].Units[y]))
            Domoticz.Debug("Device ID:       '" + str(Devices[x].Units[y].ID) + "'")
            Domoticz.Debug("Device Name:     '" + Devices[x].Units[y].Name + "'")
            Domoticz.Debug("Device iValue:    " + str(Devices[x].Units[y].iValue))
            Domoticz.Debug("Device sValue:   '" + Devices[x].Units[y].sValue + "'")
            Domoticz.Debug("Device LastLevel: " + str(Devices[x].Units[y].LastLevel))
    return

# give a type name based of unit (sFieldUnit: string), name (sFieldName: string) and type (sFieldType: string) of ebusd fielddefs
def getFieldType(sFieldUnit, sFieldName, sFieldType):
    if sFieldType == "IGN":
        return "ignore"
    elif sFieldUnit == "°C":
        return "temperature"
    elif sFieldUnit == "bar":
        return "pressure"
    elif sFieldUnit == "min":
        return "number"
    elif sFieldUnit == "h":
        return "number"
    elif sFieldUnit == "s":
        return "number"
    elif sFieldUnit != "":
        return "custom"
    elif sFieldName == "onoff":
        return "switchonoff"
    elif sFieldName == "yesno":
        return "switchyesno"
    return {
        "UCH": "number",
        "BCD": "number",
        "BCD:2": "number",
        "BCD:3": "number",
        "BCD:4": "number",
        "HCD": "number",
        "HCD:2": "number",
        "HCD:3": "number",
        "HCD:4": "number",
        "PIN": "number",
        "UCH": "number",
        "SCH": "number",
        "D1B": "number",
        "D1C": "number",
        "D2B": "number",
        "D2C": "number",
        "FLT": "number",
        "FLR": "number",
        "EXP": "number",
        "EXR": "number",
        "UIN": "number",
        "UIR": "number",
        "SIN": "number",
        "SIR": "number",
        "U3N": "number",
        "U3R": "number",
        "S3N": "number",
        "S3R": "number",
        "ULG": "number",
        "ULR": "number",
        "SLG": "number",
        "SLR": "number",
        "BI0": "number",
        "BI1": "number",
        "BI2": "number",
        "BI2": "number",
        "BI3": "number",
        "BI4": "number",
        "BI5": "number",
        "BI6": "number",
        "TEM_P": "number"
        }.get(sFieldType, "text")

# convert domoticz sCommand (string) and ifValue (integer of float) or sValue (string) to string value for ebusd, for dUnit (dictionnary)
def valueDomoticzToEbusd(dUnit, sCommand, ifValue, sValue, previousIValue, previousSValue):
    sLowerCommand = sCommand.lower()
    dReverseOptionsMapping = dUnit["reverseoptions"]
    if len(dReverseOptionsMapping) > 0:
        if ifValue in dReverseOptionsMapping:
            return dReverseOptionsMapping[ifValue]
        else:
            return str(ifValue)
    elif (sLowerCommand == "on") or (sLowerCommand == "yes"):
        if dUnit["fieldtype"] == "switchyesno":
            return "yes"
        else:
            return "on"
    elif (sLowerCommand == "off") or (sLowerCommand == "no"):
        if dUnit["fieldtype"] == "switchyesno":
            return "no"
        else:
            return "off"
    elif sLowerCommand == "toggle":
        if previousIValue:
            if dUnit["fieldtype"] == "switchyesno":
                return "no"
            else:
                return "off"
        else:
            if dUnit["fieldtype"] == "switchyesno":
                return "yes"
            else:
                return "on"
    else:
        if dUnit["fieldtype"] == "switchonoff":
            if ifValue == 0:
                return "off"
            else:
                return "on"
        elif dUnit["fieldtype"] == "switchyesno":
            if ifValue == 0:
                return "no"
            else:
                return "yes"
        elif sValue:
            return sValue
        else:
            return str(ifValue)
            
    return ""

# convert ebus sFieldValue (string) to integer, string values for domoticz, for dUnit (dictionnary)
def valueEbusdToDomoticz(dUnit, sFieldValue):
    dOptionsMapping = dUnit["options"]
    if len(dOptionsMapping) > 0:
        if sFieldValue in dOptionsMapping:
            # iValue from GetLightStatus in RFXName.cpp and hardwaretypes.h
            iValue = 2
            sValue = str(dOptionsMapping[sFieldValue])
        else:
            try:
                iValue = int(sFieldValue)
            except ValueError:
                iValue = 0
            sValue = sFieldValue
    else:
        sLowerFieldValue = sFieldValue.lower()
        if (sLowerFieldValue == "on") or (sLowerFieldValue == "yes"):
            iValue = 1
            sValue = "100"
        elif (sLowerFieldValue == "off") or (sLowerFieldValue == "no"):
            iValue = 0
            sValue = "0"
        else:
            try:
                iValue = int(sFieldValue)
            except ValueError:
                iValue = 0
            sValue = sFieldValue

    # prevent overflow when translating to C language
    if iValue >= 2147483647:
        Domoticz.Debug("Integer value too big, converted to 0, for circuit " + dUnit["circuit"] + " message " + dUnit["message"] + " field " + str(dUnit["fieldindex"]))
        iValue = 0
   
    return iValue, sValue
