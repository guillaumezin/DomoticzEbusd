#           ebusd Plugin
#
#           Author:     Barberousse, z1mEk, 2017-2018
#           MIT license
#
"""
<plugin key="ebusd" name="ebusd bridge" author="Barberousse" version="1.1.2" externallink="https://github.com/guillaumezin/DomoticzEbusd">
    <params>
        <!-- <param field="Username" label="Username (left empty if authentication not needed)" width="200px" required="false" default=""/>
        <param field="Password" label="Password" width="200px" required="false" default=""/> -->
        <param field="Address" label="IP or named address" width="200px" required="true" default="127.0.0.1"/>
        <param field="Port" label="Telnet port" width="75px" required="true" default="8888"/>
        <param field="Mode1" label="JSON HTTP port" width="75px" required="true" default="8889"/>
        <param field="Mode2" label="Registers" width="1000px" required="true" default=""/>
        <param field="Mode3" label="Refresh rate (seconds)" width="75px" required="false" default="600"/>
        <param field="Mode4" label="Disable cache" width="75px">
            <options>
                <option label="True" value="True"/>
                <option label="False" value="False"  default="true" />
            </options>
        </param>
        <param field="Mode5" label="Read-only" width="75px">
            <options>
                <option label="True" value="True"/>
                <option label="False" value="False"  default="true" />
            </options>
        </param>
        <param field="Mode6" label="Debug" width="75px">
            <options>
                <option label="True" value="Debug"/>
                <option label="False" value="Normal"  default="true" />
            </options>
        </param>
    </params>
</plugin>
"""

# TODO : gérer la casse = tout passer en minuscule : from requests import CaseInsensitiveDict
# TODO : gérer écriture des autres types de champs

# https://www.domoticz.com/wiki/Developing_a_Python_plugin

import Domoticz
import json
import time
from collections import deque

class BasePlugin:
    # boolean to check that we are started, to prevent error messages when disabling or restarting the plugin
    isStarted = None
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
    #   "index": integer: Devices index of unit
    #   "circuit": string: circuit name, for instance "f47"
    #   "name": string: register, for instance "OutsideTemp"
    #   "fieldindex": integer: field index (0 based)
    #   "fieldscount": integer: total number of fields
    #   "options": dictionnary: keyed by ebusd value, contains selector switch level integer value, empty if not selector switch
    #   "reverseoptions": dictionnary: keyed by selector switch level integer valu, contains selector switch ebusd string value, empty if not selector switch
    #   "domoticzoptions": dictionnary: options send during domoticz device type selector switch creation and update
    #   "fieldsvalues": string: fields values read after "readwhole" operation
    #   "fieldsvaluestimestamp": integer: time when fields values have been updated
    dUnits = None
    # dequeue of dictionnaries
    #   "operation": string: can be "read", "readwhole", "write", "authenticate"
    #   "deviceid":string, deviceid string (circuit:register:fieldindex, for instance "f47:OutsideTemp:0"), used only for "read", "readwhole" and "write" operation
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

    def __init__(self):
        self.isStarted = False
        self.telnetConn = None
        self.jsonConn = None
        self.dUnits = {}
        self.sBuffer = ""
        self.bStillToLook = True
        self.iRefreshTime = 0
        self.iRefreshRate = 1000
        self.dqFifo = deque()
        self.sConnectionStep = "idle"
        self.iConnectionTimestamp = 0
        self.sCurrentCommand = ""
        return
    
    # Connect to JSON HTTP port to get list of ebusd devices
    def findDevices(self):
        if self.jsonConn == None:
            Domoticz.Debug("findDevices create connection to " + Parameters["Address"] + ":" + Parameters["Mode1"])
            self.jsonConn = Domoticz.Connection(Name="JSON HTTP", Transport="TCP/IP", Protocol="HTTP", Address=Parameters["Address"], Port=Parameters["Mode1"])
            
        if not self.jsonConn.Connected():
            Domoticz.Debug("Connect")
            self.jsonConn.Connect()
        else:
            Domoticz.Debug("Find")
            # we connect with def and write to get complete list of fields and writable registers
            sendData = { 'Verb' : 'GET',
                        'URL'  : '/data?def&write',
                        'Headers' : { 'Content-Type': 'text/xml; charset=utf-8', \
                                        'Connection': 'keep-alive', \
                                        'Accept': 'Content-Type: text/html; charset=UTF-8', \
                                        'Host': Parameters["Address"]+":"+Parameters["Mode1"], \
                                        'User-Agent':'Domoticz/1.0' }
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
        Domoticz.Debug("Parse telnet buffer size " + str(len(localStrBuffer)))
        # We are interested only in first line
        lLines = localStrBuffer.splitlines()
        sReadValue = lLines[0]
        # Check if we received an error message
        if sReadValue[:5] == "ERR: ":
            Domoticz.Error("Error from telnet client: " + sReadValue[5:])
        else:
            Domoticz.Debug("Reveived value: " + repr(sReadValue))
            # We sould receive something like "f47 OutsideTemp temp=9.56;sensor=ok"
            # Split by space
            sParams = sReadValue.split(" ", 2)
            if len(sParams) >= 3:
                # Search in configured units a corresponding one
                for dUnit in self.dUnits.values():
                    if (type(dUnit) is dict) and (dUnit["circuit"] == sParams[0]) and (dUnit["name"] == sParams[1]):
                        Domoticz.Debug("Match circuit " + dUnit["circuit"] + " register " + dUnit["name"] + " for value " + sReadValue)
                        # Split received fields by ;
                        sFields = sParams[2].split(";")
                        lFieldsValues = []
                        # Sanity check
                        if len(sFields) == dUnit["fieldscount"]:
                            # If command is "readwhole", collect all fields contents and save them inside dUnit["fieldsvalues"]
                            if self.sCurrentCommand == "readwhole":
                                for sField in sFields:
                                    # Keep only the right of =
                                    sFieldContent = sField.split("=")
                                    # Sanity check
                                    if len(sFieldContent) == 2:
                                        lFieldsValues.append(sFieldContent[1])
                                    else:
                                        Domoticz.Error("Parsing error on field for value " + sReadValue)
                                dUnit["fieldsvalues"] = ";".join(lFieldsValues)
                                dUnit["fieldsvaluestimestamp"] = time.time()
                                Domoticz.Debug("Save whole fields values " + dUnit["fieldsvalues"])
                            else:
                                # Command wasn't "readwhole", extract correct field
                                sFieldContent = sFields[dUnit["fieldindex"]].split("=")
                                # Sanity check
                                if len(sFieldContent) == 2:
                                    sFieldValue = sFieldContent[1]
                                    # Convert value from ebusd to domoticz ones
                                    iValue, sValue = valueEbusdToDomoticz(dUnit, sFieldValue)
                                    Domoticz.Debug("Update domoticz with iValue " + str(iValue) + " and sValue " + sValue + " field number " + str(dUnit["fieldindex"]))
                                    Devices[dUnit["index"]].Update(nValue=iValue, sValue=sValue, Options=dUnit["domoticzoptions"])
                                else:
                                    Domoticz.Error("parsing error on field for value " + sReadValue)
                        else:
                            Domoticz.Error("parsing error on field count for value " + sReadValue + " (" + str(dUnit["fieldscount"]) + " fields expected)")
                        # break for loop because device found
                        break
                            
        # Data received, going back to "connected" connection step
        self.sConnectionStep = "connected"
        # Handle fifo if there are still command to proceed
        self.handleFifo()

    # parse JSON data received from ebusd
    #   sData: string: data received
    def parseJson(self, sData):
        oJson = json.loads(sData)
        # register are separated with a space
        lUnits = Parameters["Mode2"].split(" ")
        iKey = 0
        # enumerate with 0 based integer and register name (sDeviceID)
        for sDeviceID in lUnits:
            # continue only if sDeviceID not already in self.dUnits
            if (len(sDeviceID) > 0) and not (sDeviceID in self.dUnits):
                # now split device in circuit/message/fieldnumber
                #sPath = sDeviceID.split("-")
                sPath = sDeviceID.split(":")
                # if it seems incorrect
                if ((len(sPath)) < 2) or ((len(sPath)) > 3):
                    Domoticz.Error("register definition of " + sDeviceID + " is not correct, it must be for instance f47:Hc1DayTemp or f47:Hc1DayTemp:0")
                    self.dUnits[sDeviceID] = "length error"
                else:
                    sCircuit = sPath[0]
                    sMessage = sPath[1]
                    Domoticz.Debug("Look for circuit " + sCircuit + " register " + sMessage + " in JSON data")
                    # if no fielnumber, default to 0
                    if len(sPath) == 2:
                        iFieldIndex = 0
                        sFieldIndex = "0"
                        sDeviceID += ":0"
                    else:
                        # try to get fieldnumber, if not an integer, throw an error and continue for loop
                        try:
                            sFieldIndex = sPath[2]
                            iFieldIndex = int(sFieldIndex)
                        except ValueError:
                            Domoticz.Error("Field number of device " + sDeviceID + " is not set correctly")
                            self.dUnits[sDeviceID] = "field number error"
                            continue
                    # look for circuit/message in JSON, if not found, we will rescan later in case register not yet available on ebus messaging system
                    Domoticz.Debug("Look for field number " + sFieldIndex + " in JSON data")
                    self.bStillToLook = False
                    if (sCircuit in oJson) and ("messages" in oJson[sCircuit]) and (sMessage in oJson[sCircuit]["messages"]):
                        Domoticz.Debug("Found")
                        # check if writable
                        sWKey = sMessage + "-w"
                        if (not (Parameters["Mode5"] == "True")) and (sWKey in oJson[sCircuit]["messages"]) and ("write" in oJson[sCircuit]["messages"][sWKey]) and oJson[sCircuit]["messages"][sWKey]["write"] :
                            Domoticz.Debug("Writable")
                            dMessage = oJson[sCircuit]["messages"][sWKey]
                            bWritable = True
                        else:
                            dMessage = oJson[sCircuit]["messages"][sMessage]
                            bWritable = False
                        # look at fielddefs
                        if ("fielddefs" in dMessage) and (iFieldIndex >= 0) and (iFieldIndex < len(dMessage["fielddefs"])):
                            iFieldsCount = len(dMessage["fielddefs"])
                            #flen = len(dMessage["fielddefs"])
                            #if bWritable and (flen > 1):
                                #Domoticz.Error("Register " + sCircuit + "-" + sMessage + " has " + str(flen) + " fields and is writable, more than one field and writable isn't supported yet, the register will be read only")
                                #bWritable = False
                            dFields = dMessage['fielddefs'][iFieldIndex]
                            sTypeName = ""
                            dValues = None
                            dOptions = {}
                            dOptionsMapping = {}
                            dReverseOptionsMapping = {}
                            # now we try to get the best match between domoticz sensor and ebusd field type
                            # https://github.com/domoticz/domoticz/blob/master/hardware/hardwaretypes.h ligne 42
                            # https://github.com/domoticz/domoticz/blob/master/hardware/plugins/PythonObjects.cpp ligne 410
                            sFieldType = getFieldType(dFields["unit"], dFields["name"], dFields["type"])
                            Domoticz.Debug("Field is type " + sFieldType)
                            # on/off type
                            if (sFieldType == "switch") and bWritable:
                                sTypeName = "Switch"
                            # selector switch type
                            if ("values" in dFields) and bWritable:
                                dValues = dFields["values"]
                                sTypeName = "Selector Switch"
                                sLevelActions = "|"
                                sLevelNames = "|"
                                for iIndexValue, sValue in enumerate(sorted(dValues.values())):
                                    if iIndexValue > 0:
                                        sLevelActions += "|"
                                        sLevelNames += "|"
                                    sLevelNames += str(sValue)
                                    iIndexValue += 1
                                    iIndexValue *= 10
                                    dOptionsMapping[sValue] = iIndexValue
                                    dReverseOptionsMapping[iIndexValue] = sValue
                                Domoticz.Debug("LevelNames for Domoticz are " + sLevelNames)
                                dOptions = {"LevelActions": sLevelActions, "LevelNames": sLevelNames, "LevelOffHidden": "true", "SelectorStyle": "1"}
                            # number type, probably to improve
                            elif (sFieldType == "number") or (sFieldType == "custom"):
                                sTypeName = "Custom"
                                dOptions = { "Custom": "1;" + str(dFields["unit"])}
                            # setpoint type
                            elif (sFieldType == "temperature") and bWritable:
                                iMainType = 0xF2
                                iSubtype = 0x01
                            # read-only temperature type
                            elif (sFieldType == "temperature"):
                                sTypeName = "Temperature"
                            # pressure type
                            elif (sFieldType == "pressure"):
                                sTypeName = "Pressure"
                            # else text type
                            else:
                                sTypeName = "Text"
                                
                            # check if device is already in domoticz database, based on deviceid
                            bFound = False
                            for iIndexUnit, currentDevice in Devices.items():
                                if currentDevice.DeviceID == sDeviceID:
                                    # log device found, with dFields['comment'] giving hints on how to use register
                                    Domoticz.Log("Device " + currentDevice.Name + " unit " + str(iIndexUnit) + " and deviceid " + sDeviceID + " detected: " + dFields['comment'])
                                    # if found, break for loop
                                    bFound = True
                                    break

                            # not in database: add device
                            if not bFound:
                                # look for free index in Devices
                                for iIndexUnit in range(1, 257):
                                    if not iIndexUnit in Devices:
                                        break
                                # domoticz database doesn't handle more than 256 devices per plugin !
                                if iIndexUnit <= 256:
                                    # Create device based on sTypeName or iMainType
                                    if sTypeName != "":
                                        # create device, log dFields['comment'] giving hints on how to use register
                                        Domoticz.Log("Add device " + sDeviceID + " unit " + str(iIndexUnit) + " as type " + sTypeName + ": " + dFields['comment'])
                                        Domoticz.Device(Name=sMessage,  Unit=iIndexUnit, TypeName=sTypeName, Options=dOptions, Used=1, DeviceID=sDeviceID).Create()
                                    else:
                                        # create device, log dFields['comment'] giving hints on how to use register
                                        Domoticz.Log("Add device " + sDeviceID + " unit " + str(iIndexUnit) + " as type " + str(iMainType) + " and subtype " + str(iSubtype) + ": " + dFields['comment'])
                                        Domoticz.Device(Name=sMessage,  Unit=iIndexUnit, Type=iMainType, Subtype=iSubtype, Options=dOptions, Used=1, DeviceID=sDeviceID).Create()
                                else:
                                    Domoticz.Error("Too many devices, " + sDeviceID + " cannot be added")
                                    self.dUnits[sDeviceID] = "too many devices"
                                    break
                            
                            # incorporate found or created device to local self.dUnits dictionnary, to keep additionnal parameters used by the plugin
                            self.dUnits[sDeviceID] = { "index":iIndexUnit, "circuit":sCircuit, "name":sMessage, "fieldindex":iFieldIndex, "fieldscount":iFieldsCount, "options":dOptionsMapping, "reverseoptions":dReverseOptionsMapping, "domoticzoptions": dOptions }
                            # place a read command in the queue for each device to refresh its value asap
                            self.read(iIndexUnit)
                        else:
                            Domoticz.Error("device " + sDeviceID + " has no field " + sFieldIndex)
                            self.dUnits[sDeviceID] = "incorrect field"
                    else:
                        # we will rescan later in case register not yet available on ebus messaging system
                        Domoticz.Log("Device " + sDeviceID + " not found, will try again later")
                        self.bStillToLook = True

    def onStart(self):
        Domoticz.Log("onStart called")
        # Ignore username and password, I'm not sure when I should authenticate and it can be handled by ACL file directly by ebusd
        #Domoticz.Log("Username set to " + Parameters["Username"])
        Domoticz.Log("IP or named address set to " + Parameters["Address"])
        Domoticz.Log("Telnet port set to " + Parameters["Port"])
        Domoticz.Log("JSON  HTTP port set to " + Parameters["Mode1"])
        Domoticz.Log("Registers set to " + Parameters["Mode2"])
        Domoticz.Log("Refresh rate set to " + Parameters["Mode3"])
        Domoticz.Log("Disable cache set to " + Parameters["Mode4"])
        Domoticz.Log("Read-only set to " + Parameters["Mode5"])
        Domoticz.Log("Debug set to " + Parameters["Mode6"])
        # most init
        self.__init__()
        # set refresh rate to its default value if not an integer
        try:
            self.iRefreshRate = int(Parameters["Mode3"])
        except ValueError:
            #Handle the exception
            Domoticz.Error("refresh rate parameter incorrect, set to its default value")
            self.iRefreshRate = 600
        # enable debug if required
        if Parameters["Mode6"] == "Debug":
            Domoticz.Debugging(1)
        # now we can enabling the plugin
        self.isStarted = True
        # Ignore username and password, I'm not sure when I should authenticate and it can be handled by ACL file directly by ebusd
        #if Parameters["Username"] != "":
            #self.dqFifo.append({"operation":"authenticate"})
        # first scan of available registers
        self.findDevices()

    def onStop(self):
        Domoticz.Debug("onStop called")
        # prevent error messages during disabling plugin
        self.isStarted = False
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
        if self.isStarted:
            if ((Connection == self.jsonConn) and (Status == 0)):
                Domoticz.Debug("onConnect for json called")
                self.findDevices()
            elif ((Connection == self.telnetConn) and (Status == 0)):
                Domoticz.Debug("onConnect for telnet called")
                self.sConnectionStep = "connected"
                self.handleFifo()

    def onMessage(self, Connection, Data):
        Domoticz.Debug("onMessage called")

        # if started and not stopping
        if self.isStarted:
            # message for finddevices: JSON HTTP response, buffer completion is handled by domoticz HTTP protocol
            if (Connection == self.jsonConn):       
                sData = Data["Data"].decode("utf-8", "ignore")
                Status = int(Data["Status"])

                if (Status == 200):
                    Domoticz.Debug("Good Response received from ebusd : length " + str(len(sData)))
                    #self.jsonConn.Disconnect()
                    # now parse
                    self.parseJson(sData)

                else:
                    Domoticz.Error("ebusd JSON HTTP interface returned a status: " + str(Status))
            # telnet answer, buffer may be incomplete, we wait for \n\n to be sure to get complete response, buffer completion is not handled by domoticz line protocol
            else:
                sData = Data.decode("utf-8", "ignore")
                # Domoticz.Debug("Received data size " + str(len(sData)) + ": '"+sData+"'")
                # we limit buffer size to keep memory, telnet answer shouldn't be big, as used by the plugin
                if len(self.sBuffer) > 100000:
                    self.sBuffer = ""
                self.sBuffer += sData
                # \n\n is the end of telnet response send by ebusd
                if sData.endswith("\n\n"):
                    # Domoticz.Debug("Received buffer size " + str(len(self.sBuffer)) + ": '"+self.sBuffer+"'")
                    # now parse
                    self.parseTelnet(self.sBuffer)
                    # empty buffer
                    self.sBuffer = ""

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Debug("onCommand called for unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level) + ", Hue: " + str(Hue))
        # if started and not stopping
        if Command != "udevice":
            if self.isStarted:
                # add write to the queue
                self.write(Unit, Command, Level, '')

    def onUpdate(self, Unit, Command, Details):
        if (Details is not None) and ('sValue' in Details):
            sValue = Details['sValue']
        else:
            sValue = ''
        if (Details is not None) and ('iValue' in Details):
            iValue = Details['iValue']

        Domoticz.Debug("onUpdate called for unit " + str(Unit) + ": Parameter '" + str(Command) + "', iValue: " + str(iValue) + ", sValue: " + str(sValue))
        if Command == "udevice":
            # if started and not stopping
            if self.isStarted:
                # add write to the queue
                self.write(Unit, Command, iValue, sValue)

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Debug("onNotification called: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(Priority) + "," + Sound + "," + ImageFile)

    def onDisconnect(self, Connection):
        Domoticz.Debug("onDisconnect called")

    # Add a read command to the queue
    #   iUnitNumber: integer: unit index in Devices dict
    def read(self, iUnitNumber):
        Domoticz.Debug("read called for unit " + str(iUnitNumber))
        if iUnitNumber in Devices:
            self.dqFifo.append({"operation":"read", "deviceid":Devices[iUnitNumber].DeviceID})
            self.handleFifo()
        else:
            Domoticz.Error("Cannot read device " + str(iUnitNumber) + " that doesn't exist")
    
    # Will write a value to ebusd
    #   iUnitNumber: integer: unit index in Devices dict
    #   ifLevel: integer or float: value to write
    def write(self, iUnitNumber, sCommand, ifValue, sValue):
        Domoticz.Debug("write called for unit " + str(iUnitNumber) + " command " + sCommand + " value " + str(ifValue) + " / " + sValue)
        if (iUnitNumber in Devices) and (Devices[iUnitNumber].DeviceID in self.dUnits):
            dUnit = self.dUnits[Devices[iUnitNumber].DeviceID]
            
            # convert domoticz command and level to ebusd string value
            sValue = valueDomoticzToEbusd(dUnit, sCommand, ifValue, sValue, Devices[iUnitNumber].nValue, Devices[iUnitNumber].sValue)
                
            # if there are more than one field, we must read all fields, modify the required field and write back all fields at once
            iFieldsCount = dUnit["fieldscount"]
            if iFieldsCount <= 1:
                Domoticz.Debug("Will write " + sValue)
                self.dqFifo.append({"operation":"write", "deviceid":Devices[iUnitNumber].DeviceID, "value":sValue})
                # write then read to update Domoticz interface
                self.dqFifo.append({"operation":"read", "deviceid":Devices[iUnitNumber].DeviceID})
                # launch commands in the queue
                self.handleFifo()
            else:
                Domoticz.Debug("Will write (more than one field) " + sValue)
                # read all fields first before write one field when more than one field in the message
                self.dqFifo.append({"operation":"readwhole", "deviceid":Devices[iUnitNumber].DeviceID})
                self.dqFifo.append({"operation":"write", "deviceid":Devices[iUnitNumber].DeviceID, "value":sValue})
                # write then read to update Domoticz interface
                self.dqFifo.append({"operation":"read", "deviceid":Devices[iUnitNumber].DeviceID})
                # launch commands in the queue
                self.handleFifo()
        else:
            Domoticz.Error("Cannot write device " + str(iUnitNumber) + " that doesn't exist")
        
    # Handle the connection to Telnet port and the command queue
    def handleFifo(self):
        Domoticz.Debug("handleFifo called")
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
                Domoticz.Debug("handleFifo create connection to " + Parameters["Address"] + ":" + Parameters["Port"])
                self.telnetConn = Domoticz.Connection(Name="Telnet", Transport="TCP/IP", Protocol="line", Address=Parameters["Address"], Port=Parameters["Port"])
            if not self.telnetConn.Connected():
                Domoticz.Debug("Connect")
                self.sConnectionStep = "connecting"
                self.telnetConn.Connect()
            # or process queue
            else:
                Domoticz.Debug("Handle")
                # pop command from queue (first in first out)
                sCommand = self.dqFifo.popleft()
                # get corresponding unit by deviceid
                sDeviceID = sCommand["deviceid"]
                if sDeviceID in self.dUnits:
                    self.sConnectionStep = "data sending"
                    dUnit = self.dUnits[sDeviceID]
                    self.sCurrentCommand = sCommand["operation"]
                    # read command
                    if (self.sCurrentCommand == "readwhole") or (self.sCurrentCommand == "read"):
                        #self.telnetConn.Send("read -c " + dUnit["circuit"] + " " + dUnit["name"] + "\r\n")
                        #self.telnetConn.Send("read -c " + dUnit["circuit"] + " " + dUnit["name"] + " " + dUnit["fieldname"] + "." + str(dUnit["fieldindex"]) + "\r\n")
                        # telnet read command in verbose mode
                        sRead = "read "
                        # if no cache
                        if Parameters["Mode4"] == "True" :
                            sRead = sRead + "-f "
                        sRead = sRead + " -v -c " + dUnit["circuit"] + " " + dUnit["name"] + "\r\n"
                        Domoticz.Debug("Telnet write: " + sRead)
                        self.telnetConn.Send(sRead)
                    # write command
                    elif self.sCurrentCommand == "write":
                        iFieldsCount = dUnit["fieldscount"]
                        # we have more than one field, retrieve all fields value (from last readwhole) if not too old, modify the field and write
                        if iFieldsCount > 1:
                            if ("fieldsvaluestimestamp" in dUnit) and ((dUnit["fieldsvaluestimestamp"] + self.timeoutConstant) > time.time()):
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
                                    sWrite = "write -c " + dUnit["circuit"] + " " + dUnit["name"] + " " + sData + "\r\n"
                                    Domoticz.Debug("Telnet write: " + sWrite)
                                    self.telnetConn.Send(sWrite)
                            else:
                                Domoticz.Error("Data cached is too old or inexistent, won't take the risk to modify many fields at once")
                        else:
                            # telnet write command if only one field in message
                            sWrite = "write -c " + dUnit["circuit"] + " " + dUnit["name"] + " " + sCommand["value"] + "\r\n"
                            Domoticz.Debug("Telnet write: " + sWrite)
                            self.telnetConn.Send(sWrite)
                    # Ignore username and password, I'm not sure when I should authenticate and it can be handled by ACL file directly by ebusd
                    #elif self.sCurrentCommand == "authenticate":
                        #sWrite = "auth " + Parameters["Username"] + " " + Parameters["Password"] + "\r\n"
                        #Domoticz.Debug("Telnet write:" + sWrite)
                else:
                    Domoticz.Error("Received command for unknow unit: " + sDeviceID)
        # the plugin seems blocked in connecting or data sending step, restart the plugin
        elif (len(self.dqFifo) > 0) and (timeNow > (self.iConnectionTimestamp + self.timeoutConstant)) :
            Domoticz.Error("timeout during handleFifo, restart plugin")
            self.onStop()
            self.onStart()
            return
        
    def onHeartbeat(self):
        Domoticz.Debug("onHeartbeat called")
        # if started and not stopping
        if self.isStarted:
            timeNow = time.time()
            # refresh
            if (timeNow > (self.iRefreshTime + self.iRefreshRate)) :
                # we still not have detected all registers given in configuration, retry JSON search
                if self.bStillToLook:
                    self.findDevices()
                # refresh values of already detected registers
                for indexUnit, dUnit in self.dUnits.items():
                    # check this is a real unit (dict) and not a string (error)
                    if type(dUnit) is dict:
                        self.read(dUnit["index"])
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

def onUpdate(Unit, Command, Details):
    global _plugin
    _plugin.onUpdate(Unit, Command, Details)

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
    if sFieldUnit == "°C":
        return "temperature"
    elif sFieldUnit == "bar":
        return "pressure"
    elif sFieldUnit != "":
        return "custom"
    elif sFieldName == "onoff":
        return "switch"
    elif sFieldName == "yesno":
        return "selectoryesno"
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
    sCommand = sCommand.lower()
    dReverseOptionsMapping = dUnit["reverseoptions"]
    if len(dReverseOptionsMapping) > 0:
        if ifValue in dReverseOptionsMapping:
            sReturnValue = dReverseOptionsMapping[ifValue]
        else:
            sReturnValue = str(ifValue)
    elif sCommand == "on":
        sReturnValue = "on"
    elif sCommand == "yes":
        sReturnValue = "yes"
    elif sCommand == "off":
        sReturnValue = "off"
    elif sCommand == "no":
        sReturnValue = "no"
    elif sCommand == "toggle":
        if previousIValue:
            sReturnValue = "no"
        else:
            sReturnValue = "yes"
    else:
        if sValue:
            sReturnValue = sValue
        else:
            sReturnValue = str(ifValue)
            
    return sReturnValue

# convert ebus sFieldValue (string) to integer, string values for domoticz, for dUnit (dictionnary)
def valueEbusdToDomoticz(dUnit, sFieldValue):
    dOptionsMapping = dUnit["options"]
    if len(dOptionsMapping) > 0:
        if sFieldValue in dOptionsMapping:
            # iValue from GetLightStatus in RFXName.cpp and hardwaretypes.h
            iValue = 2
            sValue = str(dOptionsMapping[sFieldValue])
    else:
        sLowerFieldValue = sFieldValue.lower()
        if (sLowerFieldValue == "on") or (sLowerFieldValue == "yes"):
            iValue = 1
            sValue = "100"
        elif (sLowerFieldValue == "off") or (sLowerFieldValue == "no"):
            iValue = 0
            sValue = "100"
        else:
            try:
                iValue = int(sFieldValue)
            except ValueError:
                iValue = 0
            sValue = sFieldValue
   
    return iValue, sValue
