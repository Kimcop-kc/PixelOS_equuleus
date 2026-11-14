# Touchscreen calibration for Xiaomi Mi 8 Pro (equuleus) FTS touchscreen
#
# The fts_521 driver obtains a pressure value from the external NDT press IC
# (ndt_get_pressure) and reports that single value 'z' to BOTH
# ABS_MT_TOUCH_MAJOR/ABS_MT_TOUCH_MINOR and ABS_MT_PRESSURE.
#
# 'z' is therefore a pressure reading, not a contact diameter. Android's
# default touch.size.calibration=GEOMETRIC interprets it as a physical size
# and, because the declared axis maximum is 2048 while real readings are in
# the low single digits, derives a contact diameter of only a few pixels.
# Taps then miss widget hit targets and users must tap several times.
#
# Fix: stop deriving a contact size from the raw axis. Pressure is left at
# its default physical calibration because the NDT press IC is a real force
# sensor used by the in-display fingerprint flow, and the value must keep
# reaching the framework unchanged.

touch.deviceType = touchScreen

# 'z' is pressure, not size: do not derive a contact diameter from it.
touch.size.calibration = none

# Keep the default physical calibration: the NDT press IC reports a real
# force value that the fingerprint flow relies on.
touch.pressure.calibration = physical

# Driver does not report a usable contact orientation.
touch.orientation.calibration = none

# Distance is a small integer (0..127); do not scale it.
touch.distance.calibration = none
