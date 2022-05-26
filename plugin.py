#           ebusd Plugin
#
#           Author:     Barberousse, z1mEk, 2017-2018
#           MIT license
#
"""
<plugin key="ebusd" name="ebusd bridge" author="Barberousse" version="1.4.4" externallink="https://github.com/guillaumezin/DomoticzEbusd">
    <params>
        <!-- <param field="Username" label="Username (left empty if authentication not needed)" width="200px" required="false" default=""/>
        <param field="Password" label="Password" width="200px" required="false" default="" password="true"/> -->
        <param field="Address" label="IP or named address" width="200px" required="true" default="127.0.0.1"/>
        <param field="Port" label="Telnet port" width="100px" required="true" default="8888"/>
        <param field="Mode1" label="JSON HTTP port" width="100px" required="true" default="8889"/>
        <param field="Mode2" label="Registers" width="1000px" required="true" default=""/>
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

import Domoticz
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

    def __setitem__(self, key, value):
        # Use the lowercased key for lookups, but store the actual
        # key alongside the value.
        self._store[key.lower()] = (key, value)

    def __getitem__(self, key):
        return self._store[key.lower()][1]

    def __delitem__(self, key):
        del self._store[key.lower()]

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
    # boolean that indicates that some registers were'nt found yet
    bStillToLook = None
    # integer to keep time of last refresh
    iRefreshTime = None
    # integer that reflects the refresh time set in Parameters["Mode3"]
    iRefreshRate = None
    # dictionnary of dictonnaries, keyed by deviceid string (circuit:register:fieldindex, for instance "f47:OutsideTemp:0")
    #   "device": object: object corresponding in Devices dict
    #   "circuit": string: circuit name, for instance "f47"
    #   "register": string: register, for instance "OutsideTemp"
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
    # same dictionnary, but keyed by unit number
    dUnitsByUnitNumber = None
    # same dictionnary, but keyed by 3 dimensions: dUnits3D[circuit][register][fieldindex]
    dUnits3D = None
    # dequeue of dictionnaries
    #   "operation": string: can be "read", "readwhole", "write", "authenticate"
    #   "unit": dict contained in dUnitsByUnitNumber
    #   "value": string: value to write in ebusd format, used only for "write" operation
    dqFifo = None
    # string that contains the connection step: "idle", then "connecting", then "connected", then "data sending"
    sConnectionStep = None
    # integer: time when connection step has been updated
    iConnectionTimestamp = None
    # string: keep track of current operation, see dfFifo
    sCurrentCommand = None
    # integer: timeout in s
    timeoutConstant = 10
    # integer: max heartbeat interval in s
    maxHeartbeatInterval = 30
    # integer: debug level
    iDebugLevel = 0
    
    def __init__(self):
        self.bIsStarted = False
        self.bShallRestart = False
        self.telnetConn = None
        self.jsonConn = None
        self.dUnitsByDeviceID = {}
        self.dUnitsByUnitNumber = {}
        self.dUnits3D = {}
        self.sBuffer = ""
        self.bStillToLook = True
        self.iRefreshTime = 0
        self.iRefreshRate = 1000
        self.dqFifo = deque()
        self.sConnectionStep = "idle"
        self.iConnectionTimestamp = 0
        self.sCurrentCommand = ""

    def myDebug(self, message):
        if self.iDebugLevel:
            Domoticz.Log(message)

    # Connect to JSON HTTP port to get list of ebusd devices
    def findDevices(self):
        if self.jsonConn == None:
            self.myDebug("findDevices() create connection to " + Parameters["Address"] + ":" + Parameters["Mode1"])
            self.jsonConn = Domoticz.Connection(Name="JSON HTTP", Transport="TCP/IP", Protocol="HTTP", Address=Parameters["Address"], Port=Parameters["Mode1"])

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
                                        "Host": Parameters["Address"]+":"+Parameters["Mode1"], \
                                        "User-Agent":"Domoticz/1.0" }
                       }
            self.jsonConn.Send(sendData)            
     
    #def parseTelnet(self, localStrBuffer):
        #Domoticz.Log("Parse telnet buffer size " + str(len(localStrBuffer)))
        #lLines = localStrBuffer.splitlines()
        #for sLine in lLines:
            #Domoticz.Log(" -- line " + sLine)
            #Domoticz.Log(" -- line2 " + sLine.replace("="," "))
            #sParams = sLine.replace("="," ").split(" ")
            #if (sParams[0] == "ERR:"):
                #Domoticz.Error("Error from telnet client: " + sLine)
            #elif len(sParams) >= 4:
                #sReadValue = sParams[3]
                #Domoticz.Log(repr(sParams[3]))
                ## remove invisible characters
                ##sReadValue = re.sub('\W+','', sParams[3])
                ##sReadValue = "".join(char for char in sParams[3] if char in 
                ##sReadValue = re.sub("[^{}]+".format(printable), "", sParams[3])
                #Domoticz.Log(" -- p0 " + sParams[0] + " -- p1 " + sParams[1] + " -- p2 " + sParams[2] + " -- p3 " + sReadValue + " len " + str(len(sReadValue)))
                #Domoticz.Log(" -- len " + str(len(sReadValue)))
                #for indexUnit, dUnit in self.dUnits.items():
                    #if (dUnit["circuit"] == sParams[0]) and (dUnit["name"] == sParams[1]) and (dUnit["fieldname"] == sParams[2]):
                        #Domoticz.Log(" --- match2 " + sLine + " param " + sReadValue + "--")
                        #iValue = 0
                        #sValue = ""
                        #dOptionsMapping = dUnit["options"]
                        #if len(dOptionsMapping) > 0:
                            #if sReadValue in dOptionsMapping:
                                #iValue = dOptionsMapping[sReadValue]
                                #sValue = str(iValue)
                        #else:
                            #if (sReadValue == "on") or (sReadValue == "yes"):
                                #iValue = 1
                            #elif (sReadValue == "off") or (sReadValue == "no"):
                                #iValue = 1
                            #else:
                                #try:
                                    #iValue = int(sReadValue)
                                #except ValueError:
                                    #sValue = sReadValue
                                
                        #Domoticz.Log(" --- update " + str(iValue) + " / " + sValue + "--")
                        #Devices[dUnit["index"]].Update(nValue=iValue, sValue=sValue, Options=dUnit["domoticzoptions"])
                            ##self.dUnits[indexUnit] = { "value":0, "circuit":sPath[0], "name":sPath[1], "field":field["name"], "nfield":nfield }
            #Domoticz.Log(" - "+sLine)
        #self.sConnectionStep = "idle"
        #self.handleFifo()

    #def parseTelnet(self, localStrBuffer):
        #Domoticz.Log("Parse telnet buffer size " + str(len(localStrBuffer)))
        #lLines = localStrBuffer.splitlines()
        #sReadValue = lLines[0]
        #dUnit = self.currentUnit
        #if dUnit != None:
            #sDeviceID = Devices[dUnit["index"]].DeviceID
        #else:
            #sDeviceID = "unknown"
        #if sReadValue[:5] == "ERR: ":
            #Domoticz.Error("Error from telnet client for device " + sDeviceID  + ": " + sReadValue[5:])
        #else:
            #Domoticz.Log(repr(sReadValue))
            ## remove invisible characters
            ##sReadValue = re.sub('\W+','', sParams[3])
            ##sReadValue = "".join(char for char in sParams[3] if char in 
            ##sReadValue = re.sub("[^{}]+".format(printable), "", sParams[3])
            #Domoticz.Log(" -- len " + str(len(sReadValue)))
            #if dUnit != None:
                #if self.sCurrentCommand == "readwhole":
                    #dUnit["fieldsvalues"] = sReadValue
                    #dUnit["fieldsvaluestimestamp"] = time.time()
                #elif self.sCurrentCommand == "read":
                    ##lData = sReadValue.split(";")
                    ##iFieldsCount = dUnit["fieldscount"]
                    ##if len(lData) != iFieldsCount: 
                        ##Domoticz.Error("Field count for device " + sDeviceID + " is not " + str(iFieldsCount) + " as expected")
                    ##else:
                        ##sReadValue = lData[dUnit["fieldindex"]]
                    #iValue = 0
                    #sValue = ""
                    #dOptionsMapping = dUnit["options"]
                    #if len(dOptionsMapping) > 0:
                        #if sReadValue in dOptionsMapping:
                            #iValue = dOptionsMapping[sReadValue]
                            #sValue = str(iValue)
                    #else:
                        #if (sReadValue == "on") or (sReadValue == "yes"):
                            #iValue = 1
                        #elif (sReadValue == "off") or (sReadValue == "no"):
                            #iValue = 1
                        #else:
                            #try:
                                #iValue = int(sReadValue)
                            #except ValueError:
                                #sValue = sReadValue
                        
                    #Domoticz.Log(" --- update " + str(iValue) + " / " + sValue + "--")
                    #Devices[dUnit["index"]].Update(nValue=iValue, sValue=sValue, Options=dUnit["domoticzoptions"])
                    ##self.dUnits[indexUnit] = { "value":0, "circuit":sPath[0], "name":sPath[1], "field":field["name"], "nfield":nfield }
        #self.sConnectionStep = "idle"
        #self.currentUnit = None
        #self.handleFifo()

    # Parse received data from telnet connection in localStrBuffer
    def parseTelnet(self, localStrBuffer):
        self.myDebug("Parse telnet buffer size " + str(len(localStrBuffer)))
        # We are interested only in first line
        lLines = localStrBuffer.splitlines()
        sReadValue = lLines[0]
        # Check if we received an error message
        if sReadValue[:5] == "ERR: ":
            Domoticz.Error("Error from telnet client: " + sReadValue[5:])
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
                sRegister = lParams[1].lower()
                # Look for corresponding circuit and register
                if (sCircuit in self.dUnits3D) and (sRegister in self.dUnits3D[sCircuit]):
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
                    for dUnit in self.dUnits3D[sCircuit][sRegister].values():
                        dUnit["fieldsvalues"] = sFieldsValues
                        dUnit["fieldsvaluestimestamp"] = iFieldsValuesTimestamp
                        self.myDebug("Save whole fields values " + dUnit["fieldsvalues"])						
                        # Distribute read values for each field we are interested into
                        if dUnit["fieldindex"] < len(lFieldsValues):
                            sFieldValue = lFieldsValues[dUnit["fieldindex"]]
                            iValue, sValue = valueEbusdToDomoticz(dUnit, sFieldValue)
                            oDevice = dUnit["device"]
                            if oDevice is not None:
                                if dUnit["forcerefresh"] or dUnit["alwaysrefresh"] or oDevice.TimedOut or (oDevice.nValue != iValue) or (oDevice.sValue != sValue):
                                    oDevice.Update(nValue=iValue, sValue=sValue, TimedOut=0)
                                    dUnit["forcerefresh"] = False
                            else:
                                Domoticz.Error("Received unexpected value " + sReadValue + " for device not anymore in dictionnary")
                        else:
                            Domoticz.Error("Field not found in unit dictionaries for circuit " + dUnit["circuit"] + " register " + dUnit["register"] + " field " + str(dUnit["fieldindex"]) + " for value " + sReadValue)
                else:
                        Domoticz.Error("Received unexpected value " + sReadValue)
                            
        # Data received, going back to "connected" connection step
        self.sConnectionStep = "connected"
        # Handle fifo if there are still command to proceed
        self.handleFifo()

    # parse JSON data received from ebusd
    #   sData: string: data received
    def parseJson(self, sData):
        try:
            dJson = json.loads(sData, object_pairs_hook= lambda dict: CaseInsensitiveDict(dict))
            # dJson = json.loads(sData)
        except Exception as e:
            Domoticz.Error("Impossible to parse JSON (buffer size " + str(len(sData)) + "). " + traceback.format_exc())
            return
        # register are separated with a space
        lUnits = Parameters["Mode2"].lower().split(" ")
        iKey = 0
        timeNow = time.time()
        # if device not found, we will rescan later in case register not yet available on ebus messaging system
        self.bStillToLook = False
        # enumerate with 0 based integer and register name (sDeviceID)
        for sDeviceID in lUnits:
            # continue only if sDeviceID not already in self.dUnitsByDeviceID
            if (len(sDeviceID) > 0) and not (sDeviceID in self.dUnitsByDeviceID):
                # now split device in circuit/message/fieldnumber
                #lPath = sDeviceID.split("-")
                lPath = sDeviceID.split(":")
                # if it seems incorrect
                if ((len(lPath)) < 2) or ((len(lPath)) > 3):
                    Domoticz.Error("Register definition of " + sDeviceID + " is not correct, it must be for instance f47:Hc1DayTemp, f47:Hc1DayTemp:temp1 or f47:Hc1DayTemp:0")
                    self.dUnitsByDeviceID[sDeviceID] = "length error"
                else:
                    sCircuit = lPath[0]
                    sMessage = lPath[1]
                    self.myDebug("Look for circuit " + sCircuit + " register " + sMessage + " in JSON data")
                    if (sCircuit in dJson) :
                        self.myDebug("Circuit " + sCircuit + " found")
                        if ("messages" in dJson[sCircuit]) and (sMessage in dJson[sCircuit]["messages"]) :
                            self.myDebug("Register " + sMessage + " found")
                        
                    # look for circuit/message in JSON
                    if (sCircuit in dJson) and ("messages" in dJson[sCircuit]) and (sMessage in dJson[sCircuit]["messages"]):
                        self.myDebug("Found")
                        # check if writable
                        sWKey = sMessage + "-w"
                        if (not (Parameters["Mode5"] == "True")) and (sWKey in dJson[sCircuit]["messages"]) and ("write" in dJson[sCircuit]["messages"][sWKey]) and dJson[sCircuit]["messages"][sWKey]["write"] :
                            self.myDebug("Writable")
                            dMessage = dJson[sCircuit]["messages"][sWKey]
                            bWritable = True
                        else:
                            dMessage = dJson[sCircuit]["messages"][sMessage]
                            bWritable = False
                        # look at fielddefs
                        # if no fielnumber, default to 0
                        if len(lPath) == 2:
                            sFieldIndex = "0"
                            self.myDebug("Field set to 0 by default")
                        else:
                            sFieldIndex = lPath[2]

                        if (not ("fielddefs" in dMessage)):
                            Domoticz.Error("No field definition for device " + sDeviceID)
                            self.dUnitsByDeviceID[sDeviceID] = "no field definition"
                            continue
                            
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
                                        self.myDebug("Field number of device " + sDeviceID + " is " + str(iFieldIndex))
                                    iFieldsCount += 1
                        if iFieldAbsoluteIndex < 0:
                                Domoticz.Error("Cannot find usable field for device " + sDeviceID)
                                # error on this item, mark device as erroneous and go to next item
                                self.dUnitsByDeviceID[sDeviceID] = "no usable field for device"
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
                        dFieldDefs = dMessage["fielddefs"][iFieldAbsoluteIndex]
                        sFieldType = getFieldType(dFieldDefs["unit"], dFieldDefs["name"], dFieldDefs["type"])

                        #sTypeName = ""
                        iSwitchtype = -1
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
                            iSubtype = 0x49
                            if bWritable:
                                iSwitchtype = 0
                            else:
                                iSwitchtype = 2
                            bHandleTimeout = True
                        # selector switch type
                        elif ("values" in dFieldDefs):
                            if bWritable:
                                #sTypeName = "Selector Switch"
                                iMainType = 0xF4
                                iSubtype = 0x3E
                                iSwitchtype = 18
                            else:
                                #sTypeName = "Text"
                                iMainType = 0xF3
                                iSubtype = 0x13
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
                            iSubtype = 0x1F
                            dOptions = { "Custom": "1;" + str(dFieldDefs["unit"])}
                        # setpoint type
                        elif (sFieldType == "temperature") and bWritable:
                            iMainType = 0xF2
                            iSubtype = 0x01
                        # read-only temperature type
                        elif (sFieldType == "temperature"):
                            #sTypeName = "Temperature"
                            iMainType = 0x50
                            iSubtype = 0x05
                            bAlwaysRefresh = True
                        # pressure type
                        elif (sFieldType == "pressure"):
                            #sTypeName = "Pressure"
                            iMainType = 0xF3
                            iSubtype = 0x09
                            bAlwaysRefresh = True
                        # else text type
                        else:
                            #sTypeName = "Text"
                            iMainType = 0xF3
                            iSubtype = 0x13
                            
                        # check if device is already in domoticz database, based on deviceid
                        bFound = False
                        bForceRefresh = False
                        for iIndexUnit, oDevice in Devices.items():
                            # .lower() for backward compatibility
                            if oDevice.DeviceID.lower() == sDeviceIntegerID:
                                if (oDevice.Type != iMainType) or (oDevice.SubType != iSubtype):
                                    Domoticz.Log("Device " + oDevice.Name + " type changed, updating Domoticz database")
                                    bForceRefresh = True
                                    if iSwitchtype >= 0:
                                        oDevice.Update(nValue=oDevice.nValue, sValue=oDevice.sValue, TimedOut=0, Type=iMainType, Subtype=iSubtype, Switchtype=iSwitchtype, Options=dOptions, Used=1)
                                    else:
                                        oDevice.Update(nValue=oDevice.nValue, sValue=oDevice.sValue, TimedOut=0, Type=iMainType, Subtype=iSubtype, Options=dOptions, Used=1)
                                # log device found, with dFieldDefs["name"] and dFieldDefs["comment"] giving hints on how to use register
                                Domoticz.Log("Device " + oDevice.Name + " unit " + str(iIndexUnit) + " and deviceid " + sDeviceID + " detected: " + dFieldDefs["name"] + " - " + dFieldDefs["comment"])
                                # if found, continue loop to next item
                                bFound = True
                                break

                        # not in database: add device
                        if not bFound:
                            bForceRefresh = True
                            # look for free index in Devices
                            for iIndexUnit in range(1, 257):
                                if not iIndexUnit in Devices:
                                    break
                            # domoticz database doesn't handle more than 256 devices per plugin !
                            if iIndexUnit <= 256:
                                # Create name
                                sCompleteName = sCircuit + " - " + sMessage
                                if dFieldDefs["name"] != "":
                                    sCompleteName += " - " + dFieldDefs["name"]
                                else:
                                    sCompleteName += " - " + sFieldIndex
                                # create device, log dFieldDefs["name"] and dFieldDefs["comment"] giving hints on how to use register
                                if iSwitchtype >= 0:
                                    Domoticz.Device(Name=sCompleteName, Unit=iIndexUnit, Type=iMainType, Subtype=iSubtype, Switchtype=iSwitchtype, Description=dFieldDefs["comment"], Options=dOptions, Used=1, DeviceID=sDeviceIntegerID).Create()
                                    if iIndexUnit in Devices:
                                        Domoticz.Log("Add device " + sDeviceID + " (" + sDeviceIntegerID + ") unit " + str(iIndexUnit) + " as type " + str(iMainType) + ", subtype " + str(iSubtype) + " and switchtype " + str(iSwitchtype) + ": " + dFieldDefs["name"] + " - " + dFieldDefs["comment"])
                                    else:
                                        Domoticz.Error("Cannot add device " + sDeviceID + " (" + sDeviceIntegerID + ") unit " + str(iIndexUnit) + ". Check in settings that Domoticz is set up to accept new devices")
                                        self.bStillToLook = True
                                        break
                                else:
                                    Domoticz.Device(Name=sCompleteName, Unit=iIndexUnit, Type=iMainType, Subtype=iSubtype, Description=dFieldDefs["name"] + " - " + dFieldDefs["comment"], Options=dOptions, Used=1, DeviceID=sDeviceIntegerID).Create()
                                    if iIndexUnit in Devices:
                                        Domoticz.Log("Add device " + sDeviceID + " (" + sDeviceIntegerID + ") unit " + str(iIndexUnit) + " as type " + str(iMainType) + " and subtype " + str(iSubtype) + ": " + dFieldDefs["name"] + " - " + dFieldDefs["comment"])
                                    else:
                                        Domoticz.Error("Cannot add device " + sDeviceID + " (" + sDeviceIntegerID + ") unit " + str(iIndexUnit) + ". Check in settings that Domoticz is set up to accept new devices")
                                        self.bStillToLook = True
                                        break
                            else:
                                Domoticz.Error("Too many devices, " + sDeviceID + " cannot be added")
                                self.dUnitsByDeviceID[sDeviceID] = "too many devices"
                                break
                        
                        # incorporate found or created device to local self.dUnits dictionnaries, to keep additionnal parameters used by the plugin
                        self.dUnitsByDeviceID[sDeviceID] = { "device":Devices[iIndexUnit], "circuit":sCircuit, "register":sMessage, "fieldindex":iFieldIndex, "fieldscount":iFieldsCount, "options":dOptionsMapping, "reverseoptions":dReverseOptionsMapping, "domoticzoptions": dOptions, "fieldtype": sFieldType, "forcerefresh": bForceRefresh, "alwaysrefresh": bAlwaysRefresh }
                        # set fieldsvaluestimestamp for read then write timeout
                        self.dUnitsByDeviceID[sDeviceID]["fieldsvaluestimestamp"] = timeNow - (2 * self.timeoutConstant)
                        self.dUnitsByUnitNumber[iIndexUnit] = self.dUnitsByDeviceID[sDeviceID]
                        if not sCircuit in self.dUnits3D:
                            self.dUnits3D[sCircuit] = {}
                        if not sMessage in self.dUnits3D[sCircuit]:
                            self.dUnits3D[sCircuit][sMessage] = {}
                        self.dUnits3D[sCircuit][sMessage][iFieldIndex] = self.dUnitsByDeviceID[sDeviceID]
                        # place a read command in the queue for each device to refresh its value asap
                        self.read(self.dUnitsByDeviceID[sDeviceID])
                    else:
                        # we will rescan later in case register not yet available on ebus messaging system
                        Domoticz.Log("Device " + sDeviceID + " not found, will try again later")
                        self.bStillToLook = True

    def onStart(self):
        Domoticz.Debug("onStart called")
        # Ignore username and password, I'm not sure when I should authenticate and it can be handled by ACL file directly by ebusd
        #Domoticz.Log("Username set to " + Parameters["Username"])
        Domoticz.Log("This plugin is compatible with Domoticz version 3.9085 onwards")
        Domoticz.Log("IP or named address set to " + Parameters["Address"])
        Domoticz.Log("Telnet port set to " + Parameters["Port"])
        Domoticz.Log("JSON  HTTP port set to " + Parameters["Mode1"])
        Domoticz.Log("Registers set to " + Parameters["Mode2"])
        Domoticz.Log("Refresh rate set to " + Parameters["Mode3"])
        Domoticz.Log("Disable cache set to " + Parameters["Mode4"])
        Domoticz.Log("Read-only set to " + Parameters["Mode5"])
        Domoticz.Log("Debug set to " + Parameters["Mode6"])
        try:
            self.iDebugLevel = int(Parameters["Mode6"])
        except ValueError:
            self.iDebugLevel = 0
            
        # most init
        self.__init__()
        # set refresh rate to its default value if not an integer
        try:
            self.iRefreshRate = int(Parameters["Mode3"])
        except ValueError:
            #Handle the exception
            Domoticz.Error("Refresh rate parameter incorrect, set to its default value")
            self.iRefreshRate = 600
        # enable debug if required
        if self.iDebugLevel > 1:
            Domoticz.Debugging(1)            
        # set heartbeat interval	
        if self.iRefreshRate < self.maxHeartbeatInterval:
                Domoticz.Heartbeat(self.iRefreshRate)
        else:
                Domoticz.Heartbeat(self.maxHeartbeatInterval)
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

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Debug("onCommand called for unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level) + ", Hue: " + str(Hue))
        # if started and not stopping
        if self.bIsStarted:
            # add write to the queue
            self.write(Unit, Command, Level, "")

    def onDeviceModified(self, Unit):
        Domoticz.Debug("onDeviceModified called for unit " + str(Unit))
        # if started and not stopping
        if self.bIsStarted:
            # add write to the queue
            self.write(Unit, "udevice", Devices[Unit].nValue, Devices[Unit].sValue)

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Debug("onNotification called: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(Priority) + "," + Sound + "," + ImageFile)

    def onDisconnect(self, Connection):
        Domoticz.Debug("onDisconnect called")

    # Add a read command to the queue
    #   dUnit: dict
    def read(self, dUnit):
        if type(dUnit) is dict:
            self.myDebug("read called for circuit " + dUnit["circuit"] + " register " + dUnit["register"] + " field " + str(dUnit["fieldindex"]))
            self.dqFifo.append({"operation":"read", "unit":dUnit})
            self.handleFifo()
        else:
            Domoticz.Error("Cannot read device that is in error state: " + dUnit)
    
    # Will write a value to ebusd
    #   iUnitNumber: integer: unit index in Devices dict
    #   ifLevel: integer or float: value to write
    def write(self, iUnitNumber, sCommand, ifValue, sValue):
        Domoticz.Debug("write called for unit " + str(iUnitNumber) + " command " + sCommand + " value " + str(ifValue) + " / " + sValue)
        if Parameters["Mode5"] == "True":
            Domoticz.Debug("Cannot write device " + str(iUnitNumber) + " because the read-only parameter is set")
            return
        elif iUnitNumber in self.dUnitsByUnitNumber:
            dUnit = self.dUnitsByUnitNumber[iUnitNumber]
            # convert domoticz command and level to ebusd string value
            sValue = valueDomoticzToEbusd(dUnit, sCommand, ifValue, sValue, Devices[iUnitNumber].nValue, Devices[iUnitNumber].sValue)
                    
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
            Domoticz.Error("Cannot write device " + str(iUnitNumber) + " that doesn't exist")

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
                self.myDebug("handleFifo() create connection to " + Parameters["Address"] + ":" + Parameters["Port"])
                self.telnetConn = Domoticz.Connection(Name="Telnet", Transport="TCP/IP", Protocol="", Address=Parameters["Address"], Port=Parameters["Port"])
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
                        #self.telnetConn.Send("read -c " + dUnit["circuit"] + " " + dUnit["register"] + "\r\n")
                        #self.telnetConn.Send("read -c " + dUnit["circuit"] + " " + dUnit["register"] + " " + dUnit["fieldname"] + "." + str(dUnit["fieldindex"]) + "\r\n")
                        # telnet read command in verbose mode
                        sRead = "read "
                        # if no cache
                        if Parameters["Mode4"] == "True" :
                            sRead = sRead + "-f "
                        sRead = sRead + " -v -c " + dUnit["circuit"] + " " + dUnit["register"] + "\r\n"
                        self.myDebug("Telnet write: " + sRead)
                        self.telnetConn.Send(sRead)
                    # write command
                    elif self.sCurrentCommand == "write" and (not (Parameters["Mode5"] == "True")):
                        iFieldsCount = dUnit["fieldscount"]
                        # we have more than one field, retrieve all fields value (from last read) if not too old, modify the field and write
                        if iFieldsCount > 1:
                            if ((dUnit["fieldsvaluestimestamp"] + self.timeoutConstant) >= timeNow):
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
                                    sWrite = "write -c " + dUnit["circuit"] + " " + dUnit["register"] + " " + sData + "\r\n"
                                    self.myDebug("Telnet write: " + sWrite)
                                    self.telnetConn.Send(sWrite)
                            else:
                                Domoticz.Error("Data cached is too old or inexistent, won't take the risk to modify many fields at once")
                        else:
                            # telnet write command if only one field in message
                            sWrite = "write -c " + dUnit["circuit"] + " " + dUnit["register"] + " " + sCommand["value"] + "\r\n"
                            self.myDebug("Telnet write: " + sWrite)
                            self.telnetConn.Send(sWrite)
                    # Ignore username and password, I'm not sure when I should authenticate and it can be handled by ACL file directly by ebusd
                    #elif self.sCurrentCommand == "authenticate":
                            #sWrite = "auth " + Parameters["Username"] + " " + Parameters["Password"] + "\r\n"
                            #self.myDebug("Telnet write:" + sWrite)
                else:
                    Domoticz.Error("Received command for unit in error state: " + dUnit)
        # the plugin seems blocked in connecting or data sending step, restart the plugin
        elif (len(self.dqFifo) > 0) and (timeNow >= (self.iConnectionTimestamp + self.timeoutConstant)) :
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
                if (timeNow >= (self.iRefreshTime + self.iRefreshRate)) :
                    # we still not have detected all registers given in configuration, retry JSON search
                    if self.bStillToLook:
                        self.findDevices()
                    # refresh values of already detected registers
                    for sMessage in self.dUnits3D:
                        for sRegister in self.dUnits3D[sMessage]:
                            # only refresh first found field, read operation will read all declared fields anyway
                            dUnit = next(iter(self.dUnits3D[sMessage][sRegister].values()), None)
                            if dUnit:
                                self.read(dUnit)
                    # check for timeouts
                    for iIndexUnit, oDevice in Devices.items():
                        if not oDevice.TimedOut:
                            bTimedOut = False                    
                            if iIndexUnit in self.dUnitsByUnitNumber:
                                dUnit = self.dUnitsByUnitNumber[iIndexUnit]
                                if (dUnit["fieldsvaluestimestamp"] + (3 * self.iRefreshRate)) < timeNow:
                                    bTimedOut = True
                            else:
                                bTimedOut = True
                            if bTimedOut:
                                Domoticz.Error("Device " + oDevice.Name + " ID " + str(oDevice.ID) + " DeviceID " + oDevice.DeviceID + " timed out")
                                oDevice.Update(nValue=oDevice.nValue, sValue=oDevice.sValue, TimedOut=1)
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

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)

def onDeviceAdded(Unit):
    global _plugin

def onDeviceModified(Unit):
    global _plugin
    _plugin.onDeviceModified(Unit)

def onDeviceRemoved(Unit):
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
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device iValue:    " + str(Devices[x].iValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
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
        Domoticz.Debug("Integer value too big, converted to 0, for circuit " + dUnit["circuit"] + " register " + dUnit["register"] + " field " + str(dUnit["fieldindex"]))
        iValue = 0
   
    return iValue, sValue
