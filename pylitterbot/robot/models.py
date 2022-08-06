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
        updated_at
        active_schedule {
            id
            name
            meals
            created_at
        }
    }
    feeding_snack (limit: 10, order_by: {timestamp: desc}) {
        timestamp
        amount
    }
    feeding_meal (limit: 10, order_by: {timestamp: desc}) {
        timestamp
        amount
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
    laserBoardFirmwareVersion
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
