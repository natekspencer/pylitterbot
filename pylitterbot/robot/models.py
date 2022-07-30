"""pylitterbot robot models."""

FEEDER_ROBOT_MODEL = """
{
    id
    name
    serial
    timezone
    isEighthCupEnabled
    created_at
    household_id
    state {
        id
        info
        active_schedule_id
        updated_at
    }
}
"""

LITTER_ROBOT_4_MODEL = """
{
    unitId
    name
    serial
    userId
    espFirmware
    picFirmwareVersion
    picFirmwareVersionHex
    laserBoardFirmwareVersion
    laserBoardFirmwareVersionHex
    wifiRssi
    unitPowerType
    catWeight
    unitTimezone
    unitTime
    cleanCycleWaitTime
    isKeypadLockout
    nightLightMode
    nightLightBrightness
    isPanelSleepMode
    panelSleepTime
    panelWakeTime
    weekdaySleepModeEnabled {
        Sunday {
            sleepTime
            wakeTime
            isEnabled
        }
        Monday {
            sleepTime
            wakeTime
            isEnabled
        }
        Tuesday {
            sleepTime
            wakeTime
            isEnabled
        }
        Wednesday {
            sleepTime
            wakeTime
            isEnabled
        }
        Thursday {
            sleepTime
            wakeTime
            isEnabled
        }
        Friday {
            sleepTime
            wakeTime
            isEnabled
        }
        Saturday {
            sleepTime
            wakeTime
            isEnabled
        }
    }
    unitPowerStatus
    sleepStatus
    robotStatus
    globeMotorFaultStatus
    pinchStatus
    catDetect
    isBonnetRemoved
    isNightLightLEDOn
    odometerPowerCycles
    odometerCleanCycles
    odometerEmptyCycles
    odometerFilterCycles
    isDFIResetPending
    DFINumberOfCycles
    DFILevelPercent
    isDFIFull
    DFIFullCounter
    DFITriggerCount
    litterLevel
    DFILevelMM
    isCatDetectPending
    globeMotorRetractFaultStatus
    robotCycleStatus
    robotCycleState
    weightSensor
    isOnline
    isOnboarded
    isProvisioned
    isDebugModeActive
    lastSeen
    sessionId
    setupDateTime
    isFirmwareUpdateTriggered
    firmwareUpdateStatus
    wifiModeStatus
    isUSBPowerOn
    USBFaultStatus
    isDFIPartialFull
}"""
